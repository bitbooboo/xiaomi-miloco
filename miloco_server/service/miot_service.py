# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MiOT service module
"""

import logging
from typing import List, Optional

from miot.types import MIoTUserInfo, MIoTCameraInfo, MIoTDeviceInfo, MIoTManualSceneInfo

from miloco_server.proxy.miot_proxy import MiotProxy
from miloco_server.schema.trigger_schema import Action
from miloco_server.schema.miot_schema import CameraChannel, CameraImgSeq, CameraInfo, DeviceInfo, SceneInfo
from miloco_server.middleware.exceptions import (
    MiotOAuthException,
    MiotServiceException,
    ValidationException,
    BusinessException,
    ResourceNotFoundException
)
from miloco_server.utils.default_action import DefaultPresetActionManager
from miloco_server.mcp.mcp_client_manager import MCPClientManager

logger = logging.getLogger(__name__)


class MiotService:
    """MiOT service class"""

    def __init__(self, miot_proxy: MiotProxy, mcp_client_manager: MCPClientManager,
                 default_preset_action_manager: Optional[DefaultPresetActionManager] = None):
        self._miot_proxy = miot_proxy
        self._mcp_client_manager = mcp_client_manager
        self._default_preset_action_manager = default_preset_action_manager

    @property
    def miot_client(self):
        """Get the MIoTClient instance."""
        return self._miot_proxy.miot_client

    async def process_xiaomi_home_callback(self, code: str, state: str):
        """
        Process Xiaomi MiOT authorization code
        """
        try:
            logger.info(
                "process_xiaomi_home_callback code: %s, status: %s", code, state)

            await self._miot_proxy.get_miot_auth_info(code=code,
                                                              state=state)
            await self._mcp_client_manager.init_miot_mcp_clients()

        except Exception as e:
            logger.error("Failed to process Xiaomi MiOT authorization code: %s", e)
            raise MiotServiceException(f"Failed to process Xiaomi MiOT authorization code: {str(e)}") from e


    async def refresh_miot_all_info(self) -> dict:
        """
        Refresh MiOT all information
        
        Returns:
            dict: Dictionary containing result of each refresh operation
        """
        try:
            return await self._miot_proxy.refresh_miot_info()
        except Exception as e: # pylint: disable=broad-exception-caught
            # If refresh fails (e.g., no MiOT login), return default result instead of raising exception
            # This allows the system to work without requiring MiOT authentication
            logger.warning("Failed to refresh MiOT all information, returning default result: %s", e)
            return {
                "cameras": False,
                "scenes": False,
                "user_info": False,
                "devices": False
            }

    async def refresh_miot_cameras(self):
        """
        Refresh MiOT camera information
        """
        try:
            result = await self._miot_proxy.refresh_cameras()
            if not result:
                # If no MiOT account is logged in, return True to allow system access
                logger.warning("Failed to refresh MiOT cameras: No MiOT account logged in")
                return True
            return True
        except Exception as e:
            # If refresh fails (e.g., no MiOT login), return True instead of raising exception
            # This allows the system to work without requiring MiOT authentication
            logger.warning("Failed to refresh MiOT cameras, continuing without MiOT cameras: %s", e)
            return True

    async def refresh_miot_scenes(self):
        """
        Refresh MiOT scene information
        """
        try:
            result = await self._miot_proxy.refresh_scenes()
            if not result:
                # If no MiOT account is logged in, return True to allow system access
                logger.warning("Failed to refresh MiOT scenes: No MiOT account logged in")
                return True
            return True
        except Exception as e:
            # If refresh fails (e.g., no MiOT login), return True instead of raising exception
            # This allows the system to work without requiring MiOT authentication
            logger.warning("Failed to refresh MiOT scenes, continuing without MiOT scenes: %s", e)
            return True

    async def refresh_miot_user_info(self):
        """
        Refresh MiOT user information
        """
        try:
            result = await self._miot_proxy.refresh_user_info()
            if not result:
                raise MiotServiceException("Failed to refresh MiOT user info")
            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT user info: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT user info: {str(e)}") from e

    async def refresh_miot_devices(self):
        """
        Refresh MiOT device information (including HA cameras)
        """
        try:
            result = await self._miot_proxy.refresh_devices()
            if not result:
                logger.error("Failed to refresh MiOT devices: refresh_devices returned None")
                raise MiotServiceException("Failed to refresh MiOT devices: refresh operation returned no result")
            
            # 同时刷新HA摄像头
            from miloco_server.service.manager import get_manager
            manager = get_manager()
            await manager.ha_service.refresh_ha_cameras()

            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT devices: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT devices: {str(e)}") from e

    async def get_miot_login_status(self) -> dict:
        """
        Get MiOT login status

        Returns:
            dict: Dictionary containing status and login_url (if needed)

        Raises:
            MiotOAuthException: When user is not logged in or login status check fails
        """
        try:
            # Allow system login without requiring MiOT account login
            # System can enter home page after PIN login without MiOT authentication
            return {"is_logged_in": True}
            
            # Original code (commented out):
            # is_token_valid = await self._miot_proxy.check_token_valid()
            # if not is_token_valid:
            #     login_url = await self._miot_proxy.get_miot_login_url()
            #     return {"is_logged_in": False, "login_url": login_url}
            # return {"is_logged_in": True}

        except Exception as e:
            logger.error("Failed to check MiOT login status: %s", e)
            raise MiotOAuthException(f"Failed to check MiOT login status: {str(e)}") from e

    async def check_miot_auth_status(self) -> dict:
        """
        Check MiOT authorization status (for settings page)
        
        Returns:
            dict: Dictionary containing is_configured status
        """
        try:
            is_token_valid = await self._miot_proxy.check_token_valid()
            return {"is_configured": is_token_valid}
        except Exception as e:
            # If check fails, assume not configured
            logger.warning("Failed to check MiOT auth status, assuming not configured: %s", e)
            return {"is_configured": False}

    async def get_miot_login_url(self) -> dict:
        """
        Get MiOT login URL for authorization
        
        Returns:
            dict: Dictionary containing login_url
        """
        try:
            login_url = await self._miot_proxy.get_miot_login_url()
            return {"login_url": login_url}
        except Exception as e:
            logger.error("Failed to get MiOT login URL: %s", e)
            raise MiotServiceException(f"Failed to get MiOT login URL: {str(e)}") from e

    async def get_miot_user_info(self) -> MIoTUserInfo:
        """
        Get MiOT user information

        Returns:
            dict: User information dictionary

        Raises:
            ResourceNotFoundException: When unable to get user information
            ExternalServiceException: When external service call fails
        """
        try:
            user_info = await self._miot_proxy.get_user_info()

            if not user_info:
                # If no MiOT account is logged in, return a default user info
                # This allows the system to work without requiring MiOT authentication
                logger.info("No MiOT user info found, returning default user info")
                return MIoTUserInfo(
                    uid="",
                    nickname="Guest",
                    icon="",
                    union_id=""
                )

            return user_info
        except Exception as e:
            # If there's an error (e.g., 401 Unauthorized), return default user info
            # instead of raising an exception to allow system access without MiOT login
            logger.warning("Failed to get MiOT user info, returning default: %s", e)
            return MIoTUserInfo(
                uid="",
                nickname="Guest",
                icon="",
                union_id=""
            )

    async def get_miot_camera_list(self) -> List[CameraInfo]:
        """
        Get MiOT camera list (including both Xiaomi and Home Assistant cameras)

        Returns:
            List[CameraInfo]: Camera information list

        Raises:
            MiotServiceException: When getting camera list fails
        """
        try:
            # Get Xiaomi cameras
            camera_dict: dict[
                str,
                MIoTCameraInfo] | None = await self._miot_proxy.get_cameras()
            
            camera_list = []
            if camera_dict:
                camera_list = [
                    CameraInfo.model_validate(camera_info.model_dump())
                    for camera_info in camera_dict.values()
                ]

            # Get Home Assistant cameras and merge
            try:
                from miloco_server.service.manager import get_manager
                manager = get_manager()
                ha_cameras = await manager.ha_service.get_ha_cameras()
                camera_list.extend(ha_cameras)
                logger.info("Merged %d HA cameras with %d MiOT cameras", len(ha_cameras), len(camera_list) - len(ha_cameras))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to get HA cameras, continuing with MiOT cameras only: %s", e)

            return camera_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT camera list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT camera list: {str(e)}") from e

    async def get_miot_device_list(self) -> List[DeviceInfo]:
        try:
            device_dict: dict[
                str, MIoTDeviceInfo] = await self._miot_proxy.get_devices()
            
            device_list = []
            if device_dict:
                device_list = [
                    DeviceInfo.model_validate(device_info.model_dump())
                    for device_info in device_dict.values()
                ]

            # Get Home Assistant cameras and merge as devices
            try:
                from miloco_server.service.manager import get_manager
                manager = get_manager()
                ha_cameras = await manager.ha_service.get_ha_cameras()
                # CameraInfo extends DeviceInfo, so we can add them directly
                device_list.extend(ha_cameras)
                logger.info("Merged %d HA cameras with %d MiOT devices", len(ha_cameras), len(device_list) - len(ha_cameras))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to get HA cameras for device list, continuing with MiOT devices only: %s", e)

            return device_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT device list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT device list: {str(e)}") from e

    async def get_miot_cameras_img(
            self, camera_dids: list[str], vision_use_img_count: int) -> list[CameraImgSeq]:
        logger.info(
            "get_miot_cameras_img, camera_dids: %s", ", ".join(camera_dids))
        try:
            # Separate HA cameras (prefixed with "ha_") from MiOT cameras
            ha_camera_dids = [did for did in camera_dids if did.startswith("ha_")]
            miot_camera_dids = [did for did in camera_dids if not did.startswith("ha_")]

            camera_img_seqs = []

            # Get MiOT camera images
            if miot_camera_dids:
                all_camera_info: dict[str, MIoTCameraInfo] = await self._miot_proxy.get_cameras()
                if all_camera_info:
                    selected_camera_info: list[MIoTCameraInfo] = [
                        info for info in all_camera_info.values() if (info.did in miot_camera_dids)
                    ]

                    camera_channels: list[CameraChannel] = []
                    for camera_info in selected_camera_info:
                        for channel in range(camera_info.channel_count or 1):
                            camera_channels.append(
                                CameraChannel(did=camera_info.did, channel=channel))

                    for camera_channel in camera_channels:
                        camera_img_seq = self._miot_proxy.get_recent_camera_img(
                            camera_channel.did, camera_channel.channel, vision_use_img_count)
                        if not camera_img_seq:
                            logger.error(
                                "get_miot_cameras_img, get recent camera img failed, did: %s, channel: %s",
                                camera_channel.did, camera_channel.channel
                            )
                            continue

                        camera_img_seqs.append(camera_img_seq)

            # Get HA camera images
            if ha_camera_dids:
                try:
                    from miloco_server.service.manager import get_manager
                    manager = get_manager()
                    ha_img_seqs = await manager.ha_service.get_ha_cameras_img(ha_camera_dids, vision_use_img_count)
                    camera_img_seqs.extend(ha_img_seqs)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Failed to get HA camera images: %s", e)

            return camera_img_seqs
        except Exception as e:
            logger.error("Failed to get MiOT camera images: %s", e)
            raise MiotServiceException(f"Failed to get MiOT camera images: {str(e)}") from e

    async def get_miot_scene_list(self) -> List[SceneInfo]:
        """
        Get all MiOT scenes

        Returns:
            dict: Scene information dictionary

        Raises:
            MiotServiceException: When getting scenes fails
        """
        try:
            scenes: dict[
                str,
                MIoTManualSceneInfo] | None = await self._miot_proxy.get_all_scenes(
                )

            if scenes is None:
                raise MiotServiceException("Failed to get MiOT scene list")

            scene_info_list = [
                SceneInfo(scene_id=scene_info.scene_id,
                          scene_name=scene_info.scene_name)
                for scene_info in scenes.values()
            ]

            return scene_info_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT scene list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT scene list: {str(e)}") from e

    async def send_notify(self, notify: str) -> None:
        """Send notification"""
        try:
            notify_id = await self._miot_proxy.get_miot_app_notify_id(notify)
            if not notify_id:
                raise ValidationException("MiOT app notification content is inappropriate, please re-enter")
            result = await self._miot_proxy.send_app_notify(notify_id)
            if not result:
                raise BusinessException("Failed to send notification")
        except Exception as e:
            logger.error("Failed to send notification: %s", str(e))
            raise BusinessException(f"Failed to send notification: {str(e)}") from e

    async def start_video_stream(self, camera_id: str, channel: int, callback):
        """
        Start video stream (business layer method)
        Note: HA cameras are already filtered at the controller layer.
        This method only handles MIoT cameras.

        Args:
            camera_id: Camera device ID (MIoT cameras only, HA cameras filtered at controller layer)
            channel: Channel number
            callback: Video data callback function

        Raises:
            MiotServiceException: When startup fails
        """
        try:
            logger.info("Starting video stream: camera_id=%s, channel=%s", camera_id, channel)
            
            # MIoT camera video stream
            if callback:
                await self._miot_proxy.start_camera_raw_stream(
                    camera_id, channel, callback)
            else:
                logger.info("No callback function, only recording startup request: camera_id=%s", camera_id)
        except Exception as e:
            logger.error("Failed to start video stream: %s", e)
            raise MiotServiceException(f"Failed to start video stream: {str(e)}") from e

    async def stop_video_stream(self, camera_id: str, channel: int):
        """
        Stop video stream (business layer method)
        Supports both MIoT cameras and Home Assistant cameras

        Args:
            camera_id: Camera device ID (MIoT cameras or HA cameras with "ha_" prefix)
            channel: Channel number

        Raises:
            MiotServiceException: When stopping fails
        """
        try:
            logger.info("Stopping video stream: camera_id=%s", camera_id)
            
            # Check if this is a Home Assistant camera
            if camera_id.startswith("ha_"):
                # HA cameras don't have active video streams to stop
                logger.info("HA camera %s doesn't have active video stream to stop", camera_id)
                return
            
            # MIoT camera video stream
            await self._miot_proxy.stop_camera_raw_stream(camera_id, channel)
            logger.info("Video stream stopped successfully: camera_id=%s", camera_id)
        except Exception as e:
            logger.error("Failed to stop video stream: %s", e)
            raise MiotServiceException(f"Failed to stop video stream: {str(e)}") from e

    async def get_miot_scene_actions(self) -> List[Action]:
        """
        Get MiOT scene action list

        Returns:
            dict: MiOT scene action dictionary

        Raises:
            MiotServiceException: When getting scene actions fails
        """
        try:
            if not self._default_preset_action_manager:
                logger.error("DefaultPresetActionManager not initialized")
                raise MiotServiceException("DefaultPresetActionManager not initialized")

            actions = await self._default_preset_action_manager.get_miot_scene_actions()

            return list(actions.values())
        except Exception as e:
            logger.error("Failed to get MiOT scene action list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT scene action list: {str(e)}") from e
