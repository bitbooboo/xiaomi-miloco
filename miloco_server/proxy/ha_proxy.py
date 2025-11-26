# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Home Assistant proxy module for handling Home Assistant related operations."""

import asyncio
import json
import logging
from typing import Optional, Dict

from pydantic_core import to_jsonable_python
from miot.ha_api import HAAutomationInfo, HAHttpClient, HAStateInfo

from miloco_server.dao.kv_dao import AuthConfigKeys, KVDao, DeviceInfoKeys
from miloco_server.schema.miot_schema import HAConfig, CameraInfo, CameraImgSeq
from miloco_server.utils.ha_camera_vision_handler import HACameraVisionHandler
from miloco_server.config import CAMERA_CONFIG


logger = logging.getLogger(__name__)

class HAProxy:
    """Home Assistant proxy class responsible for handling Home Assistant related operations."""
    def __init__(self, kv_dao: KVDao):
        self._kv_dao = kv_dao
        self._ha_rest_api: Optional[HAHttpClient] = None
        self._automations: dict[str, HAAutomationInfo] = {}
        self._cameras: dict[str, HAStateInfo] = {} # 存储 Home Assistant 摄像头状态信息，key 为实体 ID
        self._camera_img_managers: dict[str, HACameraVisionHandler] = {} # 存储每个摄像头的图像处理器实例，用于管理图像队列和快照
        self._camera_img_cache_max_size: int = CAMERA_CONFIG["camera_img_cache_max_size"] # 图像缓存的最大数量（队列最大长度）
        self._camera_img_cache_ttl: int = max(1, int(CAMERA_CONFIG["frame_interval"] * self._camera_img_cache_max_size / 1000 * 2)) # 图像缓存的生存时间（秒）
        self._snapshot_interval: int = 30  # 快照采集间隔（秒），用于定期获取摄像头快照
        self.init_ha_info_dict()

    @property
    def ha_client(self) -> Optional[HAHttpClient]:
        return self._ha_rest_api

    def init_ha_info_dict(self):
        """Initialize HA related information dictionary"""
        miot_ha_base_url = self._kv_dao.get(AuthConfigKeys.MIOT_HA_BASE_URL_KEY)
        miot_ha_token = self._kv_dao.get(AuthConfigKeys.MIOT_HA_TOKEN_KEY)
        if miot_ha_base_url and miot_ha_token:
            self._ha_rest_api = HAHttpClient(miot_ha_base_url, miot_ha_token)
        else:
            self._ha_rest_api = None

        automations_str = self._kv_dao.get(DeviceInfoKeys.HA_AUTOMATIONS_KEY)
        if automations_str:
            self._automations: dict[str, HAAutomationInfo] = {
                automation_id: HAAutomationInfo.model_validate(automation_info)
                for automation_id, automation_info in json.loads(automations_str).items()}
        else:
            self._automations = {}

        # 初始化HA摄像头信息
        cameras_str = self._kv_dao.get(DeviceInfoKeys.HA_CAMERAS_KEY)
        if cameras_str:
            cameras_dict = json.loads(cameras_str)
            self._cameras = {}
            for camera_id, camera_info in cameras_dict.items():
                self._cameras[camera_id] = HAStateInfo.model_validate(camera_info)
        else:
            self._cameras = {}

    async def set_ha_config(self, miot_ha_base_url: str, miot_ha_token: str):
        """Set Home Assistant configuration"""
        if not await HAHttpClient.validate_async(miot_ha_base_url, miot_ha_token):
            raise ValueError("Miot ha rest api is not valid, please check the base url and token")

        self._kv_dao.set(AuthConfigKeys.MIOT_HA_BASE_URL_KEY, miot_ha_base_url)
        self._kv_dao.set(AuthConfigKeys.MIOT_HA_TOKEN_KEY, miot_ha_token)
        self._ha_rest_api = HAHttpClient(miot_ha_base_url, miot_ha_token)
        await self.refresh_ha_automations()
        await self.refresh_cameras()

    def get_ha_config(self) -> HAConfig | None:
        """Get Home Assistant configuration"""
        base_url = self._kv_dao.get(AuthConfigKeys.MIOT_HA_BASE_URL_KEY)
        token = self._kv_dao.get(AuthConfigKeys.MIOT_HA_TOKEN_KEY)
        if base_url and token:
            return HAConfig(
                base_url=base_url,
                token=token
            )
        else:
            return None

    async def _fetch_and_save_automations(self) -> dict[str, HAAutomationInfo] | None:
        """Fetch automation information from Home Assistant and save to cache and KV storage"""
        if not self._ha_rest_api:
            logger.warning("Miot ha rest api is not initialized")
            return None
        try:
            automations = await self._ha_rest_api.get_automations_async()
            self._automations = automations
            self._kv_dao.set(DeviceInfoKeys.HA_AUTOMATIONS_KEY, json.dumps(to_jsonable_python(automations)))
            return automations
        except (ConnectionError, TimeoutError, ValueError, RuntimeError) as e:
            logger.warning("Failed to fetch automations: %s", e)
            return None


    async def get_automations(self) -> dict[str, HAAutomationInfo] | None:
        """Get automation information, return from cache first, fetch from HA if cache is empty"""
        if self._automations:
            return self._automations
        return await self._fetch_and_save_automations()

    async def refresh_ha_automations(self) -> bool:
        """Force refresh Home Assistant automation information"""
        automations = await self._fetch_and_save_automations()
        if automations:
            logger.info("Successfully refreshed HA automations: %s", automations)
            return True
        else:
            logger.warning("Failed to refresh HA automations")
            return False

    async def trigger_automation(self, automation_id: str):
        """Trigger specified automation"""
        if self._ha_rest_api:
            try:
                return await self._ha_rest_api.trigger_automation_async(automation_id)
            except (ConnectionError, TimeoutError, ValueError, RuntimeError) as e:
                logger.warning("Failed to trigger automation %s: %s", automation_id, e)
                return None
        else:
            logger.warning("Miot ha rest api is not initialized")
            return None

    async def _fetch_and_save_cameras(self) -> dict[str, HAStateInfo] | None:
        # 从HA获取摄像头信息并保存到缓存和KV存储
        if not self._ha_rest_api:
            logger.warning("Miot ha rest api is not initialized")
            return None
        try:
            cameras = await self._ha_rest_api.get_cameras_async()
            
            # 创建或更新摄像头管理器
            for entity_id, state_info in cameras.items():
                if entity_id not in self._camera_img_managers:
                    await self._create_camera_img_manager(entity_id, state_info)
                else:
                    # 更新摄像头信息
                    camera_info = self._create_camera_info_from_state(entity_id, state_info)
                    await self._camera_img_managers[entity_id].update_camera_info(camera_info)
                    if camera_info.online and not self._camera_img_managers[entity_id]._running:
                        await self._camera_img_managers[entity_id].start()
                    elif not camera_info.online and self._camera_img_managers[entity_id]._running:
                        await self._camera_img_managers[entity_id].stop()
            
            # 移除不再存在的摄像头管理器
            for entity_id in list(self._camera_img_managers.keys()):
                if entity_id not in cameras:
                    await self._camera_img_managers[entity_id].destroy()
                    del self._camera_img_managers[entity_id]
            
            self._cameras = cameras
            self._kv_dao.set(DeviceInfoKeys.HA_CAMERAS_KEY, json.dumps(to_jsonable_python(cameras)))
            return cameras
        except (ConnectionError, TimeoutError, ValueError, RuntimeError) as e:
            logger.warning("Failed to fetch cameras: %s", e)
            return None

    async def get_cameras(self) -> dict[str, HAStateInfo] | None:
        # 获取摄像头信息，优先从缓存返回，如果缓存为空则从HA获取
        if self._cameras:
            return self._cameras
        return await self._fetch_and_save_cameras()

    async def refresh_cameras(self) -> bool:
        # 强制刷新HA摄像头信息
        cameras = await self._fetch_and_save_cameras()
        if cameras:
            logger.info("Successfully refreshed HA cameras: %s", cameras)
            return True
        else:
            logger.warning("Failed to refresh HA cameras")
            return False

    def _create_camera_info_from_state(self, entity_id: str, state_info: HAStateInfo) -> CameraInfo:
        """从HAStateInfo创建CameraInfo对象"""
        friendly_name = state_info.attributes.get("friendly_name", entity_id)
        online = state_info.state not in ["unavailable", "unknown"]
        icon_url = "/assets/images/carmera-default.png"
        
        return CameraInfo(
            did=f"ha_{entity_id}",  # 添加"ha_"前缀以区分MIoT摄像头
            name=friendly_name,
            online=online,
            model="Home Assistant Camera",
            icon=icon_url,
            home_name="Home Assistant",
            room_name="",
            channel_count=1,
            camera_status="idle" if online else "unavailable",
            is_set_pincode=0  # HA 摄像头没有密码
        )

    async def _create_camera_img_manager(self, entity_id: str, state_info: HAStateInfo) -> HACameraVisionHandler | None:
        # 为HA摄像头创建图像管理器
        if not self._ha_rest_api:
            logger.error("HA REST API is not initialized")
            return None
        
        try:
            camera_info = self._create_camera_info_from_state(entity_id, state_info)
            
            camera_img_manager = HACameraVisionHandler(
                camera_info=camera_info,
                ha_client=self._ha_rest_api,
                entity_id=entity_id,
                max_size=self._camera_img_cache_max_size,
                ttl=self._camera_img_cache_ttl,
                snapshot_interval=self._snapshot_interval
            )
            
            if camera_info.online:
                await camera_img_manager.start()
            
            self._camera_img_managers[entity_id] = camera_img_manager
            return camera_img_manager
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to create camera img manager for %s: %s", entity_id, e)
            return None

    async def get_recent_camera_img(self, entity_id: str, channel: int, recent_count: int) -> CameraImgSeq | None:
        """
        获取最近的摄像头图像
        按需捕获：仅在LLM确定需要图像时才捕获
        """
        # 如果摄像头管理器不存在，先尝试创建它
        if entity_id not in self._camera_img_managers:
            logger.info("Camera %s not found in managers, attempting to create manager", entity_id)
            # 尝试获取摄像头状态并创建管理器
            if self._ha_rest_api:
                try:
                    cameras = await self._ha_rest_api.get_cameras_async(force_update=False)
                    if cameras and entity_id in cameras:
                        state_info = cameras[entity_id]
                        await self._create_camera_img_manager(entity_id, state_info)
                        logger.info("Successfully created camera manager for %s", entity_id)
                    else:
                        logger.warning("Camera %s not found in HA cameras list", entity_id)
                        return None
                except Exception as e:
                    logger.error("Failed to create camera manager for %s: %s", entity_id, e)
                    return None
            else:
                logger.warning("HA REST API is not initialized, cannot create camera manager for %s", entity_id)
                return None
        
        if recent_count > self._camera_img_cache_max_size or recent_count <= 0:
            logger.warning(
                "recent_count is out of range, entity_id: %s, channel: %s, "
                "recent_count: %s, camera_img_cache_max_size: %s",
                entity_id, channel, recent_count, self._camera_img_cache_max_size
            )
        
        camera_handler = self._camera_img_managers[entity_id]
        # get_recents_camera_img 现在是异步的，如果队列为空将按需捕获
        return await camera_handler.get_recents_camera_img(channel, recent_count)
