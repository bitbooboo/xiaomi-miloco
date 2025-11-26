# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Home Assistant service module
"""

import logging
from typing import List, Optional

from miloco_server.mcp.mcp_client_manager import MCPClientManager
from miloco_server.middleware.exceptions import (
    HaServiceException,
    ValidationException,
    BusinessException
)
from miloco_server.proxy.ha_proxy import HAProxy
from miloco_server.schema.miot_schema import HAConfig, CameraInfo, CameraImgSeq
from miloco_server.schema.trigger_schema import Action
from miloco_server.utils.default_action import DefaultPresetActionManager

from miot.types import HAAutomationInfo

logger = logging.getLogger(__name__)


class HaService:
    """Home Assistant service class"""

    def __init__(
        self,
        ha_proxy: HAProxy,
        mcp_client_manager: MCPClientManager,
        default_preset_action_manager: Optional[DefaultPresetActionManager] = None
    ):
        self._ha_proxy = ha_proxy
        self._mcp_client_manager = mcp_client_manager
        self._default_preset_action_manager = default_preset_action_manager

    @property
    def ha_client(self) -> Optional[object]:
        """Get the HAHttpClient instance."""
        return self._ha_proxy.ha_client

    async def refresh_ha_automations(self):
        """
        Refresh Home Assistant automation information
        """
        try:
            await self._ha_proxy.refresh_ha_automations()
        except Exception as e:
            logger.error("Failed to refresh Home Assistant automations: %s", e)
            raise HaServiceException(f"Failed to refresh Home Assistant automations: {str(e)}") from e

    async def set_ha_config(self, ha_config: HAConfig):
        try:
            if not ha_config.base_url or not ha_config.base_url.strip():
                raise ValidationException("Home Assistant base URL cannot be empty")
            if not ha_config.token or not ha_config.token.strip():
                raise ValidationException("Home Assistant access token cannot be empty")

            await self._ha_proxy.set_ha_config(ha_config.base_url,
                                                    ha_config.token.strip())

            await self._mcp_client_manager.init_ha_automations()
            logger.info("Home Assistant configuration saved successfully: base_url=%s", ha_config.base_url)

        except ValidationException:
            raise
        except Exception as e:
            logger.error("Exception occurred while saving Home Assistant configuration: %s", e)
            raise BusinessException(f"Failed to save Home Assistant configuration: {str(e)}") from e

    async def get_ha_config(self) -> HAConfig | None:
        try:
            ha_config = self._ha_proxy.get_ha_config()
            if not ha_config:
                logger.warning("Home Assistant configuration not set")
            return ha_config
        except Exception as e:
            logger.error("Exception occurred while getting Home Assistant configuration: %s", e)
            raise HaServiceException(f"Failed to get Home Assistant configuration: {str(e)}") from e

    async def get_ha_automations(self) -> list[HAAutomationInfo]:
        try:
            automations = await self._ha_proxy.get_automations()
            if automations is None:
                logger.warning("Failed to get Home Assistant automation list")
                raise HaServiceException("Failed to get Home Assistant automation list")
            logger.info(
                "Successfully retrieved Home Assistant automation list - count: %d", len(automations.values()))
            return list(automations.values())

        except Exception as e:
            logger.error("Failed to get Home Assistant automation list: %s", e)
            raise HaServiceException(
                f"Failed to get Home Assistant automation list: {str(e)}") from e

    async def get_ha_automation_actions(self) -> List[Action]:
        """
        Get Home Assistant automation action list

        Returns:
            List[Action]: Home Assistant automation action list

        Raises:
            HaServiceException: When getting automation actions fails
        """
        try:
            if not self._default_preset_action_manager:
                logger.error("DefaultPresetActionManager not initialized")
                raise HaServiceException("DefaultPresetActionManager not initialized")

            actions = await self._default_preset_action_manager.get_ha_automation_actions()

            return list(actions.values())
        except Exception as e:
            logger.error("Failed to get Home Assistant automation action list: %s", e)
            raise HaServiceException(f"Failed to get Home Assistant automation action list: {str(e)}") from e

    async def get_ha_cameras(self) -> List[CameraInfo]:
        """
        获取HA摄像头列表
        Returns:
            List[CameraInfo]: HA摄像头信息列表
            如果HA未配置或获取摄像头失败，返回空列表
        """
        try:
            # 检查HA是否已配置
            if not self._ha_proxy.ha_client:
                logger.debug("Home Assistant is not configured, returning empty camera list")
                return []

            cameras_dict = await self._ha_proxy.get_cameras()
            if cameras_dict is None:
                logger.warning("Failed to get Home Assistant camera list")
                return []

            camera_list = []
            ha_config = self._ha_proxy.get_ha_config()
            base_url = ha_config.base_url if ha_config else ""
            
            for entity_id, state_info in cameras_dict.items():
                # 将HAStateInfo转换为CameraInfo
                camera_info = self._ha_proxy._create_camera_info_from_state(entity_id, state_info)
                camera_list.append(camera_info)

            logger.info(
                "Successfully retrieved Home Assistant camera list - count: %d", len(camera_list))
            return camera_list

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to get Home Assistant camera list: %s", e)
            # 返回空列表而不是抛出异常，以避免破坏设备列表
            return []

    async def refresh_ha_cameras(self) -> bool:
        """
        刷新 Home Assistant 摄像头信息

        Returns:
            bool: 刷新成功返回 True，否则返回 False

        Raises:
            HaServiceException: 刷新失败时抛出
        """
        try:
            result = await self._ha_proxy.refresh_cameras()
            if result:
                logger.info("Successfully refreshed Home Assistant cameras")
            else:
                logger.warning("Failed to refresh Home Assistant cameras")
            return result
        except Exception as e:
            logger.error("Failed to refresh Home Assistant cameras: %s", e)
            raise HaServiceException(f"Failed to refresh Home Assistant cameras: {str(e)}") from e

    async def get_ha_cameras_img(
            self, camera_dids: list[str], vision_use_img_count: int) -> list[CameraImgSeq]:
        """
        获取 Home Assistant 摄像头图像

        Args:
            camera_dids: 摄像头设备 ID 列表（带 "ha_" 前缀）
            vision_use_img_count: 每个摄像头要获取的图像数量

        Returns:
            List[CameraImgSeq]: 摄像头图像序列列表
        """
        logger.info(
            "get_ha_cameras_img, camera_dids: %s", ", ".join(camera_dids))
        try:
            camera_img_seqs = []
            
            # 从代理获取摄像头处理器
            for camera_did in camera_dids:
                # 移除 "ha_" 前缀以获取 entity_id
                if not camera_did.startswith("ha_"):
                    logger.warning("Invalid HA camera did format: %s", camera_did)
                    continue
                
                entity_id = camera_did[3:]  # 移除 "ha_" 前缀
                # get_recent_camera_img 现在是异步的，当 LLM 需要图像时按需捕获
                camera_img_seq = await self._ha_proxy.get_recent_camera_img(entity_id, 0, vision_use_img_count)
                if camera_img_seq:
                    camera_img_seqs.append(camera_img_seq)
                else:
                    logger.warning(
                        "get_ha_cameras_img, get recent camera img failed, entity_id: %s",
                        entity_id
                    )

            return camera_img_seqs
        except Exception as e:
            logger.error("Failed to get HA camera images: %s", e)
            raise HaServiceException(f"Failed to get HA camera images: {str(e)}") from e
