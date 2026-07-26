"""
大众点评 Kimi WebBridge Extractor

通过 Kimi WebBridge 驱动**已登录大众点评的真实浏览器**采集搜索页指标。
相比原 Playwright + cookie 注入方案：
- 复用真实浏览器 Profile 和登录态，无需导出/注入 cookies
- 不新建 headless Chromium，更接近人工浏览
- 共享 webbridge_client，与小红书采集同一通道

前提：
1. 树莓派桌面 Chromium 已安装 Kimi WebBridge 扩展
2. 已在该浏览器登录大众点评
3. 已启动 MCP 服务：npx -y kimi-webbridge mcp
"""
import time
from typing import Any, Dict, List, Optional

from brandpulse.collectors.modules.dianping.crawler import (
    _parse_search_text,
    _search_url,
)
from brandpulse.collectors.modules.webbridge_client import (
    DEFAULT_WS_URL,
    WebBridgeClient,
)
from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)

# 与 dianping/crawler.py 中 Playwright 版相同的取数逻辑：
# 取搜索结果第一个门店卡片的文本，交给 _parse_search_text 正则解析
_EXTRACT_FIRST_SHOP_JS = """
(() => {
    const firstShop = document.querySelector(
        '.shop-list li, .shop-list-item, .txt, #shop-all-list li'
    );
    if (!firstShop) return null;
    return { text: firstShop.innerText || firstShop.textContent || '' };
})()
"""


def _current_url(client: WebBridgeClient) -> str:
    """获取当前页面 URL"""
    try:
        result = client.execute("evaluate", {"code": "location.href"})
        value = result.get("value")
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def _wait_captcha_pass(client: WebBridgeClient, max_wait: int) -> bool:
    """
    检测是否落在大众点评验证中心，若是则等待用户手动过验证。

    WebBridge 驱动的是桌面上可见的浏览器，用户可以直接在窗口里点验证码。
    每 5 秒轮询一次 URL，离开 verify 域名即视为通过。

    Returns:
        True = 页面正常（无验证或已通过）；False = 超时仍在验证页
    """
    url = _current_url(client)
    if "verify.meituan.com" not in url and "verify.dianping.com" not in url:
        return True

    logger.warning("[dianping-webbridge] 触发大众点评验证码，请在浏览器窗口手动完成验证...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(5)
        url = _current_url(client)
        if url and "verify.meituan.com" not in url and "verify.dianping.com" not in url:
            logger.info("[dianping-webbridge] 验证码已通过，继续采集")
            time.sleep(2)  # 等目标页渲染
            return True
    return False


def extract_search(
    html_text: str,
    brand_id: str,
    brand_name: str,
    city: Optional[str],
    url: str,
    site: Any,
) -> List[Dict[str, Any]]:
    """
    通用爬虫入口：通过 WebBridge 驱动已登录浏览器抓取大众点评搜索页指标。

    返回单条门店指标记录（评分/评论数/人均），字段与 dianping crawler 一致。
    """
    if not city:
        logger.error("[dianping-webbridge] 大众点评采集必须指定城市")
        return []

    params = getattr(site, "params", {}) or {}
    ws_url = params.get("ws_url", DEFAULT_WS_URL)
    wait_seconds = params.get("wait_seconds", 3)
    captcha_wait = params.get("captcha_wait_seconds", 120)

    # 支持按商场/地点限定搜索，如 --place 南开大悦城
    place = params.get("place")
    keyword = f"{place} {brand_name}" if place else brand_name

    search_url = _search_url(keyword, city)
    if not search_url:
        logger.warning(f"[dianping-webbridge] 未找到城市 {city} 的点评 ID，跳过")
        return []

    Config.ensure_dirs()
    client = WebBridgeClient(ws_url=ws_url, timeout=params.get("timeout", 60))

    logger.info(f"[dianping-webbridge] 打开搜索页: {search_url}")
    try:
        client.execute("navigate", {"url": search_url})
    except Exception as e:
        logger.error(f"[dianping-webbridge] 打开页面失败: {e}")
        return []

    time.sleep(wait_seconds)

    # 检测验证码页，等待用户在可见浏览器里手动过验证
    if not _wait_captcha_pass(client, captcha_wait):
        logger.error(f"[dianping-webbridge] 验证码未在 {captcha_wait}s 内通过，本次跳过")
        return []

    try:
        result = client.execute("evaluate", {"code": _EXTRACT_FIRST_SHOP_JS})
    except Exception as e:
        logger.error(f"[dianping-webbridge] 提取门店文本失败: {e}")
        return []

    value = result.get("value") if isinstance(result, dict) else None
    text = (value or {}).get("text") if isinstance(value, dict) else None
    if not text:
        logger.warning("[dianping-webbridge] 未找到搜索结果门店卡片（可能触发验证或未登录）")
        return []

    data = _parse_search_text(text)
    if not data or not (data.get("overall_score") or data.get("review_count")):
        logger.warning(f"[dianping-webbridge] 文本解析无有效指标: {text[:80]!r}")
        return []

    record = {
        "brand_id": brand_id,
        "brand_name": brand_name,
        "city": city,
        "place": place,
        "platform": "大众点评",
        "score": data.get("overall_score"),
        "review_count": data.get("review_count"),
        "avg_price": data.get("avg_price"),
        "shop_text": data.get("shop_text"),
        "url": search_url,
    }
    logger.info(f"[dianping-webbridge] 解析成功: score={record['score']}, reviews={record['review_count']}, price={record['avg_price']}")

    delay = getattr(site, "delay", [5, 8])
    time.sleep(__import__("random").uniform(*delay))
    return [record]


def run_login_mode(headless: bool = False) -> bool:
    """WebBridge 复用桌面浏览器登录态，无需单独登录模式"""
    logger.info("[dianping-webbridge] 使用树莓派桌面 Chromium 中已登录的会话，无需额外登录")
    return True
