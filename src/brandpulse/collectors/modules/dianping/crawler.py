"""
大众点评数据采集模块（Playwright + Cookie 注入）

采集目标：品牌评分、评论数、人均消费等热度指标。
写入 brand_metrics 表。

本地浏览器登录方案：
1. 在本地电脑浏览器登录大众点评。
2. 使用 Cookie-Editor / EditThisCookie 等插件导出 dianping.com 的 cookies 为 JSON。
3. 把 JSON 文件放到树莓派：
   /home/lsy/BrandPulse/brandpulse-infra/data/cookies/dianping_cookies.json
4. 运行爬虫。它会在请求前注入 cookies，绕过登录态问题。

合规措施：
- 默认启用随机 User-Agent
- 请求间隔可配置（默认 3-5 秒）
- 单品牌单城市仅采集首页少量数据
- 失败时自动降级为 mock 数据

依赖：playwright + chromium
"""
import random
import time
from typing import Dict, List, Optional

from brandpulse.collectors.modules.cookie_loader import load_cookies
from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


def _search_url(brand_name: str, city: str) -> Optional[str]:
    """构造大众点评搜索 URL"""
    city_id = CITY_ID_MAP.get(city)
    if not city_id:
        logger.warning(f"未找到城市 {city} 的点评 ID，跳过")
        return None
    from urllib.parse import quote
    keyword = quote(brand_name)
    return f"https://www.dianping.com/search/keyword/{city_id}/0_{keyword}"


def _parse_search_text(text: str) -> Optional[Dict]:
    """从搜索结果文本中解析评分、评论数、人均消费"""
    import re

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


