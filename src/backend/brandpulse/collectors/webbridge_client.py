"""
Kimi WebBridge 共享客户端

通过 WebSocket 调用 Kimi WebBridge MCP 服务，驱动本地已登录的真实浏览器。
供各平台 extractor（小红书、大众点评等）复用。

前提：
1. 本机桌面浏览器（Edge/Chromium）已安装 Kimi WebBridge 扩展
2. 已启动 MCP 服务：npx -y kimi-webbridge mcp
"""
import json
import socket
import time
import uuid
from typing import Any, Dict
from urllib.parse import urlparse

import websocket

DEFAULT_WS_URL = "ws://127.0.0.1:10086/ws"


class WebBridgeClient:
    """通过 WebSocket 调用 Kimi WebBridge MCP 服务"""

    def __init__(self, ws_url: str = DEFAULT_WS_URL, timeout: int = 60):
        self.ws_url = ws_url
        self.timeout = timeout

    def execute(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 tool_call 并等待 tool_result。

        Args:
            action: navigate / evaluate / screenshot / click / fill 等
            args: 对应参数

        Returns:
            tool_result 的 payload
        """
        request_id = str(uuid.uuid4())
        # 开发环境常设置 HTTP(S)_PROXY。websocket-client 会默认读取它，
        # 即使目标是 127.0.0.1，也可能把本地 WebBridge 握手转给代理并得到
        # ``403 forbidden origin``。部分 websocket-client 版本不会把
        # http_no_proxy 传给环境代理解析器，因此本机 ws 通道直接提供已连接的
        # TCP socket，彻底绕开代理；非本机 URL 仍保留环境代理行为。
        parsed_url = urlparse(self.ws_url)
        host = parsed_url.hostname
        connection_options: Dict[str, Any] = {}
        if parsed_url.scheme == "ws" and host in {"127.0.0.1", "localhost", "::1"}:
            connection_options["socket"] = socket.create_connection(
                (host, parsed_url.port or 80), timeout=self.timeout
            )
            # 与官方 Node CLI 一样不发送 Origin，避免旧版中间件错误拦截本地请求。
            connection_options["suppress_origin"] = True
        ws = websocket.create_connection(self.ws_url, timeout=self.timeout, **connection_options)

        try:
            ws.send(json.dumps({
                "type": "tool_call",
                "requestId": request_id,
                "payload": {"name": action, "args": args},
            }))

            start = time.time()
            while time.time() - start < self.timeout:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # 跳过扩展 hello / pong
                if msg.get("type") in ("hello", "pong"):
                    continue

                if msg.get("type") == "tool_result" and (
                    msg.get("requestId") == request_id or msg.get("responseToRequestId") == request_id
                ):
                    payload = msg.get("payload", {})
                    # 某些版本的 payload 会再包一层 data
                    if isinstance(payload, dict) and "data" in payload and len(payload) <= 2:
                        return payload["data"]
                    return payload
        finally:
            try:
                ws.close()
            except Exception:
                pass

        raise TimeoutError(f"WebBridge action '{action}' 超时（>{self.timeout}s）")
