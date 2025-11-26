# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
独立的台灯控制 MCP 服务器
提供通过 HA控制台灯的工具
可以作为基于 stdio 或 HTTP 的 MCP 服务器独立运行

使用方法:
    # STDIO 模式（默认）
    python desk_lamp_mcp_server.py
    
    # HTTP 模式
    python desk_lamp_mcp_server.py --http --host 0.0.0.0 --port 8001
    
    # HTTP 模式（自定义主机和端口）
    python desk_lamp_mcp_server.py --http --host localhost --port 8081
"""

import argparse
import logging
import sys
from typing import Any, Optional, Annotated
from fastmcp import FastMCP
from fastmcp.tools import Tool
import httpx

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # 日志输出到 stderr，以便 stdout 可用于 MCP 协议
)
logger = logging.getLogger(__name__)

# 默认HA配置（可通过环境变量或配置文件覆盖）
DEFAULT_HA_BASE_URL = "http://192.168.68.222:8123"
DEFAULT_HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIwY2NjZmFhZmU3MDU0OTU5ODY3MzUzYmViOGQ3ZDRmNCIsImlhdCI6MTc2MzYwNTY3MCwiZXhwIjoyMDc4OTY1NjcwfQ.jzzpR5tL3f_C89SGPPTIzXVYhiDf5FxSg_1xp7NIstA"

# 创建 FastMCP 实例
mcp = FastMCP(
    name="台灯控制工具 (Desk Lamp Control)",
    instructions="提供台灯的控制功能，包括开关切换、色温调整、亮度调整等。"
)


async def get_ha_states(ha_base_url: str, ha_token: str) -> dict[str, Any]:
    """获取所有 HA状态"""
    url = f"{ha_base_url}/api/states"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"获取HA状态失败: {e}")
        raise


async def get_ha_services(ha_base_url: str, ha_token: str) -> dict[str, Any]:
    """获取所有 HA服务"""
    url = f"{ha_base_url}/api/services"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"获取HA服务失败: {e}")
        raise


async def call_ha_service(
    ha_base_url: Annotated[str, "HA基础 URL"],
    ha_token: Annotated[str, "HA访问令牌"],
    domain: Annotated[str, "服务域（例如：'light'、'button'、'number'）"],
    service: Annotated[str, "服务名称（例如：'turn_on'、'press'、'set_value'）"],
    entity_id: Annotated[str, "实体 ID（例如：'light.yeelink_cn_708787196_lamp27_s_2_light'）"],
    service_data: Annotated[Optional[dict[str, Any]], "附加服务数据"] = None
) -> dict[str, Any]:
    """
    调用 HA服务
    
    Args:
        ha_base_url: HA基础 URL
        ha_token: HA访问令牌
        domain: 服务域
        service: 服务名称
        entity_id: 要控制的实体 ID
        service_data: 附加服务数据（可选）
        
    Returns:
        dict: 包含成功状态和结果的响应
    """
    url = f"{ha_base_url}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "entity_id": entity_id
    }
    if service_data:
        payload.update(service_data)
    
    try:
        logger.info(f"正在调用HA服务: {domain}.{service}，实体: {entity_id}，数据: {payload}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json() if response.content else {}
            logger.info(f"HA 服务调用成功: {result}")
            return {
                "success": True,
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "response": result
            }
    except httpx.HTTPStatusError as e:
        error_msg = f"调用HA服务时发生 HTTP 错误: {e.response.status_code} - {e.response.text}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    except httpx.RequestError as e:
        error_msg = f"调用HA服务时发生请求错误: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    except Exception as e:  # pylint: disable=broad-exception-caught
        error_msg = f"调用HA服务时发生意外错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}


async def toggle_lamp(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "台灯实体ID，例如: button.yeelink_cn_708787196_lamp27_toggle_a_2_1"] = "button.yeelink_cn_708787196_lamp27_toggle_a_2_1"
) -> dict[str, Any]:
    """
    台灯开关切换
    当用户要求打开或关闭台灯、切换台灯开关状态时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def increase_brightness(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "亮度+按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_bright_increase_a_3_3"
) -> dict[str, Any]:
    """
    增加台灯亮度
    当用户要求调亮台灯、增加亮度、亮度+时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def decrease_brightness(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "亮度-按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_bright_decrease_a_3_4"
) -> dict[str, Any]:
    """
    降低台灯亮度
    当用户要求调暗台灯、降低亮度、亮度-时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def cycle_brightness(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "亮度切换按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_bright_circle_a_3_5"
) -> dict[str, Any]:
    """
    切换台灯亮度
    当用户要求切换亮度、循环亮度时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def increase_color_temperature(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "色温+按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_ct_increase_a_3_7"
) -> dict[str, Any]:
    """
    增加台灯色温（更冷/更白）
    当用户要求增加色温、调成冷光、调成白光、色温+时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def decrease_color_temperature(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "色温-按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_ct_decrease_a_3_8"
) -> dict[str, Any]:
    """
    降低台灯色温（更暖/更黄）
    当用户要求降低色温、调成暖光、调成黄光、色温-时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def cycle_color_temperature(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "色温切换按钮实体ID"] = "button.yeelink_cn_708787196_lamp27_ct_circle_a_3_9"
) -> dict[str, Any]:
    """
    切换台灯色温
    当用户要求切换色温、循环色温时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "button", "press", entity_id)


