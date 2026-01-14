# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
提供通过微信、QQ或京ME发送消息的工具
可以作为基于 stdio 或 HTTP 的 MCP 服务器独立运行
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

# 创建 FastMCP 实例
mcp = FastMCP(
    name="消息发送工具 (Message Sender)",
    instructions="提供通过微信、QQ或京ME发送消息的工具。"
)


async def send_message(
    msgtype: Annotated[str, "消息类型：'wx' 表示微信，'qq' 表示QQ，'jme' 表示京ME"],
    content: Annotated[str, "要发送的消息内容"],
    erp: Annotated[Optional[str], "ERP 用户名"] = None,
    telephone: Annotated[Optional[str], "接收者的电话号码"] = None,
    subject: Annotated[Optional[str], "消息主题"] = None
) -> dict[str, Any]:
    """
    通过微信、QQ或京ME发送消息
    
    Args:
        msgtype: 消息类型 - 'wx' (微信), 'qq' (QQ), 或 'jme' (京ME)
        content: 消息内容
        erp: ERP 用户名（可选，默认为 zhuhongxu7）
        telephone: 接收者的电话号码（可选，默认为 13718027675）
        subject: 消息主题（可选）
        
    Returns:
        dict: 包含成功状态和结果的响应
    """
    # 验证 msgtype
    valid_types = ["wx", "qq", "jme"]
    if msgtype not in valid_types:
        error_msg = f"无效的消息类型: {msgtype}。必须是以下之一: {valid_types}"
        logger.error(error_msg)
        return {"error": error_msg}
    
    # 如果未提供 erp，使用默认值
    if not erp:
        erp = "zhuhongxu7"
    
    # 如果未提供 telephone，使用默认值
    if not telephone:
        telephone = "13718027675"
    
    # 准备请求
    url = "http://jarvis-notify.yunjian.jd.com/api/v1/notify"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "telephone": telephone,
        "erp": erp,
        "msgtype": msgtype,
        "subject": subject if subject else "sub",
        "content": content
    }
    
    try:
        logger.info("===========================================> Sending message via %s to %s (erp: %s), subject: %s, content: %s", 
                   msgtype, telephone, erp, subject, content)
        logger.info("Request payload: %s", payload)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json() if response.content else {}
            # result = {}
            logger.info("**************************> Message sent successfully via %s, response: %s", msgtype, result)
            return {
                "success": True,
                "msgtype": msgtype,
                "subject": subject,
                "content": content,
                "response": result
            }
    except httpx.HTTPStatusError as e:
        error_msg = f"发送消息时发生 HTTP 错误: {e.response.status_code} - {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except httpx.RequestError as e:
        error_msg = f"发送消息时发生请求错误: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:  # pylint: disable=broad-exception-caught
        error_msg = f"发送消息时发生意外错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg}


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="独立消息发送 MCP 服务器")
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
        default=8000,
        help="绑定的端口（仅 HTTP 模式，默认: 8000）"
    )
    args = parser.parse_args()
    
    logger.info("正在启动独立消息发送 MCP 服务器...")
    
    # 注册 send_message 工具
    send_message_tool = Tool.from_function(
        fn=send_message,
        name="send_message",
        description="""
用于发送消息的工具 / Tool for sending messages via WeChat, QQ, or JingMe.
当用户需要通过微信、QQ或京ME（使用erp）发送消息或通知时使用此工具 / Use this tool when users need to send messages via WeChat, QQ, or JingMe.
支持的msgtype类型 / Supported msgtype values:
- "wx": 微信 / WeChat
- "qq": QQ
- "jme": 京ME / JingMe
"""
    )
    mcp.add_tool(tool=send_message_tool)
    
    # 运行 MCP 服务器
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


