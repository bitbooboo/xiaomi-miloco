# -*- coding: utf-8 -*-
# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
Home Assistant Rest API client.
"""
# pylint: disable=too-many-arguments, too-many-positional-arguments
# pylint: disable=too-many-instance-attributes
import asyncio
from datetime import datetime
import logging
from typing import Dict, List, Optional
import aiohttp

from .types import HAAutomationInfo, HAStateInfo

from .oauth2 import BaseOAuth2Client

_LOGGER = logging.getLogger(__name__)

HA_HTTP_API_TIMEOUT: int = 30

SUPPORT_ENTITY_CLASSES = {
    "light": {
        "name": "Light"
    }
}


class HAOAuth2Client(BaseOAuth2Client):
    """OAuth2 agent url, default: product env."""

    async def revoke_token_async(self, refresh_token: str) -> None:
        """Revoke access token.

        Args:
            refresh_token (str): Refresh token.

        Returns:
            bool: True if success, False otherwise.
        """
        if not refresh_token:
            raise ValueError("invalid refresh_token")

        http_res = await self._session.post(
            url=f"{self._base_url}/auth/revoke",
            data={
                "token": refresh_token,
                "action": "revoke"
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=self._AUTH_API_TIMEOUT
        )
        if http_res.status != 200:
            raise ValueError(f"revoke token failed, {http_res.status}")


class HAHttpClient:
    """
    Home Assistant http client.
    Successful calls will return status code 200 or 201. Other status codes that can return are:
    400 (Bad Request)
    401 (Unauthorized)
    404 (Not Found)
    405 (Method Not Allowed)
    """
    _main_loop: asyncio.AbstractEventLoop
    _session: aiohttp.ClientSession
    _base_url: str
    _token: str

    _states_buffer: Dict[str, HAStateInfo]

    def __init__(
        self, base_url: str, access_token: str,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        """Initialize."""
        self._main_loop = loop or asyncio.get_running_loop()
        if not base_url or not access_token:
            raise ValueError("invalid init params")
        self._base_url = base_url
        self._token = access_token

        self._states_buffer = {}

        self._session = aiohttp.ClientSession(loop=self._main_loop)

    async def deinit_async(self) -> None:
        """Deinit the client."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __api_get_async(
        self, url_path: str, params: Dict,
        timeout: int = HA_HTTP_API_TIMEOUT
    ) -> Dict:
        """Get data from ha api with http get."""
        http_res = await self._session.get(
            url=f"{self._base_url}{url_path}",
            params=params,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}"
            },
            timeout=aiohttp.ClientTimeout(total=timeout))
        if http_res.status == 401:
            raise TypeError("ha api get failed, unauthorized(401)")
        if http_res.status not in [200, 201]:
            raise TypeError(f"ha api get failed, {http_res.status}, {url_path}, {params}")
        return await http_res.json()

    async def __api_post_async(
        self, url_path: str, data: Dict,
        timeout: int = HA_HTTP_API_TIMEOUT
    ) -> Dict:
        """Get data from ha api with http post."""
        http_res = await self._session.post(
            url=f"{self._base_url}{url_path}",
            json=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}"
            },
            timeout=aiohttp.ClientTimeout(total=timeout))
        if http_res.status == 401:
            raise TypeError("ha api get failed, unauthorized(401)")
        if http_res.status not in [200, 201]:
            raise TypeError(f"ha api post failed, {http_res.status}, {url_path}, {data}")
        return await http_res.json()

    async def update_info_async(self, token: str) -> None:
        """Update the url and token."""
        if not token:
            raise ValueError("invalid token")
        self._token = token

    async def check_token_async(self) -> bool:
        """Check the token."""
        return await HAHttpClient.validate_async(url=self._base_url, token=self._token, loop=self._main_loop)

    @staticmethod
    async def validate_async(
        url: str,
        token: str,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> bool:
        """Validate the token."""
        if not isinstance(url, str) or url.strip() == "":
            raise ValueError("invalid url")
        if not isinstance(token, str) or token.strip() == "":
            raise ValueError("invalid token")
        async with aiohttp.ClientSession(loop=loop or asyncio.get_running_loop()) as session:
            http_res = await session.get(
                url=f"{url}/api/",
                params={},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                timeout=10
            )
            if http_res.status == 401:
                raise TypeError("ha api get failed, unauthorized(401)")
            if http_res.status not in [200, 201]:
                raise TypeError(f"ha auth get failed, code={http_res.status}")
            res_obj = await http_res.json()
            if "message" not in res_obj:
                raise TypeError(f"invalid response, {res_obj}")
            _LOGGER.debug("Token is valid: %s", res_obj)
            return True
        _LOGGER.error("Failed to validate token, %s", url)
        return False

    async def get_states_async(
        self, entity_id: Optional[str] = None, force_update: bool = True
    ) -> Dict[str, HAStateInfo]:
        """Get states."""
        if not force_update and self._states_buffer:
            if entity_id:
                if entity_id in self._states_buffer:
                    return {entity_id: self._states_buffer[entity_id]}
            else:
                return self._states_buffer
        res_obj = await self.__api_get_async(
            url_path="/api/states" + (f"/{entity_id}" if entity_id else ""),
            params={}
        )
        if entity_id:
            if not isinstance(res_obj, Dict):
                raise TypeError(f"invalid response, {res_obj}")
        elif not isinstance(res_obj, List):
            raise TypeError(f"invalid response, {res_obj}")
        states: Dict[str, HAStateInfo] = {}

        for state in res_obj if isinstance(res_obj, List) else [res_obj]:
            if (
                "entity_id" not in state
                or "state" not in state
                or "attributes" not in state
                or "friendly_name" not in state["attributes"]
            ):
                _LOGGER.warning("unknown state: %s", state)
                continue
            eid: str = state["entity_id"]
            states[eid] = HAStateInfo(
                entity_id=eid,
                domain=eid.partition(".")[0],
                state=state["state"],
                friendly_name=state["attributes"]["friendly_name"],
                last_changed=state.get("last_changed", 0),
                last_reported=state.get("last_reported", 0),
                last_updated=state.get("last_updated", 0),
                attributes=state.get("attributes", {}),
                context=state.get("context", {})
            )

        return states

    async def call_service(self, domain: str, service: str, entity_id: str) -> bool:
        """Call a service."""
        if not domain or not service or not entity_id:
            raise ValueError("invalid params")
        res_obj = await self.__api_post_async(
            url_path=f"/api/services/{domain}/{service}",
            data={
                "entity_id": entity_id
            }
        )
        if not isinstance(res_obj, List):
            raise TypeError(f"invalid response, {res_obj}")
        return True

    async def get_automations_async(self, force_update: bool = True) -> Dict[str, HAAutomationInfo]:
        """Get all automations."""
        res_obj = await self.get_states_async(force_update=force_update)
        automations: Dict[str, HAAutomationInfo] = {}
        for e_id, item in res_obj.items():
            if item.domain != "automation":
                continue
            last_triggered = item.attributes.get("last_triggered", None)
            last_triggered_ts = 0
            if last_triggered:
                try:
                    last_triggered_ts = int(datetime.fromisoformat(
                        last_triggered).timestamp()*1000)
                except Exception:  # pylint: disable=broad-except
                    pass
            automations[e_id] = HAAutomationInfo(
                **item.model_dump(),
                last_triggered=last_triggered_ts,
                attr_id=item.attributes.get("id", ""),
                attr_mode=item.attributes.get("mode", "")
            )
        return automations

    async def trigger_automation_async(self, automation: str | HAAutomationInfo) -> bool:
        """Trigger automation."""
        return await self.call_service(
            domain="automation",
            service="trigger",
            entity_id=automation if isinstance(automation, str) else automation.entity_id
        )

    async def get_cameras_async(self, force_update: bool = True) -> Dict[str, HAStateInfo]:
        # 从HA获取所有摄像头实例
        res_obj = await self.get_states_async(force_update=force_update)
        cameras: Dict[str, HAStateInfo] = {}
        for e_id, item in res_obj.items():
            if item.domain == "camera":
                cameras[e_id] = item
        return cameras

    async def get_camera_snapshot_async(self, entity_id: str) -> bytes:
        # 获取摄像头快照
        if not entity_id:
            raise ValueError("invalid entity_id")
        
        failed_methods = []  # 记录失败的方法和原因
        
        # 首先，尝试从entity_picture URL获取图像，entity_picture的URL中通常包含token
        try:
            state = await self.get_states_async(entity_id=entity_id, force_update=False)
            if entity_id in state:
                entity_picture = state[entity_id].attributes.get("entity_picture")
                if entity_picture:
                    # 构建完整 URL
                    if entity_picture.startswith("/"):
                        image_url = f"{self._base_url}{entity_picture}"
                    elif entity_picture.startswith("http"):
                        image_url = entity_picture
                    else:
                        image_url = f"{self._base_url}/{entity_picture}"
                    
                    # 检查URL是否已包含token参数
                    # 如果entity_picture包含 token，直接使用，无需Authorization头
                    # 否则，添加 Authorization 头
                    headers = {}
                    if "token=" not in image_url:
                        headers["Authorization"] = f"Bearer {self._token}"
                    
                    img_res = await self._session.get(
                        url=image_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=HA_HTTP_API_TIMEOUT)
                    )
                    if img_res.status == 200:
                        _LOGGER.info("尝试从 entity_picture URL 获取图像，entity_picture的URL中通常包含token 获取 %d for %s", img_res.status, entity_id)
                        return await img_res.read()
                    else:
                        error_msg = f"entity_picture returned status {img_res.status}"
                        failed_methods.append(f"entity_picture: {error_msg}")
                        _LOGGER.warning("Method 1 (entity_picture) failed for %s: %s", entity_id, error_msg)
                else:
                    failed_methods.append("entity_picture: attribute not found")
                    _LOGGER.warning("Method 1 (entity_picture) failed for %s: entity_picture attribute not found", entity_id)
            else:
                failed_methods.append("entity_picture: entity not found in state")
                _LOGGER.warning("Method 1 (entity_picture) failed for %s: entity not found in state", entity_id)
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            failed_methods.append(f"entity_picture: {error_msg}")
            _LOGGER.warning("Method 1 (entity_picture) failed for %s: %s", entity_id, error_msg)
        
        # 回退方案：尝试使用属性中的access_token从摄像头代理URL获取
        try:
            state = await self.get_states_async(entity_id=entity_id, force_update=False)
            if entity_id in state:
                access_token = state[entity_id].attributes.get("access_token")
                if access_token:
                    # 使用camera_proxy和属性中的access_token
                    proxy_url = f"{self._base_url}/api/camera_proxy/{entity_id}?token={access_token}"
                    proxy_res = await self._session.get(
                        url=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=HA_HTTP_API_TIMEOUT)
                    )
                    if proxy_res.status == 200:
                        _LOGGER.info("尝试使用属性中的 access_token 从摄像头代理 URL 获取 %d for %s", proxy_res.status, entity_id)
                        return await proxy_res.read()
                    else:
                        error_msg = f"HTTP status {proxy_res.status}"
                        failed_methods.append(f"camera_proxy with access_token: {error_msg}")
                        _LOGGER.warning("Method 2 (camera_proxy with access_token) failed for %s: %s", entity_id, error_msg)
                else:
                    failed_methods.append("camera_proxy with access_token: access_token attribute not found")
                    _LOGGER.warning("Method 2 (camera_proxy with access_token) failed for %s: access_token attribute not found", entity_id)
            else:
                failed_methods.append("camera_proxy with access_token: entity not found in state")
                _LOGGER.warning("Method 2 (camera_proxy with access_token) failed for %s: entity not found in state", entity_id)
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            failed_methods.append(f"camera_proxy with access_token: {error_msg}")
            _LOGGER.warning("Method 2 (camera_proxy with access_token) failed for %s: %s", entity_id, error_msg)
        
        # 回退方案：尝试使用Authorization头的摄像头代理URL
        try:
            proxy_url = f"{self._base_url}/api/camera_proxy/{entity_id}"
            proxy_res = await self._session.get(
                url=proxy_url,
                headers={
                    "Authorization": f"Bearer {self._token}"
                },
                timeout=aiohttp.ClientTimeout(total=HA_HTTP_API_TIMEOUT)
            )
            if proxy_res.status == 200:
                _LOGGER.info("尝试使用 Authorization 头的摄像头代理 URL 获取 %d for %s", proxy_res.status, entity_id)
                return await proxy_res.read()
            else:
                error_msg = f"HTTP status {proxy_res.status}"
                failed_methods.append(f"camera_proxy: {error_msg}")
                _LOGGER.warning("Method 3 (camera_proxy) failed for %s: %s", entity_id, error_msg)
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            failed_methods.append(f"camera_proxy: {error_msg}")
            _LOGGER.warning("Method 3 (camera_proxy) failed for %s: %s", entity_id, error_msg)
        
        # 最后手段：尝试摄像头快照服务（需要filename参数，可能不适用于所有摄像头）
        try:
            http_res = await self._session.post(
                url=f"{self._base_url}/api/services/camera/snapshot",
                json={"entity_id": entity_id},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._token}"
                },
                timeout=aiohttp.ClientTimeout(total=HA_HTTP_API_TIMEOUT)
            )
        
            if http_res.status == 401:
                raise TypeError("ha api get failed, unauthorized(401)")
        
            # 如果快照服务成功，尝试从响应中获取图像
            if http_res.status in [200, 201]:
                content_type = http_res.headers.get("Content-Type", "")
                if "image" in content_type:
                    _LOGGER.info("尝试使用快照服务获取图像 %d for %s", http_res.status, entity_id)
                    return await http_res.read()
                else:
                    error_msg = f"HTTP status {http_res.status}, Content-Type: {content_type} (not an image)"
                    failed_methods.append(f"snapshot service: {error_msg}")
                    _LOGGER.warning("Method 4 (snapshot service) failed for %s: %s", entity_id, error_msg)
            else:
                error_msg = f"HTTP status {http_res.status}"
                failed_methods.append(f"snapshot service: {error_msg}")
                _LOGGER.warning("Method 4 (snapshot service) failed for %s: %s", entity_id, error_msg)
        except TypeError:
            # 重新抛出授权错误
            raise
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            failed_methods.append(f"snapshot service: {error_msg}")
            _LOGGER.warning("Method 4 (snapshot service) failed for %s: %s", entity_id, error_msg)
        
        # 如果所有方法都失败，抛出包含详细信息的错误
        error_details = "; ".join(failed_methods)
        raise ValueError(f"Failed to get camera snapshot for {entity_id}: all methods failed. Details: {error_details}")