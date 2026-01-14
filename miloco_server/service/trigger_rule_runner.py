# Copyright (C) 2025 Xiaomi Corporation  # 版权声明：小米公司版权所有
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.  # 本软件可根据小米Miloco许可协议使用和分发

"""
Trigger business logic service  # 触发器业务逻辑服务
Handles trigger-related business logic and data validation  # 处理触发器相关的业务逻辑和数据验证
"""

import json  # 导入JSON处理模块
import time  # 导入时间处理模块
from typing import Callable, List, Dict, Optional  # 导入类型提示：可调用对象、列表、字典、可选类型
import asyncio  # 导入异步IO模块
import logging  # 导入日志模块
import uuid  # 导入UUID生成模块

from schema.mcp_schema import CallToolResult  # 从MCP模式导入工具调用结果
from thespian.actors import ActorExitRequest  # 从Thespian演员系统导入演员退出请求

from miloco_server import actor_system  # 导入演员系统
from miloco_server.config.normal_config import TRIGGER_RULE_RUNNER_CONFIG  # 导入触发器规则运行器配置
from miloco_server.config.prompt_config import UserLanguage  # 导入用户语言配置
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO  # 导入触发器规则日志数据访问对象
from miloco_server.mcp.tool_executor import ToolExecutor  # 导入工具执行器
from miloco_server.proxy.llm_proxy import LLMProxy  # 导入LLM代理
from miloco_server.proxy.miot_proxy import MiotProxy  # 导入MIoT代理
from miloco_server.schema.miot_schema import CameraImgPathSeq, CameraImgSeq, CameraInfo  # 导入摄像头相关模式：图像路径序列、图像序列、摄像头信息
from miloco_server.schema.trigger_log_schema import (  # 导入触发器日志模式
    AiRecommendDynamicExecuteResult, TriggerConditionResult, ActionExecuteResult,  # AI推荐动态执行结果、触发器条件结果、动作执行结果
    TriggerRuleLog, NotifyResult, ExecuteResult  # 触发器规则日志、通知结果、执行结果
)
from miloco_server.schema.trigger_schema import (  # 导入触发器模式
    Action, TriggerRule, ExecuteType  # 动作、触发器规则、执行类型
)
from miloco_server.utils.check_img_motion import check_camera_motion  # 导入检查图像运动函数
from miloco_server.utils.local_models import ModelPurpose  # 导入模型用途枚举
from miloco_server.utils.normal_util import extract_json_from_content  # 导入从内容中提取JSON的工具函数
from miloco_server.utils.prompt_helper import TriggerRuleConditionPromptBuilder  # 导入触发器规则条件提示构建器
from miloco_server.utils.trigger_filter import trigger_filter  # 导入触发器过滤器
from service import trigger_rule_dynamic_executor_cache  # 导入触发器规则动态执行器缓存
from service.trigger_rule_dynamic_executor import START, TriggerRuleDynamicExecutor  # 导入动态执行器：启动信号、触发器规则动态执行器

logger = logging.getLogger(name=__name__)  # 获取当前模块的日志记录器