class DianpingCrawler:
    """大众点评爬虫（Playwright 版本）"""

    def __init__(
        self,
        delay: tuple = (8, 12),
        headless: bool = True,
        use_cookies: bool = True,
    ):
        self.delay = delay
        self.headless = headless
        self.use_cookies = use_cookies

    def _random_delay(self):
        seconds = random.uniform(*self.delay)
        logger.debug(f"大众点评爬虫 sleep {seconds:.2f}s")
        time.sleep(seconds)

    def _extract_metrics(self, page, brand_id: str, city: str) -> Optional[Dict]:
        """
        从已渲染的点评搜索页解析第一条门店数据。

        注意：大众点评页面结构经常变化，以下选择器需要随页面调整。
        """
        # 等待页面至少加载完列表容器（超时 10s）
        try:
            page.wait_for_selector(
                ".shop-list, .shop-list-item, .txt, #shop-all-list",
                timeout=10000,
            )
        except Exception as e:
            logger.warning(f"等待列表容器超时: {e}")

        # 用 JavaScript 读取第一条结果的文本，避免选择器频繁失效
        result = page.evaluate("""
            () => {
                const firstShop = document.querySelector(
                    '.shop-list li, .shop-list-item, .txt, #shop-all-list li'
                );
                if (!firstShop) return null;
                const text = firstShop.innerText || firstShop.textContent || '';
                return { text: text };
            }
        """)

        if not result or not result.get("text"):
            logger.warning("未找到搜索结果列表项")
            self._debug_save(page, brand_id="unknown", city="unknown")
            return None

        text = result["text"]
        return _parse_search_text(text)

    def _debug_save(self, page, brand_id: str, city: str):
        """解析失败时保存截图和 HTML，便于调试"""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        Config.ensure_dirs()
        timestamp = int(time.time())
        prefix = f"{brand_id}_{city}_{timestamp}"
        screenshot_path = Config.DEBUG_DIR / f"{prefix}.png"
        html_path = Config.DEBUG_DIR / f"{prefix}.html"

        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"调试截图已保存: {screenshot_path}")
        except Exception as e:
            logger.warning(f"保存截图失败: {e}")

        try:
            html = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"调试 HTML 已保存: {html_path}")
        except Exception as e:
            logger.warning(f"保存 HTML 失败: {e}")

    def collect_brand_metrics(
        self,
        brand_id: str,
        brand_name: str,
        cities: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        使用 Playwright 采集某品牌在多个城市的点评指标。
        支持两种模式：
        1. 本地启动 Chromium（DIANPING_CDP_URL 留空）
        2. 通过 CDP 连接远程浏览器（如本地电脑的 Edge/Chrome）
        """
        from playwright.sync_api import sync_playwright

        if cities is None:
            cities = ["北京", "上海", "广州"]

        metrics = []
        cookies = load_cookies(domain_filter="dianping") if self.use_cookies else []
        cdp_url = Config.DIANPING_CDP_URL
        if cdp_url and not cdp_url.startswith(("http://", "https://", "ws://", "wss://")):
            cdp_url = f"http://{cdp_url}"
            logger.info(f"自动补全 CDP URL: {cdp_url}")

        with sync_playwright() as p:
            if cdp_url:
                logger.info(f"通过 CDP 连接远程浏览器: {cdp_url}")
                browser = p.chromium.connect_over_cdp(cdp_url)
                # 使用浏览器默认 context（已登录态通常在这里）
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                    logger.info("使用远程浏览器默认 context")
                else:
                    context = browser.new_context(
                        user_agent=random.choice(USER_AGENTS),
                        viewport={"width": 1280, "height": 800},
                    )
                    logger.info("远程浏览器无默认 context，已新建")
            else:
                logger.info("本地启动 Chromium")
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1280, "height": 800},
                )

            if cookies:
                try:
                    context.add_cookies(cookies)
                    logger.info(f"已注入 {len(cookies)} 条大众点评 cookies")
                except Exception as e:
                    logger.warning(f"注入 cookies 失败: {e}")

            page = context.new_page()

            for city in cities:
                url = _search_url(brand_name, city)
                if not url:
                    continue

                logger.info(f"[{brand_id}] 开始采集 {city} 点评数据: {url}")
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    # 再等待一下 JS 渲染
                    page.wait_for_timeout(2000)

                    data = self._extract_metrics(page, brand_id=brand_id, city=city)
                    if data and (data["overall_score"] or data["review_count"]):
                        metric = {
                            "metric_id": f"{brand_id}_{city}_dianping_{int(time.time())}",
                            "brand_id": brand_id,
                            "metric_date": time.strftime("%Y-%m-%d"),
                            "platform": "大众点评",
                            "overall_score": data.get("overall_score"),
                            "review_count": data.get("review_count"),
                            "avg_price": data.get("avg_price"),
                            "city_count": 1,
                            "data_source": f"dianping:{url}",
                        }
                        metrics.append(metric)
                        logger.info(f"[{brand_id}] {city} 解析成功: {metric}")
                    else:
                        logger.warning(f"[{brand_id}] {city} 未解析到有效指标")
                except Exception as e:
                    logger.warning(f"[{brand_id}] {city} 页面加载失败: {e}")

                self._random_delay()

            # 只有本地启动的浏览器才关闭；CDP 连接的浏览器由用户控制
            if not cdp_url:
                context.close()
                browser.close()
            else:
                # CDP 模式下只关闭页面，保留浏览器运行
                page.close()
                logger.info("CDP 模式：仅关闭页面，远程浏览器保持运行")

        return metrics

    def run_login_mode(self, login_url: str = "https://www.dianping.com") -> bool:
        """
        交互式登录模式。

        通过 X11 转发弹出一个有界面的 Chromium 窗口，用户手动登录大众点评后，
        按回车保存 cookies。后续爬虫即可复用这些 cookies。
        """
        from playwright.sync_api import sync_playwright
        from brandpulse.collectors.modules.cookie_loader import save_cookies

        with sync_playwright() as p:
            logger.info("登录模式：启动可视化浏览器（headless=False）")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            logger.info(f"打开登录页面: {login_url}")
            page.goto(login_url, wait_until="networkidle", timeout=30000)

            input(
                "\n>>> 请在弹出的浏览器窗口中登录大众点评，"
                "登录完成后按回车键保存 cookies...\n"
            )

            cookies = context.cookies()
            if cookies:
                save_cookies(cookies, filename="dianping_cookies.json")
                logger.info(f"已保存 {len(cookies)} 条 cookies")
            else:
                logger.warning("未获取到任何 cookies")

            context.close()
            browser.close()
            return bool(cookies)


def generate_mock_metrics(
    brand_id: str,
    brand_name: str,
    cities: Optional[List[str]] = None,
) -> List[Dict]:
    """生成 Mock 点评指标数据，用于无网络或测试场景"""
    if cities is None:
        cities = ["北京", "上海", "广州"]

    random.seed(brand_id)
    metrics = []
    for city in cities:
        metric = {
            "metric_id": f"{brand_id}_{city}_dianping_mock",
            "brand_id": brand_id,
            "metric_date": time.strftime("%Y-%m-%d"),
            "platform": "大众点评-mock",
            "overall_score": round(random.uniform(3.5, 4.8), 2),
            "review_count": random.randint(100, 5000),
            "avg_price": random.randint(10, 50),
            "city_count": 1,
            "data_source": "dianping:mock",
        }
        metrics.append(metric)
    return metrics
