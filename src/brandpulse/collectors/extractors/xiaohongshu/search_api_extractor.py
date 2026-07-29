"""
第三方搜索 API Extractor（BettaFish 思路）

不再用浏览器直接访问小红书/社媒页面，而是调用第三方 AI 搜索 API
（如 Bocha、Tavily）获取已经索引好的网页结果。这样可以：
- 避免主账号触发平台风控
- 不用维护 Cookie、登录态、验证码
- 把反爬压力转嫁给搜索 API 服务商

当前实现：Bocha Web Search API（国内可用，中文内容较好）
扩展方式：在 extractor 里增加 provider 分支即可。

返回字段与 webbridge_extractor 保持一致，方便 generic_web_crawler 复用。
"""
import hashlib
import re
from typing import Any, Dict, List, Optional

import requests

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BOCHA_BASE_URL = "https://api.bocha.cn/v1/web-search"
DEFAULT_TAVILY_BASE_URL = "https://api.tavily.com/search"


def _build_query(brand_name: str, city: Optional[str], template: Optional[str] = None) -> str:
    """构造搜索关键词"""
    if template:
        return template.format(city=city or "", brand_name=brand_name)
    parts = [p for p in [city, brand_name] if p]
    return " ".join(parts)


def _extract_note_id(url: str) -> Optional[str]:
    """从小红书 /explore/{note_id} 链接里提取 note_id"""
    m = re.search(r"/explore/([a-zA-Z0-9]+)", url)
    return m.group(1) if m else None


def _md5_id(text: str) -> str:
    """对无法提取 note_id 的 URL 生成稳定短 ID"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def _parse_bocha_item(item: Dict[str, Any], brand_id: str, brand_name: str, city: Optional[str], keyword: str) -> Optional[Dict[str, Any]]:
    """解析单条 Bocha 搜索结果"""
    url = item.get("url") or item.get("link")
    if not url or "xiaohongshu.com" not in url:
        return None

    note_id = _extract_note_id(url) or _md5_id(url)
    title = item.get("name") or item.get("title") or ""
    content = item.get("summary") or item.get("snippet") or ""
    publish_time = item.get("datePublished") or item.get("date")

    return {
        "note_id": note_id,
        "title": title,
        "content": content,
        "author_id": None,
        "author_name": item.get("siteName"),
        "likes": None,
        "collects": None,
        "comments": None,
        "shares": None,
        "publish_time": publish_time,
        "brand_id": brand_id,
        "brand_name": brand_name,
        "city": city,
        "keyword": keyword,
        "platform": "xiaohongshu_api",
        "url": url,
    }


def _parse_tavily_item(item: Dict[str, Any], brand_id: str, brand_name: str, city: Optional[str], keyword: str) -> Optional[Dict[str, Any]]:
    """解析单条 Tavily 搜索结果"""
    url = item.get("url")
    if not url or "xiaohongshu.com" not in url:
        return None

    note_id = _extract_note_id(url) or _md5_id(url)
    title = item.get("title") or ""
    content = item.get("content") or item.get("raw_content") or ""
    publish_time = item.get("published_date")

    return {
        "note_id": note_id,
        "title": title,
        "content": content,
        "author_id": None,
        "author_name": None,
        "likes": None,
        "collects": None,
        "comments": None,
        "shares": None,
        "publish_time": publish_time,
        "brand_id": brand_id,
        "brand_name": brand_name,
        "city": city,
        "keyword": keyword,
        "platform": "xiaohongshu_api",
        "url": url,
    }


def _bocha_search(
    keyword: str,
    max_notes: int,
    base_url: str,
    api_key: str,
) -> List[Dict[str, Any]]:
    """调用 Bocha Web Search API"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": keyword,
        "count": max_notes,
        "summary": True,
        "freshness": "noLimit",
    }

    logger.info(f"[search_api] Bocha 搜索: {keyword}")
    try:
        resp = requests.post(base_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Bocha 响应结构兼容两种可能
        web_pages = data.get("webPages") or data.get("data", {}).get("webPages", {})
        items = web_pages.get("value", [])
        logger.info(f"[search_api] Bocha 返回 {len(items)} 条网页结果")
        return items
    except Exception as e:
        logger.error(f"[search_api] Bocha 请求失败: {e}")
        return []


def _tavily_search(
    keyword: str,
    max_notes: int,
    base_url: str,
    api_key: str,
) -> List[Dict[str, Any]]:
    """调用 Tavily Search API"""
    headers = {"Content-Type": "application/json"}
    payload = {
        "api_key": api_key,
        "query": keyword,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": True,
        "max_results": max_notes,
        "include_domains": ["xiaohongshu.com"],
    }

    logger.info(f"[search_api] Tavily 搜索: {keyword}")
    try:
        resp = requests.post(base_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("results", [])
        logger.info(f"[search_api] Tavily 返回 {len(items)} 条结果")
        return items
    except Exception as e:
        logger.error(f"[search_api] Tavily 请求失败: {e}")
        return []


def extract_search(
    html_text: str,
    brand_id: str,
    brand_name: str,
    city: Optional[str],
    url: str,
    site: Any,
) -> List[Dict[str, Any]]:
    """
    通用搜索 API extractor 入口。

    通过第三方搜索 API 获取小红书等平台的公开结果，避免直接浏览器访问。
    """
    params = getattr(site, "params", {}) or {}
    provider = params.get("provider", "bocha").lower()
    max_notes = params.get("max_notes", 10)
    query_template = params.get("query_template")
    keyword = _build_query(brand_name, city, query_template)

    results: List[Dict[str, Any]] = []

    if provider == "bocha":
        api_key = Config.BOCHA_API_KEY
        base_url = Config.BOCHA_BASE_URL or DEFAULT_BOCHA_BASE_URL
        if not api_key:
            logger.error("[search_api] 未配置 BOCHA_API_KEY，无法调用 Bocha API")
            return results
        items = _bocha_search(keyword, max_notes, base_url, api_key)
        for item in items:
            note = _parse_bocha_item(item, brand_id, brand_name, city, keyword)
            if note:
                results.append(note)

    elif provider == "tavily":
        api_key = Config.TAVILY_API_KEY
        base_url = Config.TAVILY_BASE_URL or DEFAULT_TAVILY_BASE_URL
        if not api_key:
            logger.error("[search_api] 未配置 TAVILY_API_KEY，无法调用 Tavily API")
            return results
        items = _tavily_search(keyword, max_notes, base_url, api_key)
        for item in items:
            note = _parse_tavily_item(item, brand_id, brand_name, city, keyword)
            if note:
                results.append(note)

    else:
        logger.error(f"[search_api] 不支持的 provider: {provider}")

    logger.info(f"[search_api] 最终解析 {len(results)} 条小红书相关结果")
    return results
