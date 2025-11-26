# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger rule service module
"""

import logging
from typing import List, Optional

from fastapi import WebSocket
from miot.types import MIoTCameraInfo
from schema.mcp_schema import MCPClientStatus, choose_mcp_list

from miloco_server import actor_system
from miloco_server.dao.trigger_dao import TriggerRuleDAO
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.mcp.mcp_client_manager import MCPClientManager
from miloco_server.middleware.exceptions import (
    ConflictException,
    ValidationException,
    ResourceNotFoundException,
    BusinessException,
)
from miloco_server.proxy.miot_proxy import MiotProxy
from miloco_server.schema.miot_schema import choose_camera_list
from miloco_server.schema.trigger_log_schema import TriggerRuleLog
from miloco_server.schema.trigger_schema import (
    Action, ExecuteInfoDetail, Notify, TriggerRule, TriggerRuleDetail)
from miloco_server.service.trigger_rule_runner import TriggerRuleRunner

from service import trigger_rule_dynamic_executor_cache
from service.trigger_rule_dynamic_executor import RegisterWebSocket

logger = logging.getLogger(__name__)


class TriggerRuleService:
    """Trigger rule service class"""

    def __init__(self, trigger_rule_dao: TriggerRuleDAO,
                 trigger_rule_log_dao: TriggerRuleLogDAO,
                 trigger_rule_runner: TriggerRuleRunner,
                 miot_proxy: MiotProxy,
                 mcp_client_manager: MCPClientManager):
        self._trigger_rule_dao = trigger_rule_dao
        self._trigger_rule_log_dao = trigger_rule_log_dao
        self._trigger_rule_runner = trigger_rule_runner
        self._miot_proxy = miot_proxy
        self._mcp_client_manager = mcp_client_manager

    async def _get_all_valid_camera_dids(self) -> list[str]:
        """
        获取所有有效的摄像头设备ID（包括 MIoT 和 Home Assistant）

        Returns:
            list[str]: 返回字符串列表（摄像头设备ID列表）
        """
        # 获取MIoT摄像头ID
        valid_cameras = await self._miot_proxy.get_camera_dids()
        
        # 获取HA摄像头ID
        try:
            from miloco_server.service.manager import get_manager
            manager = get_manager()
            ha_cameras = await manager.ha_service.get_ha_cameras()
            ha_camera_dids = [camera.did for camera in ha_cameras]
            valid_cameras.extend(ha_camera_dids) # 将HA摄像头ID添加到有效摄像头ID列表中
            logger.debug("Merged %d HA camera IDs with %d MIoT camera IDs", 
                        len(ha_camera_dids), len(valid_cameras) - len(ha_camera_dids)) # 记录日志：合并了HA摄像头ID和MIoT摄像头ID
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to get HA cameras for validation, continuing with MIoT cameras only: %s", e) # 记录日志：获取HA摄像头失败，继续使用MIoT摄像头
        
        return valid_cameras # 返回有效摄像头ID列表

    async def create_trigger_rule(self, trigger_rule: TriggerRule) -> str:
        """
        Create trigger rule

        Args:
            trigger_rule: Trigger rule object (without ID, system auto-generates on creation)

        Returns:
            str: Created rule ID

        Raises:
            ConflictException: When rule name already exists
            ValidationException: When camera device ID is invalid
            BusinessException: When creation fails
        """
        # Check if rule name already exists
        if self._trigger_rule_dao.exists_by_name(trigger_rule.name):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")

        # Validate if camera device IDs are valid (including both MIoT and HA cameras)
        valid_cameras = await self._get_all_valid_camera_dids()
        invalid_dids = [
            did for did in trigger_rule.cameras if did not in valid_cameras
        ]
        if invalid_dids:
            ids = ", ".join(invalid_dids)
            raise ValidationException(f"Invalid camera device IDs: {ids}")

        # Validate notification for content filtering
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        # Create rule object
        rule_id = self._trigger_rule_dao.create(trigger_rule)

        if not rule_id:
            logger.error("Trigger rule creation failed")
            raise BusinessException("Failed to create trigger rule")

        trigger_rule.id = rule_id
        self._trigger_rule_runner.add_trigger_rule(trigger_rule)

        logger.info("Trigger rule created successfully: %s", rule_id)
        return rule_id

    async def get_trigger_rule(self, rule_id: str) -> TriggerRuleDetail:
        """
        Get trigger rule details

        Args:
            rule_id: Rule ID (UUID)

        Returns:
            TriggerRule: Trigger rule object

        Raises:
            ResourceNotFoundException: When rule does not exist
        """
        logger.info("Getting trigger rule details: id=%s", rule_id)

        trigger_rule = self._trigger_rule_dao.get_by_id(rule_id)

        if not trigger_rule:
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")

        trigger_rule_response = await self.make_trigger_rule_detail(trigger_rule)

        logger.info("Trigger rule retrieved successfully: %s", rule_id)
        return trigger_rule_response

    async def get_all_trigger_rules(self, enabled_only: bool = False) -> List[TriggerRuleDetail]:
        """
        Get all trigger rules

        Args:
            enabled_only: Whether to return only enabled rules

        Returns:
            List[TriggerRuleDetail]: List of trigger rule objects
        """
        logger.info("Getting all trigger rules: enabled_only=%s", enabled_only)

        trigger_rules: List[TriggerRule] = self._trigger_rule_dao.get_all(
            enabled_only)

        if not trigger_rules:
            return []

        trigger_rule_responses = await self.make_trigger_rule_details(trigger_rules)

        logger.info("Retrieved %d trigger rules", len(trigger_rule_responses))
        return trigger_rule_responses

    async def update_trigger_rule(self, trigger_rule: TriggerRule) -> bool:
        """
        Update trigger rule

        Args:
            trigger_rule: Trigger rule object (with ID)

        Returns:
            bool: True if update successful, False otherwise

        Raises:
            ResourceNotFoundException: When rule does not exist
            ConflictException: When rule name already exists
            ValidationException: When camera device ID is invalid
        """
        logger.info("Updating trigger rule: id=%s", trigger_rule.id)
        if not trigger_rule.id:
            raise ValidationException("Rule ID is required")

        # Check if rule exists
        if not self._trigger_rule_dao.exists(trigger_rule.id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{trigger_rule.id}' not found")

        # Check if rule name already exists (excluding current rule)
        if self._trigger_rule_dao.exists_by_name(trigger_rule.name, trigger_rule.id):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")

        # Validate if camera device IDs are valid (including both MIoT and HA cameras)
        valid_cameras = await self._get_all_valid_camera_dids()
        invalid_dids = [
            did for did in trigger_rule.cameras if did not in valid_cameras
        ]
        if invalid_dids:
            ids = ", ".join(invalid_dids)
            raise ValidationException(f"Invalid camera device IDs: {ids}")

        # Validate notification for content filtering
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        success = self._trigger_rule_dao.update(trigger_rule)

        if success:
            self._trigger_rule_runner.add_trigger_rule(trigger_rule)
            logger.info("Trigger rule updated successfully: %s", trigger_rule.id)
        else:
            logger.error("Failed to update trigger rule: %s", trigger_rule.id)

        return success

    async def delete_trigger_rule(self, rule_id: str) -> bool:
        """
        Delete trigger rule

        Args:
            rule_id: Rule ID (UUID)

        Returns:
            bool: True if deletion successful, False otherwise

        Raises:
            ResourceNotFoundException: When rule does not exist
            BusinessException: When deletion fails
        """
        logger.info("Deleting trigger rule: id=%s", rule_id)

        # Check if rule exists
        if not self._trigger_rule_dao.exists(rule_id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")

        # Delete rule
        success = self._trigger_rule_dao.delete(rule_id)

        if success:
            self._trigger_rule_runner.remove_trigger_rule(rule_id)
            logger.info("Trigger rule deleted successfully: %s", rule_id)
        else:
            logger.error("Failed to delete trigger rule: %s", rule_id)

        return success

    async def get_trigger_rule_logs(self, limit: int = 10) -> tuple[List[TriggerRuleLog], int]:
        """
        Get trigger rule execution logs

        Args:
            limit: Number of logs to retrieve

        Returns:
            tuple[List[TriggerRuleLog], int]: Log list and total count
        """
        logger.info("Getting trigger rule logs: limit=%d", limit)

        rule_logs = self._trigger_rule_log_dao.get_all(limit=limit)
        total_items = self._trigger_rule_log_dao.count_all()

        logger.info("Retrieved %d trigger rule logs", len(rule_logs))
        return rule_logs, total_items

    async def _check_notify(self, notify: Optional[Notify]):
        """Check notification content for filtering"""
        if not notify:
            return

        if not notify.content:
            raise ValidationException("Notification content is required")

        notify_id = await self._miot_proxy.get_miot_app_notify_id(notify.content)
        if not notify_id:
            raise ValidationException("Notification content is inappropriate, please re-enter")
        notify.id = notify_id


    async def make_trigger_rule_details(
            self, trigger_rules: List[TriggerRule]) -> List[TriggerRuleDetail]:
        """Generate trigger rule response"""
        camera_info_dict = await self._miot_proxy.get_cameras()
        all_mcp_list = await self._mcp_client_manager.get_all_clients_status()
        return [
            self._build_trigger_rule_detail(trigger_rule, camera_info_dict, all_mcp_list)
            for trigger_rule in trigger_rules
        ]


    async def make_trigger_rule_detail(self, trigger_rule: TriggerRule) -> TriggerRuleDetail:
        """Generate trigger rule response"""
        camera_info_dict = await self._miot_proxy.get_cameras()
        all_mcp_list = await self._mcp_client_manager.get_all_clients_status()
        return self._build_trigger_rule_detail(trigger_rule, camera_info_dict, all_mcp_list)

    def _build_trigger_rule_detail(
        self,
        trigger_rule: TriggerRule,
        camera_info_dict: dict[str, MIoTCameraInfo],
        all_mcp_list: List[MCPClientStatus],
    ) -> TriggerRuleDetail:
        """Generate trigger rule response"""
        camera_list = choose_camera_list(trigger_rule.cameras, camera_info_dict)
        choosed_mcp_list = choose_mcp_list(trigger_rule.execute_info.mcp_list, all_mcp_list)
        execute_info = ExecuteInfoDetail.from_execute_info(
            trigger_rule.execute_info, choosed_mcp_list)
        return TriggerRuleDetail.from_trigger_rule(
            trigger_rule=trigger_rule, cameras=camera_list, execute_info=execute_info)

    async def send_dynamic_execute_log(self, log_id: str, websocket: WebSocket) -> None:
        """Send dynamic execute log"""
        execute_result, rule_id = self._trigger_rule_log_dao.get_execute_result(log_id)
        if (execute_result and
            execute_result.ai_recommend_dynamic_execute_result and
            execute_result.ai_recommend_dynamic_execute_result.chat_history_session):
            for session in execute_result.ai_recommend_dynamic_execute_result.chat_history_session.data:
                await websocket.send_text(session.model_dump_json())
        elif rule_id:
            trigger_rule_dynamic_executor = trigger_rule_dynamic_executor_cache.get(rule_id)
            if trigger_rule_dynamic_executor:
                register_web_socket = RegisterWebSocket(websocket)
                actor_system.tell(trigger_rule_dynamic_executor, register_web_socket)
                return
            else:
                raise ResourceNotFoundException(
                    f"Trigger rule dynamic executor not found for log ID: {log_id}")
        else:
            raise ResourceNotFoundException(
                f"Trigger rule log not found for log ID: {log_id}")

    async def execute_actions(self, actions: list[Action]) -> list[bool]:
        """Execute actions"""
        results: list[bool] = []
        for action in actions:
            result: bool = await self._trigger_rule_runner.execute_action(action)
            results.append(result)
        return results