class TriggerRuleRunner:  # 触发器规则运行器类
    """Trigger service class"""  # 触发器服务类

    def __init__(self, trigger_rules: List[TriggerRule], miot_proxy: MiotProxy,  # 初始化方法：接收触发器规则列表、MIoT代理
                 get_llm_proxy_by_purpose: Callable[[ModelPurpose], LLMProxy],  # 根据用途获取LLM代理的可调用对象
                 get_language: Callable[[], UserLanguage],  # 获取用户语言的可调用对象
                 tool_executor: ToolExecutor,  # 工具执行器
                 trigger_rule_log_dao: TriggerRuleLogDAO):  # 触发器规则日志数据访问对象

        self.trigger_rules: Dict[str, TriggerRule] = {  # 触发器规则字典：规则ID到规则的映射
            rule.id: rule  # 规则ID作为键，规则对象作为值
            for rule in trigger_rules if rule.id is not None  # 遍历规则列表，只包含有ID的规则
        }
        self._get_llm_proxy_by_purpose = get_llm_proxy_by_purpose  # 保存根据用途获取LLM代理的函数
        self.miot_proxy = miot_proxy  # 保存MIoT代理
        self._get_language = get_language  # 保存获取用户语言的函数
        self.trigger_rule_log_dao = trigger_rule_log_dao  # 保存触发器规则日志数据访问对象
        self._tool_executor = tool_executor  # 保存工具执行器
        self._task = None  # 初始化定时任务为None
        self._is_running: bool = False  # 初始化运行状态为False
        self._interval_seconds = TRIGGER_RULE_RUNNER_CONFIG["interval_seconds"]  # 从配置获取执行间隔秒数
        self._vision_use_img_count = TRIGGER_RULE_RUNNER_CONFIG["vision_use_img_count"]  # 从配置获取视觉使用的图像数量
        logger.info(  # 记录初始化成功日志
            "TriggerRuleRunner init success, trigger_rules: %s", self.trigger_rules  # 日志消息：初始化成功，包含触发器规则
        )

    def _get_vision_understaning_llm_proxy(self) -> LLMProxy:  # 获取视觉理解LLM代理的私有方法
        return self._get_llm_proxy_by_purpose(  # 返回根据用途获取的LLM代理
            ModelPurpose.VISION_UNDERSTANDING)  # 用途为视觉理解

    def add_trigger_rule(self, trigger_rule: TriggerRule):  # 添加触发器规则方法
        """Add trigger rule"""  # 添加触发器规则
        self.trigger_rules[trigger_rule.id] = trigger_rule  # 将规则添加到规则字典中

    def remove_trigger_rule(self, rule_id: str):  # 移除触发器规则方法
        """Remove trigger rule"""  # 移除触发器规则
        if rule_id in self.trigger_rules:  # 如果规则ID存在于规则字典中
            del self.trigger_rules[rule_id]  # 从字典中删除该规则

    async def _periodic_task(self):  # 周期性任务异步方法
        """Scheduled task execution method, runs at configured interval"""  # 定时任务执行方法，按配置的间隔运行
        while self._is_running:  # 当运行状态为True时循环执行
            try:  # 尝试执行
                # Execute scheduled task logic  # 执行定时任务逻辑
                asyncio.create_task(self._execute_scheduled_task())  # 创建异步任务执行定时任务
                # Wait for configured interval  # 等待配置的间隔时间
                await asyncio.sleep(self._interval_seconds)  # 异步等待指定的秒数
            except Exception as e:  # pylint: disable=broad-except  # 捕获所有异常
                logger.error(  # 记录错误日志
                    "Error occurred while executing scheduled task: %s", e)  # 日志消息：执行定时任务时发生错误
                await asyncio.sleep(self._interval_seconds)  # 即使出错也等待指定间隔后继续

    async def _execute_scheduled_task(self):  # 执行定时任务的异步方法
        """Specific execution logic for scheduled tasks"""  # 定时任务的具体执行逻辑
        logger.info("Executing scheduled task - checking trigger rules")  # 记录日志：正在执行定时任务，检查触发器规则
        llm_proxy = self._get_vision_understaning_llm_proxy()  # 获取视觉理解LLM代理
        if not llm_proxy:  # 如果LLM代理不可用
            logger.warning(  # 记录警告日志
                "Vision understaning LLM proxy not available, skipping rules trigger")  # 日志消息：视觉理解LLM代理不可用，跳过规则触发
            return  # 直接返回
        start_time = int(time.time() * 1000)  # 记录开始时间（毫秒时间戳）

        # Filter triggerable rules  # 过滤可触发的规则
        enabled_rules = [(rule_id, rule)  # 创建规则ID和规则的元组列表
                         for rule_id, rule in self.trigger_rules.items()  # 遍历所有触发器规则
                         if trigger_filter.pre_filter(rule)]  # 使用预过滤器筛选规则

        if not enabled_rules:  # 如果没有启用的规则
            logger.info("No enabled trigger rules to check")  # 记录日志：没有需要检查的启用规则
            return  # 直接返回

        # Calculate all camera motion changes  # 计算所有摄像头的运动变化
        miot_camera_info_dict = await self.miot_proxy.get_cameras()  # 异步获取MIoT摄像头信息字典
        camera_info_dict = {  # 创建摄像头信息字典
            camera_id: CameraInfo.model_validate(miot_camera_info.model_dump())  # 将MIoT摄像头信息转换为CameraInfo对象
            for camera_id, miot_camera_info in miot_camera_info_dict.items()  # 遍历所有MIoT摄像头
        }
        
        # 用于获取HA摄像头信息，并将其合并到已有的MIoT摄像头字典中，以便后续统一处理所有摄像头  # 用于获取HA摄像头信息，并将其合并到已有的MIoT摄像头字典中，以便后续统一处理所有摄像头
        try:  # 尝试执行
            from miloco_server.service.manager import get_manager  # 导入获取管理器函数
            manager = get_manager()  # 获取管理器实例
            ha_cameras = await manager.ha_service.get_ha_cameras()  # 异步获取HA摄像头列表
            for ha_camera in ha_cameras:  # 遍历HA摄像头列表
                camera_info_dict[ha_camera.did] = ha_camera  # 将HA摄像头添加到摄像头信息字典中
            logger.debug("Merged %d HA cameras with %d MIoT cameras",  # 记录调试日志：合并了多少HA摄像头和MIoT摄像头
                        len(ha_cameras), len(camera_info_dict) - len(ha_cameras))  # 日志参数：HA摄像头数量、MIoT摄像头数量
        except Exception as e:  # pylint: disable=broad-exception-caught  # 捕获所有异常
            logger.warning("Failed to get HA cameras, continuing with MIoT cameras only: %s", e)  # 记录警告日志：获取HA摄像头失败，仅使用MIoT摄像头
        
        camera_motion_dict: dict[str,  # 摄像头运动字典：摄像头ID到通道运动数据的映射
                                 dict[int,  # 通道号到运动检测结果的映射
                                      tuple[bool,  # 是否检测到运动（布尔值）
                                            Optional[CameraImgSeq]]]] = {}  # 可选的摄像头图像序列

        for camera_id, camera_info in camera_info_dict.items():  # 遍历所有摄像头信息
            if camera_id not in camera_motion_dict:  # 如果摄像头ID不在运动字典中
                camera_motion_dict[camera_id] = {}  # 为该摄像头创建空字典
            
            # 检查是否为HA摄像头  # 检查是否为HA摄像头
            is_ha_camera = camera_id.startswith("ha_")  # 判断摄像头ID是否以"ha_"开头
            
            for channel in range(camera_info.channel_count or 1):  # 遍历摄像头的所有通道（如果没有通道数则默认为1）
                logger.info(  # 记录信息日志
                    "camera %s channel %s get recent camera img", camera_id, channel  # 日志消息：获取摄像头最近图像
                )
                
                # 根据摄像头类型获取摄像头图像  # 根据摄像头类型获取摄像头图像
                if is_ha_camera:  # 如果是HA摄像头
                    # 对于HA摄像头，使用ha_proxy获取图像  # 对于HA摄像头，使用ha_proxy获取图像
                    try:  # 尝试执行
                        from miloco_server.service.manager import get_manager  # 导入获取管理器函数
                        manager = get_manager()  # 获取管理器实例
                        entity_id = camera_id[3:]  # Remove "ha_" prefix  # 移除"ha_"前缀获取实体ID
                        camera_img_seq = await manager.ha_proxy.get_recent_camera_img(  # 异步获取HA摄像头最近图像序列
                            entity_id, channel, self._vision_use_img_count)  # 参数：实体ID、通道号、使用的图像数量
                    except Exception as e:  # pylint: disable=broad-exception-caught  # 捕获所有异常
                        logger.warning("Failed to get HA camera image for %s: %s", camera_id, e)  # 记录警告日志：获取HA摄像头图像失败
                        camera_img_seq = None  # 将图像序列设为None
                else:  # 否则（MIoT摄像头）
                    # For MIoT cameras, use miot_proxy  # 对于MIoT摄像头，使用miot_proxy
                    camera_img_seq = self.miot_proxy.get_recent_camera_img(  # 获取MIoT摄像头最近图像序列
                        camera_id, channel, self._vision_use_img_count)  # 参数：摄像头ID、通道号、使用的图像数量
                
                if camera_img_seq and self._check_camera_motion(  # 如果图像序列存在且检测到运动
                        camera_img_seq):  # 检查摄像头运动
                    logger.info(  # 记录信息日志
                        "camera %s channel %s motion: true", camera_id, channel)  # 日志消息：检测到运动
                    camera_motion_dict[camera_id][channel] = (True,  # 在运动字典中记录：检测到运动
                                                              camera_img_seq)  # 保存图像序列
                else:  # 否则（未检测到运动或没有图像）
                    logger.info(  # 记录信息日志
                        "camera %s channel %s motion: false", camera_id, channel)  # 日志消息：未检测到运动
                    camera_motion_dict[camera_id][channel] = (False,  # 在运动字典中记录：未检测到运动
                                                              camera_img_seq)  # 保存图像序列（可能为None）

        # Create concurrent task list  # 创建并发任务列表
        tasks = []  # 初始化任务列表
        rule_info_list = []  # 初始化规则信息列表
        for rule_id, rule in enabled_rules:  # 遍历所有启用的规则
            logger.info(  # 记录信息日志
                "Preparing to check trigger rule: %s %s", rule_id, rule.name)  # 日志消息：准备检查触发器规则
            task = self._check_trigger_condition(rule, llm_proxy,  # 创建检查触发器条件的异步任务
                                                 camera_motion_dict,  # 传入摄像头运动字典
                                                 camera_info_dict)  # 传入摄像头信息字典
            tasks.append(task)  # 将任务添加到任务列表
            rule_info_list.append((rule_id, rule))  # 将规则ID和规则添加到规则信息列表

        # Concurrently execute all trigger rule checks  # 并发执行所有触发器规则检查
        condition_results = await asyncio.gather(*tasks,  # 等待所有任务完成
                                                 return_exceptions=True)  # 返回异常而不是抛出

        # Process results  # 处理结果
        for (rule_id,  # 遍历规则ID
             rule), condition_result_list in zip(rule_info_list,  # 和规则，以及条件结果列表（通过zip配对）
                                                 condition_results):  # 和条件结果
            # Check for exceptions  # 检查异常
            if isinstance(condition_result_list, Exception):  # 如果条件结果列表是异常类型
                logger.error(  # 记录错误日志
                    "Rule check failed for %s %s: %s", rule_id, rule.name, condition_result_list  # 日志消息：规则检查失败
                )
                continue  # 跳过当前规则，继续下一个

            # Ensure return type is list  # 确保返回类型是列表
            if not isinstance(condition_result_list, list):  # 如果条件结果列表不是列表类型
                logger.error(  # 记录错误日志
                    "Invalid condition result type for rule %s: %s", rule_id, type(condition_result_list)  # 日志消息：无效的条件结果类型
                )
                continue  # 跳过当前规则，继续下一个

            execable = any([  # 判断规则是否可执行（任意一个条件结果通过后过滤）
                trigger_filter.post_filter(  # 使用后过滤器
                    rule_id,  # 规则ID
                    f"{condition_result.camera_info.did},{condition_result.channel}",  # 摄像头ID和通道号的组合字符串
                    condition_result.result)  # 条件结果
                for condition_result in condition_result_list  # 遍历所有条件结果
            ])

            is_dynamic_action_running = self._check_dynamic_action_is_running(rule_id)  # 检查动态动作是否正在运行
            logger.info(  # 记录信息日志
                "Rule %s is execable: %s, dynamic action is running: %s",  # 日志消息：规则是否可执行，动态动作是否运行
                rule_id, execable, is_dynamic_action_running)  # 日志参数：规则ID、是否可执行、动态动作是否运行

            if execable and not is_dynamic_action_running:  # 如果规则可执行且动态动作未运行
                execute_id = str(uuid.uuid4())  # 生成执行ID（UUID字符串）
                execute_result = await self._execute_trigger_action(  # 异步执行触发器动作
                    execute_id, rule, camera_motion_dict)  # 参数：执行ID、规则、摄像头运动字典
                await self._log_rule_execution(execute_id, start_time, rule,  # 异步记录规则执行日志
                                               camera_motion_dict,  # 摄像头运动字典
                                               condition_result_list,  # 条件结果列表
                                               execute_result)  # 执行结果

        logger.info(  # 记录信息日志
            "Scheduled task completed, checked %d trigger rules", len(enabled_rules)  # 日志消息：定时任务完成，检查了多少个触发器规则
        )

    async def _log_rule_execution(  # 记录规则执行日志的异步方法
            self,  # 自身引用
            execute_id: str,  # 执行ID
            start_time: int,  # 开始时间（毫秒时间戳）
            rule: TriggerRule,  # 触发器规则对象
            camera_motion_dict: dict[str, dict[int,  # 摄像头运动字典：摄像头ID到通道运动数据的映射
                                           tuple[bool,  # 是否检测到运动（布尔值）
                                                 Optional[CameraImgSeq]]]],  # 可选的摄像头图像序列
            condition_result_list: list[TriggerConditionResult],  # 条件结果列表
            execute_result: Optional[ExecuteResult] = None):  # 可选的执行结果
        """Record rule trigger and execution logs, save to database"""  # 记录规则触发和执行日志，保存到数据库
        logger.info(  # 记录信息日志
            "Rule %s triggered, condition results: %s", rule.name, condition_result_list  # 日志消息：规则触发，包含条件结果
        )

        for condition_result in condition_result_list:  # 遍历所有条件结果
            camera_id = condition_result.camera_info.did  # 获取摄像头ID
            channel = condition_result.channel  # 获取通道号
            # 检查摄像头和通道是否存在于camera_motion_dict中，如果不存在则记录日志并跳过
            if camera_id not in camera_motion_dict:  # 如果摄像头ID不在运动字典中
                logger.warning("Camera %s not found in camera_motion_dict when logging", camera_id)  # 记录警告日志：摄像头未找到
                continue  # 跳过当前循环
            if channel not in camera_motion_dict[camera_id]:  # 如果通道不在摄像头字典中
                logger.warning("Channel %s not found for camera %s when logging", channel, camera_id)  # 记录警告日志：通道未找到
                continue  # 跳过当前循环
            
            is_motion, camera_img_seq = camera_motion_dict[camera_id][channel]  # 获取摄像头运动状态和图像序列
            # 只要记录规则日志就保存图片（只要有图像序列就保存）
            if camera_img_seq:  # 如果图像序列存在
                path_seq: CameraImgPathSeq = await camera_img_seq.store_to_path()  # 异步将图像序列存储到路径
                condition_result.images = path_seq.img_list  # 将图像路径列表赋值给条件结果的图像字段

        trigger_rule_log = TriggerRuleLog(  # 创建触发器规则日志对象
            id=execute_id,  # 执行ID
            timestamp=start_time,  # 时间戳
            trigger_rule_id=rule.id,  # 触发器规则ID
            trigger_rule_name=rule.name,  # 触发器规则名称
            trigger_rule_condition=rule.condition,  # 触发器规则条件
            condition_results=condition_result_list,  # 条件结果列表
            execute_result=execute_result,  # 执行结果
        )

        # Save to database  # 保存到数据库
        log_id = self.trigger_rule_log_dao.create(trigger_rule_log)  # 创建日志记录并获取日志ID
        if log_id:  # 如果日志ID存在（创建成功）
            logger.info(  # 记录信息日志
                "Trigger rule log saved to database: id=%s, rule_id=%s", log_id, rule.id  # 日志消息：触发器规则日志已保存到数据库
            )
        else:  # 否则（创建失败）
            logger.error(  # 记录错误日志
                "Failed to save trigger rule log to database: rule_id=%s", rule.id  # 日志消息：保存触发器规则日志到数据库失败
            )

    def start_periodic_task(self):  # 启动周期性任务方法
        """Start async scheduled task"""  # 启动异步定时任务
        if self._is_running:  # 如果任务正在运行
            logger.warning("Scheduled task is already running")  # 记录警告日志：定时任务已在运行
            return  # 直接返回

        self._is_running = True  # 设置运行状态为True
        self._task = asyncio.create_task(self._periodic_task())  # 创建异步任务并保存
        logger.info("Scheduled task started, executing every %d seconds", self._interval_seconds)  # 记录信息日志：定时任务已启动

    async def stop_periodic_task(self):  # 停止周期性任务的异步方法
        """Stop async scheduled task"""  # 停止异步定时任务
        if not self._is_running:  # 如果任务未运行
            logger.warning("Scheduled task is not running")  # 记录警告日志：定时任务未运行
            return  # 直接返回

        self._is_running = False  # 设置运行状态为False
        if self._task and not self._task.done():  # 如果任务存在且未完成
            self._task.cancel()  # 取消任务
            try:  # 尝试执行
                await self._task  # 等待任务完成
            except asyncio.CancelledError:  # 捕获取消异常
                pass  # 忽略取消异常

        logger.info("Scheduled task stopped")  # 记录信息日志：定时任务已停止

    def is_task_running(self) -> bool:  # 检查任务是否正在运行的方法
        """Check if scheduled task is running"""  # 检查定时任务是否正在运行
        return self._is_running  # 返回运行状态

    async def _call_vision_understaning(self, llm_proxy: LLMProxy, messages):  # 调用视觉理解LLM的异步方法
        """
        Call vision understanding LLM  # 调用视觉理解LLM

        Returns:  # 返回
            LLM response result  # LLM响应结果
        """

        return await llm_proxy.async_call_llm(messages)  # 异步调用LLM并返回结果

    async def _check_trigger_condition(  # 检查触发器条件的异步方法
        self, rule: TriggerRule, llm_proxy: LLMProxy,  # 自身引用、触发器规则、LLM代理
        camera_motion_dict: dict[str, dict[int,  # 摄像头运动字典：摄像头ID到通道运动数据的映射
                                           tuple[bool,  # 是否检测到运动（布尔值）
                                                 Optional[CameraImgSeq]]]],  # 可选的摄像头图像序列
        camera_info_dict: dict[str,  # 摄像头信息字典：摄像头ID到摄像头信息的映射
                               CameraInfo]) -> List[TriggerConditionResult]:  # 返回触发器条件结果列表

        cameras_video: dict[tuple[str, int], CameraImgSeq] = {}  # 摄像头视频字典：摄像头ID和通道号的元组到图像序列的映射
        condition_result_list: List[TriggerConditionResult] = []  # 条件结果列表

        for camera_id in rule.cameras:  # 遍历规则中的所有摄像头ID
            # Check if camera exists in camera_info_dict  # 检查摄像头是否存在于摄像头信息字典中
            if camera_id not in camera_info_dict:  # 如果摄像头ID不在信息字典中
                logger.warning("Camera %s not found in camera_info_dict, skipping", camera_id)  # 记录警告日志：摄像头未找到
                continue  # 跳过当前循环
            
            # Check if camera exists in camera_motion_dict  # 检查摄像头是否存在于摄像头运动字典中
            if camera_id not in camera_motion_dict:  # 如果摄像头ID不在运动字典中
                logger.warning("Camera %s not found in camera_motion_dict, skipping", camera_id)  # 记录警告日志：摄像头未找到
                continue  # 跳过当前循环
            
            camera_info = camera_info_dict[camera_id]  # 摄像头基本信息对象
            channel_motion_dict = camera_motion_dict[camera_id]  # 该摄像头所有通道的运动检测数据字典
            for channel, (if_motion,  # 遍历通道和运动检测结果
                          camera_img_seq) in channel_motion_dict.items():  # 获取通道号、运动状态和图像序列
                # 即使没有检测到运动，如果有图像仍然检查条件
                # 这允许检测静态场景
                if not camera_img_seq:  # 如果图像序列为空，则记录日志并跳过LLM检查
                    logger.debug("Camera %s channel %s: no image sequence, skipping LLM check", camera_id, channel)  # 记录调试日志：无图像序列
                    condition_result_list.append(  # 添加条件结果到列表
                        TriggerConditionResult(camera_info=camera_info,  # 摄像头信息
                                               channel=channel,  # 通道号
                                               result=False,  # 结果为False
                                               images=None))  # 图像为None
                    continue  # 跳过当前循环

                # 检查图像列表是否为空，如果为空则记录日志并跳过LLM检查
                if not camera_img_seq.img_list or len(camera_img_seq.img_list) == 0:  # 如果图像列表为空或长度为0
                    logger.debug("Camera %s channel %s: image list is empty (len=%d), skipping LLM check",  # 记录调试日志：图像列表为空
                               camera_id, channel, len(camera_img_seq.img_list) if camera_img_seq.img_list else 0)  # 日志参数：摄像头ID、通道号、图像列表长度
                    condition_result_list.append(  # 添加条件结果到列表
                        TriggerConditionResult(camera_info=camera_info,  # 摄像头信息
                                               channel=channel,  # 通道号
                                               result=False,  # 结果为False
                                               images=None))  # 图像为None
                    continue  # 跳过当前循环

                logger.debug("Camera %s channel %s: adding to LLM check queue (motion=%s, img_count=%d)",  # 记录调试日志：添加到LLM检查队列
                           camera_id, channel, if_motion, len(camera_img_seq.img_list))  # 日志参数：摄像头ID、通道号、运动状态、图像数量
                cameras_video[camera_id, channel] = camera_img_seq  # 将图像序列添加到摄像头视频字典

        # 如果cameras_video不为空，则记录日志：将检查多少个摄像头通过LLM
        if cameras_video:  # 如果摄像头视频字典不为空
            logger.info("Will check %d camera(s) with LLM for rule %s: %s",  # 记录信息日志：将检查多少个摄像头
                       len(cameras_video), rule.name, list(cameras_video.keys()))  # 日志参数：摄像头数量、规则名称、摄像头键列表
        else:  # 否则
            logger.info("No cameras with valid images for LLM check in rule %s", rule.name)  # 记录信息日志：没有有效的摄像头图像

        # Concurrently execute LLM calls for all cameras  # 并发执行所有摄像头的LLM调用
        tasks = []  # 初始化任务列表
        for (camera_id, channel), camera_img_seq in cameras_video.items():  # 遍历摄像头视频字典
            messages = TriggerRuleConditionPromptBuilder.build_trigger_rule_prompt(  # 构建触发器规则提示消息
                camera_img_seq, rule.condition, self._get_language())  # 参数：图像序列、规则条件、用户语言
            
            # 记录调试信息：图像数量和条件
            img_count = len(camera_img_seq.img_list) if camera_img_seq and camera_img_seq.img_list else 0  # 获取图像数量
            logger.info(  # 记录信息日志
                "Calling LLM for rule %s, camera %s channel %s: condition='%s', image_count=%d",  # 日志消息：调用LLM
                rule.name, camera_id, channel, rule.condition, img_count  # 日志参数：规则名称、摄像头ID、通道号、条件、图像数量
            )
            
            # ---------%%%%%-------->>>>>>>>>> 在这里1调用视觉理解LLM
            task = self._call_vision_understaning(llm_proxy, messages.get_messages())  # 创建调用视觉理解LLM的异步任务
            tasks.append(task)  # 将任务添加到任务列表

        # Concurrently execute all tasks  # 并发执行所有任务
        responses = await asyncio.gather(*tasks, return_exceptions=True)  # 等待所有任务完成，返回异常而不是抛出

        # Process results  # 处理结果
        for ((camera_id, channel),  # 遍历摄像头ID和通道号
             camera_img_seq), response in zip(cameras_video.items(),  # 和图像序列，以及响应（通过zip配对）
                                              responses):  # 和响应列表
            # Check for exceptions  # 检查异常
            if isinstance(response, Exception):  # 如果响应是异常类型
                logger.error(  # 记录错误日志
                    "LLM call failed for camera %s channel %s: %s", camera_id, channel, response  # 日志消息：LLM调用失败
                )
                continue  # 跳过当前循环

            # Ensure response is dict type before accessing  # 在访问前确保响应是字典类型
            if not isinstance(response, dict):  # 如果响应不是字典类型
                logger.error(  # 记录错误日志
                    "Invalid response type for camera %s channel %s: %s", camera_id, channel, type(response)  # 日志消息：无效的响应类型
                )
                continue  # 跳过当前循环

            content = response["content"]  # 获取响应内容
            
            # 记录图像数量以便调试
            img_count = len(camera_img_seq.img_list) if camera_img_seq and camera_img_seq.img_list else 0  # 获取图像数量
            logger.info(  # 记录信息日志
                "Condition result, rule name: %s, rule condition: %s, camera_id: %s, channel: %s, image_count: %d, content: %s",  # 日志消息：条件结果
                rule.name, rule.condition, camera_id, channel, img_count, content  # 日志参数：规则名称、条件、摄像头ID、通道号、图像数量、内容
            )

            if not content:  # 如果内容为空
                continue  # 跳过当前循环

            try:  # 尝试执行
                # Use optimized helper method to extract JSON content  # 使用优化的辅助方法提取JSON内容
                json_content = extract_json_from_content(content)  # 从内容中提取JSON
                content_dict = json.loads(json_content)  # 解析JSON内容为字典
            except json.JSONDecodeError as e:  # 捕获JSON解码错误
                logger.error(  # 记录错误日志
                    "Failed to parse JSON content. Original: %s, Extracted: %s, Error: %s",  # 日志消息：解析JSON内容失败
                    content, json_content if "json_content" in locals() else "N/A", e)  # 日志参数：原始内容、提取的JSON、错误信息
                continue  # 跳过当前循环
            except Exception as e:  # pylint: disable=broad-except  # 捕获所有其他异常
                logger.error(  # 记录错误日志
                    "Unexpected error while processing content: %s, Error: %s", content, e)  # 日志消息：处理内容时发生意外错误
                continue  # 跳过当前循环

            condition_result: TriggerConditionResult = TriggerConditionResult(  # 创建触发器条件结果对象
                camera_info=camera_info_dict[camera_id],  # 摄像头信息
                channel=channel,  # 通道号
                result=content_dict["result"] == "yes")  # 结果：判断字典中的result字段是否等于"yes"

            condition_result_list.append(condition_result)  # 将条件结果添加到列表
        return condition_result_list  # 返回条件结果列表

    def _check_camera_motion(self, camera_img_seq: CameraImgSeq) -> bool:  # 检查摄像头运动的私有方法
        """Detect motion in images"""  # 检测图像中的运动
        if len(camera_img_seq.img_list) < 2:  # 如果图像列表长度小于2
            return False  # 返回False（无法检测运动）
        return check_camera_motion(camera_img_seq.img_list[0].data,  # 检查第一张图像
                                   camera_img_seq.img_list[-1].data)  # 和最后一张图像之间的运动

    async def _execute_trigger_action(  # 执行触发器动作的异步方法
        self, execute_id: str, rule: TriggerRule,  # 自身引用、执行ID、触发器规则
        camera_motion_dict: dict[str, dict[int,  # 摄像头运动字典：摄像头ID到通道运动数据的映射
                                           tuple[bool,  # 是否检测到运动（布尔值）
                                                 Optional[CameraImgSeq]]]]  # 可选的摄像头图像序列
    ) -> Optional[ExecuteResult]:  # 返回可选的执行结果
        """Execute trigger action"""  # 执行触发器动作
        logger.info("[%s] Executing trigger action: %s", execute_id, rule.name)  # 记录信息日志：正在执行触发器动作

        if not rule.execute_info:  # 如果规则没有执行信息
            return None  # 返回None

        execute_type = rule.execute_info.ai_recommend_execute_type  # 获取AI推荐执行类型
        ai_recommend_action_execute_results = None  # 初始化AI推荐动作执行结果为None
        ai_recommend_dynamic_execute_result = None  # 初始化AI推荐动态执行结果为None
        automation_action_execute_results = None  # 初始化自动化动作执行结果为None
        notify_result = None  # 初始化通知结果为None

        # Handle STATIC action type  # 处理静态动作类型
        if execute_type == ExecuteType.STATIC and rule.execute_info.ai_recommend_actions:  # 如果执行类型是静态且有AI推荐动作
            ai_recommend_action_execute_results = []  # 初始化AI推荐动作执行结果列表
            for action in rule.execute_info.ai_recommend_actions:  # 遍历所有AI推荐动作
                result = await self.execute_action(action)  # 异步执行动作
                ai_recommend_action_execute_results.append(  # 添加动作执行结果到列表
                    ActionExecuteResult(action=action, result=result))  # 创建动作执行结果对象

        # Handle DYNAMIC action type  # 处理动态动作类型
        if execute_type == ExecuteType.DYNAMIC:  # 如果执行类型是动态
            ai_recommend_dynamic_execute_result = AiRecommendDynamicExecuteResult(  # 创建AI推荐动态执行结果对象
                is_done=False,  # 未完成
                ai_recommend_action_descriptions=rule.execute_info.ai_recommend_action_descriptions,  # AI推荐动作描述
                chat_history_session=None)  # 聊天历史会话为None
            if rule.execute_info.ai_recommend_action_descriptions:  # 如果有AI推荐动作描述
                # execute dynamic action in background  # 在后台执行动态动作
                asyncio.create_task(self._execute_dynamic_action(execute_id, rule, camera_motion_dict))  # 创建异步任务执行动态动作
            else:  # 否则
                ai_recommend_dynamic_execute_result.is_done = True  # 设置完成状态为True
                logger.warning("[%s] Dynamic action descriptions not found, skip dynamic action", execute_id)  # 记录警告日志：动态动作描述未找到

        # Handle automation actions  # 处理自动化动作
        if rule.execute_info.automation_actions:  # 如果有自动化动作
            automation_action_execute_results = []  # 初始化自动化动作执行结果列表
            for action in rule.execute_info.automation_actions:  # 遍历所有自动化动作
                result = await self.execute_action(action)  # 异步执行动作
                automation_action_execute_results.append(  # 添加动作执行结果到列表
                    ActionExecuteResult(action=action, result=result))  # 创建动作执行结果对象

        # Send MiOT notification  # 发送MIoT通知
        if rule.execute_info.notify:  # 如果有通知配置
            notify_res = await self.miot_proxy.send_app_notify(rule.execute_info.notify.id)  # 异步发送应用通知
            logger.info("Send miot notify result: %s, notify: %s", notify_res, rule.execute_info.notify)  # 记录信息日志：发送MIoT通知结果
            notify_result = NotifyResult(notify=rule.execute_info.notify, result=notify_res)  # 创建通知结果对象

        return ExecuteResult(  # 返回执行结果对象
            ai_recommend_execute_type=execute_type,  # AI推荐执行类型
            ai_recommend_action_execute_results=ai_recommend_action_execute_results,  # AI推荐动作执行结果
            ai_recommend_dynamic_execute_result=ai_recommend_dynamic_execute_result,  # AI推荐动态执行结果
            automation_action_execute_results=automation_action_execute_results,  # 自动化动作执行结果
            notify_result=notify_result  # 通知结果
        )

    async def _execute_dynamic_action(self, execute_id: str, rule: TriggerRule,  # 执行动态动作的异步方法：执行ID、触发器规则
                                    camera_motion_dict: dict[str, dict[int,  # 摄像头运动字典：摄像头ID到通道运动数据的映射
                                           tuple[bool,  # 是否检测到运动（布尔值）
                                                 Optional[CameraImgSeq]]]]) -> None:  # 可选的摄像头图像序列，返回None
        """Execute dynamic action"""  # 执行动态动作
        try:  # 尝试执行
            logger.info("[%s] Executing dynamic action: %s", execute_id, rule.name)  # 记录信息日志：正在执行动态动作
            trigger_rule_dynamic_executor = trigger_rule_dynamic_executor_cache.get(rule.id)  # 从缓存获取动态执行器
            if trigger_rule_dynamic_executor:  # 如果动态执行器已存在
                logger.error(  # 记录错误日志
                    "[%s] Dynamic executor already exists pass it, trigger_rule: %s",  # 日志消息：动态执行器已存在
                    execute_id, rule.name)  # 日志参数：执行ID、规则名称
                return  # 直接返回

            trigger_rule_dynamic_executor = actor_system.createActor(  # 创建演员（Actor）
                lambda: TriggerRuleDynamicExecutor(  # Lambda函数创建触发器规则动态执行器
                    execute_id, rule, self.trigger_rule_log_dao, camera_motion_dict))  # 参数：执行ID、规则、日志DAO、摄像头运动字典
            trigger_rule_dynamic_executor_cache[rule.id] = trigger_rule_dynamic_executor  # 将动态执行器添加到缓存
            future = actor_system.ask(trigger_rule_dynamic_executor, START, timeout=5)  # 向演员发送START消息并获取Future
            result = await asyncio.wait_for(future, timeout=300)  # 等待Future完成，超时时间为300秒
            logger.info("[%s] Dynamic executor executed, result: %s", execute_id, result)  # 记录信息日志：动态执行器已执行
        except asyncio.TimeoutError as exc:  # 捕获超时异常
            logger.error("[%s] Dynamic executor timeout: %s", execute_id, exc)  # 记录错误日志：动态执行器超时
        except Exception as e:  # pylint: disable=broad-except  # 捕获所有其他异常
            logger.error("[%s] Dynamic executor error: %s", execute_id, e)  # 记录错误日志：动态执行器错误
        finally:  # 最终执行
            actor_system.tell(trigger_rule_dynamic_executor, ActorExitRequest())  # 向演员发送退出请求
            trigger_rule_dynamic_executor_cache.pop(rule.id, None)  # 从缓存中移除动态执行器

    async def execute_action(self, action: Action) -> bool:  # 执行动作的异步方法
        """Execute MCP action"""  # 执行MCP动作
        try:  # 尝试执行
            logger.info("Executing MCP action: %s on server %s", action.mcp_tool_name, action.mcp_server_name)  # 记录信息日志：正在执行MCP动作

            result: CallToolResult = await self._tool_executor.execute_tool_by_params(  # 异步执行工具并获取结果
                action.mcp_client_id, action.mcp_tool_name,  # 参数：MCP客户端ID、MCP工具名称
                action.mcp_tool_input)  # MCP工具输入

            logger.info("MCP action executed successfully: %s, result: %s", action.mcp_tool_name, result)  # 记录信息日志：MCP动作执行成功
            return result.success  # 返回执行是否成功

        except Exception as e:  # pylint: disable=broad-except  # 捕获所有异常
            logger.error(  # 记录错误日志
                "Failed to execute MCP action %s: %s", action.mcp_tool_name, e)  # 日志消息：执行MCP动作失败
            return False  # 返回False

    def _check_dynamic_action_is_running(self, rule_id: str) -> bool:  # 检查动态动作是否正在运行的私有方法
        """Check if dynamic action is running"""  # 检查动态动作是否正在运行
        return rule_id in trigger_rule_dynamic_executor_cache  # 返回规则ID是否在动态执行器缓存中
