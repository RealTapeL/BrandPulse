"""
小红书搜索 Playwright Extractor

参考 MediaCrawler 的反爬策略：
1. playwright-stealth 隐藏自动化特征
2. 注入 webId cookie 减少滑块概率
3. 拦截 /api/sns/web/v1/search/notes 接口，直接拿 JSON 数据
4. 失败时保存截图便于调试

返回字段：
    note_id, title, author, likes, collects, comments, shares, publish_time, content

注意：
- 小红书风控较严，频繁请求仍可能触发验证码
- 建议先用 --login-mode 或 cookie 方式保持登录态
- 本实现仅采集公开搜索结果的元数据，不下载正文/评论全文
"""
import json
import random
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}"
XHS_SEARCH_API_PATTERNS = [
    "/api/sns/web/v1/search/notes",
    "/api/sns/web/v2/search/notes",
    "/api/sns/web/v1/search/recommend",
]
XHS_DOMAIN = ".xiaohongshu.com"


def _random_user_agent() -> str:
    return random.choice(
        [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
    )


def _parse_note(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从搜索卡片解析单条笔记（兼容 v1/v2 接口）"""
    note_card = card.get("note_card", {})
    if not note_card:
        return None

    # note_id 可能在 item 顶层，也可能在 note_card 内
    note_id = card.get("id") or note_card.get("note_id") or note_card.get("id")
    title = note_card.get("display_title") or note_card.get("title", "")
    desc = note_card.get("desc", "")
    interact_info = note_card.get("interact_info", {})
    author = note_card.get("user", {})

    return {
        "note_id": note_id,
        "title": title,
        "content": desc,
        "author_id": author.get("user_id"),
        "author_name": author.get("nickname"),
        "likes": _to_int(interact_info.get("liked_count")),
        "collects": _to_int(interact_info.get("collected_count")),
        "comments": _to_int(interact_info.get("comment_count")),
        "shares": _to_int(interact_info.get("shared_count") or interact_info.get("share_count")),
        "publish_time": _extract_publish_time(note_card),
    }


def _extract_publish_time(note_card: Dict[str, Any]) -> Optional[str]:
    """从 corner_tag_info 或 time 字段提取发布时间"""
    if note_card.get("time"):
        return note_card.get("time")
    for tag in note_card.get("corner_tag_info", []):
        if tag.get("type") == "publish_time":
            return tag.get("text")
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def extract_search(
    html_text: str,
    brand_id: str,
    brand_name: str,
    city: Optional[str],
    url: str,
    site: Any,
) -> List[Dict[str, Any]]:
    """
    通用爬虫入口：使用 Playwright 抓取小红书搜索结果

    Args:
        html_text: 占位，本 extractor 内部重新请求
        brand_id: 品牌 ID
        brand_name: 品牌名称/关键词
        city: 城市（小红书搜索可忽略，或用于拼接关键词）
        url: 配置文件里的 base_url
        site: SiteConfig 对象

    Returns:
        笔记列表
    """
    keyword = brand_name
    if city:
        keyword = f"{city} {brand_name}"

    headless = getattr(site, "headless", True)
    delay = getattr(site, "delay", [3, 5])
    max_notes = getattr(site, "params", {}).get("max_notes", 20)

    Config.ensure_dirs()

    results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=_random_user_agent(),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

        # 反爬：注入 stealth 脚本
        Stealth().apply_stealth_sync(context)

        # 反爬：添加 webId cookie，可减少滑块出现概率
        context.add_cookies(
            [
                {
                    "name": "webId",
                    "value": f"xhs_{int(time.time())}_{random.randint(1000, 9999)}",
                    "domain": XHS_DOMAIN,
                    "path": "/",
                }
            ]
        )

        # 加载用户本地 cookies（如果存在）
        _load_user_cookies(context)

        page = context.new_page()
        intercepted_response: Optional[Dict] = None

        def handle_response(response):
            nonlocal intercepted_response
            # 记录可能是 API 的响应，便于调试
            if "/api/" in response.url and "search" in response.url and response.status == 200:
                logger.info(f"[xhs] API 响应: {response.url[:120]}")
            if any(p in response.url for p in XHS_SEARCH_API_PATTERNS) and response.status == 200:
                try:
                    data = response.json()
                    if data and "data" in data:
                        api_slug = response.url.split("/")[-1].split("?")[0].replace("/", "_")
                        _save_api_sample(data, brand_id, city, suffix=api_slug)
                        items = data.get("data", {}).get("items")
                        # 优先使用包含真实笔记列表的响应（有 note_card 或 id 的条目）
                        if items and len(items) > 0 and ("note_card" in items[0] or "id" in items[0] or "note_id" in items[0]):
                            logger.info(f"[xhs] 拦截到笔记搜索 API: {response.url[:80]}...")
                            intercepted_response = data
                        else:
                            logger.debug(f"[xhs] 搜索 API 无笔记列表: {response.url[:80]}...")
                except Exception as e:
                    logger.debug(f"[xhs] 解析响应 JSON 失败: {e}")

        page.on("response", handle_response)

        target_url = XHS_SEARCH_URL.format(keyword=keyword)
        logger.info(f"[xhs] 打开搜索页: {target_url}")

        try:
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            # 等待接口响应及页面渲染
            page.wait_for_timeout(random.randint(3000, 5000))

            if intercepted_response:
                items = intercepted_response.get("data", {}).get("items", [])
                for card in items[:max_notes]:
                    note = _parse_note(card)
                    if note:
                        note.update(
                            {
                                "brand_id": brand_id,
                                "brand_name": brand_name,
                                "city": city,
                                "keyword": keyword,
                                "platform": "xiaohongshu",
                                "url": f"https://www.xiaohongshu.com/explore/{note.get('note_id')}",
                            }
                        )
                        results.append(note)
                logger.info(f"[xhs] 通过 API 拦截解析 {len(results)} 条笔记")
            else:
                logger.warning("[xhs] 未拦截到搜索 API 响应，尝试页面兜底解析")
                results = _parse_from_page(page, brand_id, brand_name, city, keyword, max_notes)
                if not results:
                    _debug_save(page, brand_id, city)
                    logger.warning("[xhs] 兜底解析也未获取到数据，已保存调试文件")

        except Exception as e:
            logger.error(f"[xhs] 搜索页加载失败: {e}")
            _debug_save(page, brand_id, city)
        finally:
            context.close()
            browser.close()

    # 随机延迟，降低风控
    time.sleep(random.uniform(*delay))
    return results


def _load_user_cookies(context) -> None:
    """加载用户本地导出的小红书 cookies"""
    from brandpulse.collectors.modules.cookie_loader import load_cookies

    try:
        cookies = load_cookies(domain_filter="xiaohongshu")
        if cookies:
            context.add_cookies(cookies)
            logger.info(f"[xhs] 已加载 {len(cookies)} 条用户 cookies")
    except Exception as e:
        logger.debug(f"[xhs] 加载用户 cookies 失败: {e}")


def _parse_from_page(page, brand_id, brand_name, city, keyword, max_notes) -> List[Dict[str, Any]]:
    """兜底：从页面 DOM 中解析少量笔记信息"""
    results = []
    try:
        cards = page.query_selector_all('section.note-item, div.note-item, a[href*="/explore/"]')
        for idx, card in enumerate(cards[:max_notes]):
            try:
                title_el = card.query_selector('.title, .desc, span') or card
                title = title_el.inner_text() if title_el else ""
                href = card.get_attribute("href") or ""
                note_id = href.split("/explore/")[-1].split("?")[0] if "/explore/" in href else None
                if note_id:
                    results.append(
                        {
                            "note_id": note_id,
                            "title": title[:200],
                            "content": "",
                            "author_id": None,
                            "author_name": None,
                            "likes": None,
                            "collects": None,
                            "comments": None,
                            "shares": None,
                            "publish_time": None,
                            "brand_id": brand_id,
                            "brand_name": brand_name,
                            "city": city,
                            "keyword": keyword,
                            "platform": "xiaohongshu",
                            "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                        }
                    )
            except Exception:
                continue
        logger.info(f"[xhs] 页面兜底解析 {len(results)} 条笔记")
    except Exception as e:
        logger.warning(f"[xhs] 页面兜底解析失败: {e}")
    return results


def _save_api_sample(data: Dict, brand_id: str, city: Optional[str], suffix: str = "") -> None:
    """保存 API 响应样本，便于分析字段结构"""
    import json as _json
    import time as _time

    Config.ensure_dirs()
    slug = f"_{suffix}" if suffix else ""
    path = Config.DEBUG_DIR / f"xhs_api_{brand_id}_{city or 'all'}{slug}_{int(_time.time() * 1000)}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[xhs] API 样本已保存: {path}")
    except Exception as e:
        logger.warning(f"[xhs] 保存 API 样本失败: {e}")


def _debug_save(page, brand_id: str, city: Optional[str]) -> None:
    """失败时保存截图和 HTML"""
    import time as _time

    Config.ensure_dirs()
    prefix = f"xhs_{brand_id}_{city or 'all'}_{int(_time.time())}"
    try:
        page.screenshot(path=str(Config.DEBUG_DIR / f"{prefix}.png"), full_page=True)
        html = page.content()
        with open(Config.DEBUG_DIR / f"{prefix}.html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[xhs] 调试文件已保存: {Config.DEBUG_DIR}/{prefix}.*")
    except Exception as e:
        logger.warning(f"[xhs] 保存调试文件失败: {e}")


def run_login_mode(headless: bool = False) -> bool:
    """
    小红书登录模式：弹出可视化浏览器，用户扫码/密码登录后保存 cookies。

    用法：
        python main.py crawl --site xiaohongshu_search --login-mode
    """
    from brandpulse.collectors.modules.cookie_loader import save_cookies

    Config.ensure_dirs()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=_random_user_agent(),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        Stealth().apply_stealth_sync(context)

        # 同样注入 webId cookie，降低登录时出现验证码的概率
        context.add_cookies(
            [
                {
                    "name": "webId",
                    "value": f"xhs_{int(time.time())}_{random.randint(1000, 9999)}",
                    "domain": XHS_DOMAIN,
                    "path": "/",
                }
            ]
        )

        page = context.new_page()
        logger.info("[xhs] 登录模式：打开小红书首页，请扫码或密码登录")
        page.goto("https://www.xiaohongshu.com", wait_until="networkidle", timeout=60000)

        input(
            "\n>>> 请在弹出的浏览器窗口中登录小红书，"
            "登录完成后按回车键保存 cookies...\n"
        )

        cookies = context.cookies()
        if cookies:
            save_cookies(cookies, filename="xiaohongshu_cookies.json")
            logger.info(f"[xhs] 已保存 {len(cookies)} 条 cookies")
        else:
            logger.warning("[xhs] 未获取到任何 cookies")

        context.close()
        browser.close()
        return bool(cookies)
