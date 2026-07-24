"""
大众点评数据采集模块（合规、低频、试点）

采集目标：品牌评分、评论数、人均消费等热度指标。
写入 brand_metrics 表。

合规措施：
- 默认启用随机 User-Agent
- 请求间隔可配置（默认 3-5 秒）
- 单品牌单城市仅采集首页少量数据
- 失败时自动降级为 Mock 数据，避免重复请求

注意：大众点评页面结构可能变化，若解析失败请切换到 mock 模式验证流程。
"""
import random
import re
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)

# 城市名 -> 大众点评城市 ID（仅试点城市，可按需扩展）
CITY_ID_MAP = {
    "北京": 1,
    "上海": 2,
    "天津": 3,
    "广州": 4,
    "深圳": 7,
    "南京": 9,
    "苏州": 10,
    "杭州": 14,
    "重庆": 15,
    "武汉": 16,
    "西安": 17,
    "成都": 18,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


class DianpingCrawler:
    """大众点评爬虫"""

    def __init__(self, delay: tuple = (3, 5), timeout: int = 15):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.dianping.com/",
        })

    def _random_delay(self):
        """请求间隔，默认 3-5 秒"""
        seconds = random.uniform(*self.delay)
        logger.debug(f"大众点评爬虫 sleep {seconds:.2f}s")
        time.sleep(seconds)

    def _get(self, url: str) -> Optional[str]:
        """发起 GET 请求，返回 HTML 文本"""
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"请求失败 {url}: {e}")
            return None

    def _search_url(self, brand_name: str, city: str) -> Optional[str]:
        """构造搜索 URL"""
        city_id = CITY_ID_MAP.get(city)
        if not city_id:
            logger.warning(f"未找到城市 {city} 的点评 ID，跳过")
            return None
        # URL 编码品牌名
        from urllib.parse import quote
        keyword = quote(brand_name)
        return f"https://www.dianping.com/search/keyword/{city_id}/0_{keyword}"

    def _extract_search_result(self, html: str) -> Optional[Dict]:
        """
        从搜索结果页解析第一条门店数据。

        返回示例：
        {
            "shop_name": "瑞幸咖啡(XXX店)",
            "overall_score": 4.5,
            "review_count": 1234,
            "avg_price": 18.0,
        }
        """
        soup = BeautifulSoup(html, "html.parser")

        # 大众点评搜索结果列表常见容器选择器（结构可能变化）
        first_shop = soup.select_one(".shop-list li[data-mid], .shop-list li, .shop-list-item, .txt")
        if not first_shop:
            # 尝试更通用的选择器
            first_shop = soup.select_one("li[id^='shop_']") or soup.find("li")
        if not first_shop:
            logger.warning("未找到搜索结果列表项")
            return None

        # 店名
        shop_name_tag = (
            first_shop.select_one("h4 a, .tit a, .shopname, .shop-name, a[data-click-name]")
            or first_shop.find("a")
        )
        shop_name = shop_name_tag.get_text(strip=True) if shop_name_tag else ""

        # 评分：常见文本如 "4.5" 或 "4.5分"
        score_tag = first_shop.select_one(".comment, .score, .sml-rank-stars, .star-text")
        score_text = score_tag.get_text(strip=True) if score_tag else ""
        score_match = re.search(r"(\d+\.\d+|\d+)", score_text)
        overall_score = float(score_match.group(1)) if score_match else None

        # 评论数：常见文本如 "1234条评论"
        review_tag = first_shop.select_one(".comment-num, .review-num, .comment-list b")
        review_text = review_tag.get_text(strip=True) if review_tag else ""
        review_match = re.search(r"(\d+)", review_text.replace(",", ""))
        review_count = int(review_match.group(1)) if review_match else None

        # 人均：常见文本如 "人均: ¥18"
        price_tag = first_shop.select_one(".avg-price, .price, .mean-price")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        price_match = re.search(r"(\d+)", price_text.replace(",", ""))
        avg_price = int(price_match.group(1)) if price_match else None

        return {
            "shop_name": shop_name,
            "overall_score": overall_score,
            "review_count": review_count,
            "avg_price": avg_price,
        }

    def collect_brand_metrics(
        self,
        brand_id: str,
        brand_name: str,
        cities: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        采集某品牌在多个城市的点评指标

        返回列表，每个元素对应一个城市，可直接写入 brand_metrics。
        """
        if cities is None:
            cities = ["北京", "上海", "广州"]

        metrics = []
        for city in cities:
            url = self._search_url(brand_name, city)
            if not url:
                continue

            logger.info(f"[{brand_id}] 开始采集 {city} 点评数据: {url}")
            html = self._get(url)
            if not html:
                logger.warning(f"[{brand_id}] {city} 页面获取失败，跳过")
                continue

            data = self._extract_search_result(html)
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

            self._random_delay()

        return metrics


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
