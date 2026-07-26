"""
Kimi WebBridge 共享客户端

通过 WebSocket 调用 Kimi WebBridge MCP 服务，驱动本地已登录的真实浏览器。
供各平台 extractor（小红书、大众点评等）复用。

前提：
1. 树莓派桌面 Chromium/Chrome 已安装 Kimi WebBridge 扩展
2. 已启动 MCP 服务：npx -y kimi-webbridge mcp
"""
import json
import time
import uuid
from typing import Any, Dict

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
        ws = websocket.create_connection(self.ws_url, timeout=self.timeout)

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
