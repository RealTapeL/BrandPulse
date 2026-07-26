"""
Kimi WebBridge Extractor

通过 Kimi WebBridge 驱动**已登录小红书的真实浏览器**采集搜索结果。
相比新开 Playwright Context，本方案：
- 复用真实浏览器 Profile 和登录态
- 不新建 headless Chromium
- 更接近人工浏览行为，降低被风控概率

前提：
1. 树莓派桌面 Chromium/Chrome 已安装 Kimi WebBridge 扩展
2. 已登录小红书（建议小号）
3. 已启动 MCP 服务：
   ```bash
   npx -y kimi-webbridge mcp
   ```

注意：
- 即使使用 WebBridge，高频自动化仍可能触发平台风控，请控制采集频率
- 建议每次只搜 1-2 个关键词，间隔 30 秒以上
"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import websocket

from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WS_URL = "ws://127.0.0.1:10086/ws"
XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}"


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


def _build_extract_js(max_notes: int) -> str:
    """构造提取小红书搜索卡片的 JS 代码

    按 DOM 选择器取字段，不用行号切分——部分卡片（无标题笔记、视频笔记）
    footer 结构不同，按行取会错位。
    """
    return f"""
Array.from(document.querySelectorAll('section.note-item'))
  .slice(0, {max_notes})
  .map(s => {{
    const text = (sel) => {{
      const el = s.querySelector(sel);
      return el ? (el.innerText || '').trim() : null;
    }};
    const lines = (s.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean);
    const link = s.querySelector('a[href*="/explore/"]');
    const noteId = s.dataset.noteId || (link ? link.href.split('/explore/')[1].split('?')[0] : null);

    // 时间行：形如 07-18 / 2025-11-19 / 3小时前 / 6天前 / 昨天 / 刚刚
    const timeRe = /^(\\d{{4}}-\\d{{1,2}}-\\d{{1,2}}|\\d{{1,2}}-\\d{{1,2}}|\\d+\\s*(分钟|小时|天|周|个月)前|昨天|刚刚)$/;
    const publishTime = lines.find(l => timeRe.test(l)) || null;

    const likeText = text('.like-wrapper .count') || text('.count');
    return {{
      note_id: noteId,
      title: text('.title') || text('a[class*=title]') || '',
      author_name: text('.author .name') || text('.name'),
      publish_time: publishTime,
      likes: likeText ? parseInt(likeText.replace(/[^\\d]/g, '')) : null,
      url: noteId ? 'https://www.xiaohongshu.com/explore/' + noteId : null,
    }};
  }})
  .filter(item => item.note_id && /^[0-9a-f]{{24}}$/.test(item.note_id) && item.title !== '大家都在搜')
"""


def extract_search(
    html_text: str,
    brand_id: str,
    brand_name: str,
    city: Optional[str],
    url: str,
    site: Any,
) -> List[Dict[str, Any]]:
    """
    通用爬虫入口：通过 Kimi WebBridge 驱动已登录浏览器抓取小红书搜索结果
    """
    keyword = brand_name
    if city:
        keyword = f"{city} {brand_name}"

    params = getattr(site, "params", {}) or {}
    max_notes = params.get("max_notes", 10)
    ws_url = params.get("ws_url", DEFAULT_WS_URL)
    wait_seconds = params.get("wait_seconds", 3)

    Config.ensure_dirs()
    client = WebBridgeClient(ws_url=ws_url, timeout=params.get("timeout", 60))

    # 1. 打开搜索页
    target_url = XHS_SEARCH_URL.format(keyword=quote(keyword))
    logger.info(f"[webbridge] 打开小红书搜索页: {target_url}")
    try:
        client.execute("navigate", {"url": target_url})
    except Exception as e:
        logger.error(f"[webbridge] 打开页面失败: {e}")
        return []

    # 2. 等待页面渲染
    time.sleep(wait_seconds)

    # 3. 提取卡片
    js_code = _build_extract_js(max_notes)
    try:
        result = client.execute("evaluate", {"code": js_code})
    except Exception as e:
        logger.error(f"[webbridge] 提取卡片失败: {e}")
        return []

    items = result.get("value", []) or []
    logger.info(f"[webbridge] 提取到 {len(items)} 条笔记")

    results: List[Dict[str, Any]] = []
    for item in items:
        results.append({
            "note_id": item.get("note_id"),
            "title": item.get("title"),
            "content": "",
            "author_id": None,
            "author_name": item.get("author_name"),
            "likes": item.get("likes"),
            "collects": None,
            "comments": None,
            "shares": None,
            "publish_time": item.get("publish_time"),
            "brand_id": brand_id,
            "brand_name": brand_name,
            "city": city,
            "keyword": keyword,
            "platform": "xiaohongshu",
            "url": item.get("url"),
        })

    # 随机延迟，降低风控
    delay = getattr(site, "delay", [5, 10])
    time.sleep(__import__("random").uniform(*delay))

    return results


def run_login_mode(headless: bool = False) -> bool:
    """
    WebBridge 模式不需要单独登录模式：
    用户已在树莓派桌面 Chromium 里登录小红书小号，WebBridge 直接复用该会话。
    """
    logger.info("[webbridge] 使用树莓派桌面 Chromium 中已登录的会话，无需额外登录")
    return True