async def turn_on_lamp(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "台灯实体ID"] = "light.yeelink_cn_708787196_lamp27_s_2_light",
    brightness_pct: Annotated[Optional[int], "亮度百分比 (0-100)"] = None,
    color_temp_kelvin: Annotated[Optional[int], "色温值 (2600-5100K)"] = None
) -> dict[str, Any]:
    """
    打开台灯
    当用户要求打开台灯、开灯时使用此工具
    可以同时设置亮度和色温
    """
    service_data = {}
    if brightness_pct is not None:
        service_data["brightness_pct"] = brightness_pct
    if color_temp_kelvin is not None:
        service_data["color_temp_kelvin"] = color_temp_kelvin
    
    return await call_ha_service(ha_base_url, ha_token, "light", "turn_on", entity_id, service_data if service_data else None)


async def turn_off_lamp(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "台灯实体ID"] = "light.yeelink_cn_708787196_lamp27_s_2_light"
) -> dict[str, Any]:
    """
    关闭台灯
    当用户要求关闭台灯、关灯时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "light", "turn_off", entity_id)


async def set_brightness(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "台灯实体ID"] = "light.yeelink_cn_708787196_lamp27_s_2_light",
    brightness_pct: Annotated[int, "亮度百分比 (0-100)"] = 50
) -> dict[str, Any]:
    """
    设置台灯亮度
    当用户要求设置特定亮度值、设置亮度百分比时使用此工具
    """
    return await call_ha_service(ha_base_url, ha_token, "light", "turn_on", entity_id, {"brightness_pct": brightness_pct})


async def set_color_temperature(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "台灯实体ID"] = "light.yeelink_cn_708787196_lamp27_s_2_light",
    color_temp_kelvin: Annotated[int, "色温值 (2600-5100K)，数值越小越暖，越大越冷"] = 4000
) -> dict[str, Any]:
    """
    设置台灯色温
    当用户要求设置特定色温值、调成暖光/冷光时使用此工具
    色温范围：2600K（最暖/最黄）到 5100K（最冷/最白）
    """
    return await call_ha_service(ha_base_url, ha_token, "light", "turn_on", entity_id, {"color_temp_kelvin": color_temp_kelvin})


async def set_scene_mode(
    ha_base_url: Annotated[str, "HA基础 URL"] = DEFAULT_HA_BASE_URL,
    ha_token: Annotated[str, "HA访问令牌"] = DEFAULT_HA_TOKEN,
    entity_id: Annotated[str, "模式选择实体ID"] = "select.yeelink_cn_708787196_lamp27_scene_mode_p_3_8",
    mode: Annotated[str, "模式名称，例如: Free Mode, My Mode 1, Computer, Warmth, Reading等"] = "Free Mode"
) -> dict[str, Any]:
    """
    设置台灯场景模式
    当用户要求切换模式、设置场景模式时使用此工具
    可用模式包括：自由模式、我的模式1-4、电脑模式、温馨、办公模式、阅读模式、娱乐模式等
    """
    return await call_ha_service(ha_base_url, ha_token, "select", "select_option", entity_id, {"option": mode})


if __name__ == "__main__":
    """独立 MCP 服务器的主入口点"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="独立台灯控制 MCP 服务器")
    parser.add_argument(
        "--http",
        action="store_true",
        help="以 HTTP 模式运行服务器，而不是 stdio 模式"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="绑定的主机地址（仅 HTTP 模式，默认: 0.0.0.0）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="绑定的端口（仅 HTTP 模式，默认: 8001）"
    )
    args = parser.parse_args()
    
    logger.info("正在启动独立台灯控制 MCP 服务器...")
    
    # 注册所有工具
    tools = [
        Tool.from_function(
            fn=toggle_lamp,
            name="toggle_lamp",
            description="台灯开关切换。当用户要求打开或关闭台灯、切换台灯开关状态时使用此工具"
        ),
        Tool.from_function(
            fn=increase_brightness,
            name="increase_brightness",
            description="增加台灯亮度。当用户要求调亮台灯、增加亮度、亮度+时使用此工具"
        ),
        Tool.from_function(
            fn=decrease_brightness,
            name="decrease_brightness",
            description="降低台灯亮度。当用户要求调暗台灯、降低亮度、亮度-时使用此工具"
        ),
        Tool.from_function(
            fn=cycle_brightness,
            name="cycle_brightness",
            description="切换台灯亮度。当用户要求切换亮度、循环亮度时使用此工具"
        ),
        Tool.from_function(
            fn=increase_color_temperature,
            name="increase_color_temperature",
            description="增加台灯色温（更冷/更白）。当用户要求增加色温、调成冷光、调成白光、色温+时使用此工具"
        ),
        Tool.from_function(
            fn=decrease_color_temperature,
            name="decrease_color_temperature",
            description="降低台灯色温（更暖/更黄）。当用户要求降低色温、调成暖光、调成黄光、色温-时使用此工具"
        ),
        Tool.from_function(
            fn=cycle_color_temperature,
            name="cycle_color_temperature",
            description="切换台灯色温。当用户要求切换色温、循环色温时使用此工具"
        ),
        Tool.from_function(
            fn=turn_on_lamp,
            name="turn_on_lamp",
            description="打开台灯。当用户要求打开台灯、开灯时使用此工具，可以同时设置亮度和色温"
        ),
        Tool.from_function(
            fn=turn_off_lamp,
            name="turn_off_lamp",
            description="关闭台灯。当用户要求关闭台灯、关灯时使用此工具"
        ),
        Tool.from_function(
            fn=set_brightness,
            name="set_brightness",
            description="设置台灯亮度。当用户要求设置特定亮度值、设置亮度百分比时使用此工具（范围：0-100）"
        ),
        Tool.from_function(
            fn=set_color_temperature,
            name="set_color_temperature",
            description="设置台灯色温。当用户要求设置特定色温值、调成暖光/冷光时使用此工具（范围：2600-5100K）"
        ),
        Tool.from_function(
            fn=set_scene_mode,
            name="set_scene_mode",
            description="设置台灯场景模式。当用户要求切换模式、设置场景模式时使用此工具（可用模式：Free Mode, My Mode 1-4, Computer, Warmth, Reading等）"
        ),
    ]
    
    for tool in tools:
        mcp.add_tool(tool=tool)
    
    # 运行 MCP 服务器
    if args.http:
        # HTTP 模式 - 客户端可以通过 URL 连接
        # 获取实际服务器 IP/主机名用于客户端连接
        import socket
        if args.host == "0.0.0.0":
            # 尝试获取实际 IP 地址
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                actual_host = s.getsockname()[0]
                s.close()
            except Exception:
                actual_host = "localhost"
        else:
            actual_host = args.host
        
        logger.info(f"正在启动 HTTP 服务器，地址: {args.host}:{args.port}")
        logger.info(f"═══════════════════════════════════════════════════════════")
        logger.info(f"MCP 客户端应连接到:")
        logger.info(f"  URL: http://{actual_host}:{args.port}/sse")
        logger.info(f"  传输方式: http_sse")
        logger.info(f"═══════════════════════════════════════════════════════════")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        # STDIO 模式（默认）- 客户端通过命令连接
        logger.info("正在启动 STDIO 服务器")
        logger.info("MCP 客户端应将其配置为 stdio 命令")
        mcp.run()

