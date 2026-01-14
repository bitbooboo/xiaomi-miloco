# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Rule trigger filter utility for managing trigger frequency and conditions.
Provides functionality to filter trigger rules based on frequency, period, and condition changes.
"""

import datetime
import logging
from collections import deque
from typing import Dict, OrderedDict

from croniter import croniter

from miloco_server.schema.trigger_schema import TriggerRule, TriggerFrequencyFilter

logger = logging.getLogger(name=__name__)


class RuleTriggerFilter:
    """Rule trigger filter class"""
    _CONTINUOUS_CHECK_INTERVAL: int = 1000 * 10    # Post-processing continuous non-trigger detection interval ms
    _TRIGGER_INTERVAL_MIN: int = 1000 * 10  # Post-processing trigger interval minimum value ms

    # Record rule condition changes for specified camera
    _condition_history: Dict[str, Dict[str, OrderedDict[int, bool]]]
    # Record trigger time queue for specified rule
    _trigger_history: Dict[str, deque]

    def __init__(self):
        self._condition_history = {}
        self._trigger_history = {}

    def _default_rule_state(self, rule_id: str, camera_tag: str = None, filter_frequency: int = 1):
        """Default rule state."""
        self._condition_history.setdefault(rule_id, {})

        if camera_tag:
            self._condition_history[rule_id].setdefault(camera_tag, OrderedDict())

        self._trigger_history.setdefault(rule_id, deque(maxlen=filter_frequency))

    def pre_filter(self, rule: TriggerRule) -> bool:  # 预过滤器方法：在触发前进行过滤检查
        """Pre Trigger filter."""  # 预触发器过滤器
        ts_now = int(datetime.datetime.now().timestamp() * 1000)  # 获取当前时间戳（毫秒）
        if not rule.enabled:  # 如果规则未启用
            return False  # 返回False，不允许触发

        if not rule.filter:  # 如果规则没有过滤器配置
            return True  # 返回True，允许触发

        frequency = rule.filter.frequency.frequency if rule.filter.frequency else 1  # 获取触发频率，如果没有则默认为1
        self._default_rule_state(rule.id, filter_frequency=frequency)  # 初始化规则状态，设置触发历史队列的最大长度

        # Check trigger period  # 检查触发时间段
        cron_expression = rule.filter.period  # 获取Cron表达式（时间段配置）
        if cron_expression and croniter.is_valid(cron_expression):  # 如果Cron表达式存在且有效
            if not croniter.match(cron_expression, datetime.datetime.fromtimestamp(ts_now/1000)):  # 如果当前时间不匹配Cron表达式
                logger.info(  # 记录信息日志
                    "trigger_pre_filter rule-%s: period_cron: %s mismatch now_timestamp: %d, Not Exec",  # 日志消息：时间段不匹配
                    rule.id, cron_expression, ts_now)  # 日志参数：规则ID、Cron表达式、当前时间戳
                return False  # 返回False，不允许触发

        # Check trigger frequency  # 检查触发频率
        trigger_queue: deque = self._trigger_history[rule.id]  # 获取该规则的触发历史队列
        filters = [rule.filter.frequency] if rule.filter.frequency else []  # 如果存在频率过滤器，则添加到过滤器列表
        if rule.filter.interval:  # 如果存在间隔配置
            filters.append(TriggerFrequencyFilter(frequency=1, period=rule.filter.interval))  # 添加间隔过滤器到过滤器列表

        for freq_filter in filters:  # 遍历所有频率过滤器
            if (len(trigger_queue) >= freq_filter.frequency and  # 如果触发队列长度大于等于频率阈值
                    ts_now - trigger_queue[-freq_filter.frequency] < freq_filter.period * 1000):  # 且距离第N次触发的时间小于周期（转换为毫秒）
                logger.info(  # 记录信息日志
                    "trigger_pre_filter rule-%s: over frequency: %d/%ds, Not Exec",  # 日志消息：超过频率限制
                    rule.id, freq_filter.frequency, freq_filter.period)  # 日志参数：规则ID、频率、周期
                return False  # 返回False，不允许触发

        return True  # 返回True，允许触发

    def post_filter(self, rule_id: str, camera_tag: str, result: bool) -> bool:
        """Post Trigger filter."""
        ts_now = int(datetime.datetime.now().timestamp() * 1000)
        self._default_rule_state(rule_id, camera_tag=camera_tag)

        # FIFO, remove oldest
        conditions: OrderedDict[int, bool] = self._condition_history[rule_id][camera_tag]
        while len(conditions) > 0 and list(conditions.keys())[0] < ts_now - self._CONTINUOUS_CHECK_INTERVAL:
            conditions.popitem(last=False)

        last_status = any(list(conditions.values())) # 历史状态的整体判断
        conditions[ts_now] = result

        # 检查连续状态（总体）是否与当前检测结果（result）相同
        if last_status == result:
            # 如果状态为 True（条件满足），在达到最小间隔后允许重新触发
            # 这允许对持续存在的条件进行周期性通知
            if result:  # 条件为 True（例如，检测到入侵）
                if len(self._trigger_history[rule_id]) > 0: # 检查是否有历史触发记录
                    time_since_last_trigger = ts_now - self._trigger_history[rule_id][-1] # 计算距离上次触发的时间间隔（毫秒）
                    if time_since_last_trigger >= self._TRIGGER_INTERVAL_MIN: # 如果间隔 >= 最小触发间隔（默认10秒）
                        logger.info(
                            "trigger_post_filter rule-%s_camera-%s: last_status-True same to current_status-True, "
                            "but interval passed (%dms >= %dms), Exec",
                            rule_id, camera_tag, time_since_last_trigger, self._TRIGGER_INTERVAL_MIN)
                        self._trigger_history[rule_id].append(ts_now) # 添加当前时间戳到触发记录中
                        return True # 返回True，允许触发
                    else:
                        logger.info(
                            "trigger_post_filter rule-%s_camera-%s: last_status-True same to current_status-True, "
                            "interval not passed (%dms < %dms), Not Exec",
                            rule_id, camera_tag, time_since_last_trigger, self._TRIGGER_INTERVAL_MIN)
                        return False # 返回False，不允许触发
                else:
                    # 首次检测到，允许触发
                    logger.info(
                        "trigger_post_filter rule-%s_camera-%s: first time detecting True, Exec",
                        rule_id, camera_tag)
                    self._trigger_history[rule_id].append(ts_now)
                    return True
            else:  # 条件为 False（例如，无入侵）
                logger.info(
                    "trigger_post_filter rule-%s_camera-%s: last_status-False same to current_status-False, Not Exec",
                    rule_id, camera_tag)
                return False
        else:
            # 状态发生变化，检查上次触发时间是否太近
            if (len(self._trigger_history[rule_id]) > 0 and
                    ts_now - self._trigger_history[rule_id][-1] <
                    self._TRIGGER_INTERVAL_MIN): # 如果有历史记录，且距离上次触发时间 < 最小间隔
                logger.info(
                    "trigger_post_filter rule-%s_camera-%s: status changed %s->%s, "
                    "but last_trigger_time-%d too close to current_trigger_time-%d, Not Exec",
                    rule_id, camera_tag, last_status, result, self._trigger_history[rule_id][-1], ts_now)
                return False # 记录日志：状态已变化，但触发时间太近，返回 False，不触发

            # 状态发生变化且间隔已过，允许触发
            logger.info(
                "trigger_post_filter rule-%s_camera-%s: status changed %s->%s, Exec",
                rule_id, camera_tag, last_status, result)
            if result:
                self._trigger_history[rule_id].append(ts_now)
            return True


trigger_filter = RuleTriggerFilter()
