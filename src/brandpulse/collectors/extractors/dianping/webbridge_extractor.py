"""
大众点评 Kimi WebBridge Extractor

通过 Kimi WebBridge 驱动**已登录大众点评的真实浏览器**采集搜索页指标。
- 复用真实浏览器 Profile 和登录态，无需导出/注入 cookies
- 不新建 headless Chromium，更接近人工浏览
- 共享 webbridge_client，与小红书采集同一通道

前提：
1. 本机桌面浏览器（Edge/Chromium）已安装 Kimi WebBridge 扩展
2. 已在该浏览器登录大众点评
3. 已启动 MCP 服务：npx -y kimi-webbridge mcp
"""
import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from brandpulse.collectors.webbridge_client import (
    DEFAULT_WS_URL,
    WebBridgeClient,
)
from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

# 城市名 -> 大众点评城市 ID（已通过页面标题实测验证，2026-07-26）
CITY_ID_MAP = {
    "上海": 1,
    "北京": 2,
    "杭州": 3,
    "广州": 4,
    "南京": 5,
    "苏州": 6,
    "深圳": 7,
    "成都": 8,
    "重庆": 9,
    "天津": 10,
    "宁波": 11,
    "福州": 14,
    "厦门": 15,
    "武汉": 16,
    "西安": 17,
    "沈阳": 18,
}


def _search_url(brand_name: str, city: str) -> Optional[str]:
    """构造大众点评搜索 URL"""
    city_id = CITY_ID_MAP.get(city)
    if not city_id:
        logger.warning(f"未找到城市 {city} 的点评 ID，跳过")
        return None
    keyword = quote(brand_name)
    return f"https://www.dianping.com/search/keyword/{city_id}/0_{keyword}"


def _parse_search_text(text: str) -> Optional[Dict]:
    """从搜索结果文本中解析评分、评论数、人均消费"""
    # 评分：大众点评评分为 0-5 的 decimal，如 4.5 / 4.51 / 4.5分
    score_match = re.search(r"([0-5]\.\d+)\s*分?", text)
    overall_score = float(score_match.group(1)) if score_match else None

    # 评论数：1234条评论 / 1234条评价
    review_match = re.search(r"(\d+)\s*条[评论评价]", text)
    review_count = int(review_match.group(1)) if review_match else None

    # 人均：人均¥18 / 人均￥18 / 人均 18 元 / ¥18/人（¥ 有半角 U+00A5 和全角 U+FFE5 两种）
    price_match = re.search(r"人均[\s:：]*[¥￥]?\s*(\d+)", text)
    avg_price = int(price_match.group(1)) if price_match else None

    logger.debug(f"解析文本: {text[:120]!r} -> score={overall_score}, reviews={review_count}, price={avg_price}")

    return {
        "shop_text": text[:200],
        "overall_score": overall_score,
        "review_count": review_count,
        "avg_price": avg_price,
    }


def _build_shop_list_js(max_shops: int) -> str:
    """构造提取搜索页门店列表的 JS（取匹配数最多的容器，避免嵌套 .txt 重复）

    点评搜索页的评分不是文本，而是星级 CSS class（新版 star_45 = 4.5 分，
    老版 sml-str45 = 4.5 分），需要同时把星级元素的 className 带回来。
    """
    return f"""
(() => {{
    const sels = ['#shop-all-list li', '.shop-list li', '.shop-list-item'];
    let items = [];
    for (const sel of sels) {{
        const els = document.querySelectorAll(sel);
        if (els.length > items.length) items = Array.from(els);
    }}
    if (!items.length) items = Array.from(document.querySelectorAll('.txt'));
    return items.slice(0, {max_shops}).map(el => {{
        const cands = el.querySelectorAll('[class*="rank-stars"], [class*="star_"]');
        let starCls = '';
        for (const s of cands) {{
            const c = s.getAttribute('class') || '';
            if (/(?:star_|str)\\d{{2,3}}/.test(c)) {{ starCls = c; break; }}
        }}
        return {{
            text: el.innerText || el.textContent || '',
            starClass: starCls
        }};
    }});
}})()
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

    返回单条门店指标记录（评分/评论数/人均），字段与原 dianping crawler 一致。
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

    max_shops = params.get("max_shops", 10)
    try:
        result = client.execute("evaluate", {"code": _build_shop_list_js(max_shops)})
    except Exception as e:
        logger.error(f"[dianping-webbridge] 提取门店文本失败: {e}")
        return []

    value = result.get("value") if isinstance(result, dict) else None
    items = value if isinstance(value, list) else []
    if not items:
        logger.warning("[dianping-webbridge] 未找到搜索结果门店卡片（可能触发验证或未登录）")
        return []

    records = []
    seen_shops = set()
    for item in items:
        text = (item or {}).get("text") if isinstance(item, dict) else None
        if not text:
            continue
        # 去重：按门店名（文本第一行）
        shop_name = text.split("\n", 1)[0].strip()
        if not shop_name or shop_name in seen_shops:
            continue
        seen_shops.add(shop_name)

        data = _parse_search_text(text)
        if not data or not (data.get("overall_score") or data.get("review_count")):
            continue

        # 评分优先取星级 CSS class（新版 star_45 / 老版 sml-str45 = 4.5 分），
        # 搜索页文本里没有评分数字，正则解析通常拿不到
        star_class = (item or {}).get("starClass") or ""
        star_match = re.search(r"(?:star_|str)(\d{2,3})", star_class)
        if star_match:
            data["overall_score"] = int(star_match.group(1)) / 10

        records.append({
            "brand_id": brand_id,
            "brand_name": brand_name,
            "city": city,
            "place": place,
            "shop_name": shop_name,
            "platform": "大众点评",
            "score": data.get("overall_score"),
            "review_count": data.get("review_count"),
            "avg_price": data.get("avg_price"),
            "shop_text": data.get("shop_text"),
            "url": search_url,
        })

    logger.info(f"[dianping-webbridge] 解析成功 {len(records)}/{len(items)} 家门店")

    delay = getattr(site, "delay", [5, 8])
    time.sleep(random.uniform(*delay))
    return records
