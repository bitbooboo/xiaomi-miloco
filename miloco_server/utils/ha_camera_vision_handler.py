# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
用于管理HA摄像头图像流。
提供处理HA摄像头图像队列和视觉处理的功能。
"""

import logging
import time

from miloco_server.schema.miot_schema import CameraImgInfo, CameraImgSeq, CameraInfo
from miot.ha_api import HAStateInfo, HAHttpClient

logger = logging.getLogger(__name__)

from miloco_server.utils.carmera_vision_handler import SizeLimitedQueue


class HACameraVisionHandler:
    def __init__(
        self,
        camera_info: CameraInfo,
        ha_client: HAHttpClient,
        entity_id: str,
        max_size: int,
        ttl: int,
        snapshot_interval: int = 5
    ):
        """
        初始化HA摄像头视觉处理器
        
        Args:
            camera_info: 摄像头信息
            ha_client: HA HTTP客户端
            entity_id: HA实体ID
            max_size: 队列最大大小
            ttl: 生存时间（秒）
            snapshot_interval: 快照间隔（秒）
        """
        self.camera_info = camera_info
        self.ha_client = ha_client
        self.entity_id = entity_id
        self.snapshot_interval = snapshot_interval
        self.camera_img_queue = SizeLimitedQueue(max_size=max_size, ttl=ttl)
        self._running = False
        
        logger.info("HACameraVisionHandler init success, entity_id: %s", entity_id)

    async def start(self):
        """启动处理器（不进行定期捕获，仅按需捕获）"""
        if self._running:
            return
        self._running = True
        # 不启动定期快照循环 - 仅在 LLM 需要图像时按需捕获
        logger.info("HACameraVisionHandler started (on-demand mode), entity_id: %s", self.entity_id)

    async def stop(self):
        """停止处理器"""
        self._running = False
        self.camera_img_queue.clear()
        logger.info("HACameraVisionHandler stopped, entity_id: %s", self.entity_id)

    async def capture_immediate_snapshot(self) -> bool:
        """
        立即捕获快照并添加到队列
        当LLM确定需要图像时按需调用
        
        Returns:
            bool: 如果快照捕获成功返回 True，否则返回 False
        """
        if not self.camera_info.online:
            logger.debug("Camera %s is not online, cannot capture snapshot", self.entity_id)
            return False
        
        try:
            snapshot_data = await self.ha_client.get_camera_snapshot_async(self.entity_id)
            if snapshot_data:
                self.camera_img_queue.put(
                    CameraImgInfo(data=snapshot_data, timestamp=int(time.time() * 1000))
                )
                logger.info(
                    "Captured on-demand snapshot for entity_id: %s, size: %d",
                    self.entity_id, len(snapshot_data)
                )
                return True
            else:
                logger.warning("No snapshot data returned for entity_id: %s", self.entity_id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to capture on-demand snapshot for entity_id %s: %s", self.entity_id, e)
        
        return False

    async def update_camera_info(self, camera_info: CameraInfo) -> None:
        """更新摄像头信息"""
        self.camera_info = camera_info
        if not self.camera_info.online:
            self.camera_img_queue.clear()

    async def get_recents_camera_img(self, channel: int, n: int) -> CameraImgSeq:
        """
        获取最近的摄像头图像
        按需捕获：如果队列为空，当 LLM 需要图像时立即捕获
        
        Args:
            channel: 通道号（HA 摄像头始终为 0）
            n: 要获取的图像数量
            
        Returns:
            包含最近图像的 CameraImgSeq
        """
        if not self.camera_info.online:
            return CameraImgSeq(
                camera_info=self.camera_info,
                channel=channel,
                img_list=[]
            )
        
        # 如果队列为空，立即捕获（当 LLM 需要图像时按需捕获）
        if self.camera_img_queue.is_empty():
            logger.info("Image queue is empty for %s, capturing on-demand snapshot", self.entity_id)
            capture_success = await self.capture_immediate_snapshot()
            if not capture_success:
                logger.warning("Failed to capture snapshot for %s, returning empty image list", self.entity_id)
                return CameraImgSeq(
                    camera_info=self.camera_info,
                    channel=channel,
                    img_list=[]
                )
        
        img_list = self.camera_img_queue.get_recent(n)
        logger.debug("get_recents_camera_img for %s: requested %d images, got %d images", 
                    self.entity_id, n, len(img_list))
        
        return CameraImgSeq(
            camera_info=self.camera_info,
            channel=channel,
            img_list=img_list
        )

    async def destroy(self) -> None:
        """销毁处理器并清理资源"""
        await self.stop()

