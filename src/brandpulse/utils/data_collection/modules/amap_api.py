"""
高德地图 API 数据采集模块
用于采集品牌门店布局数据
"""
import time
from typing import Dict, List, Optional

import requests

from brandpulse.utils.config.modules.config import Config
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)

AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"


class AmapCollector:
    """高德地图数据采集器"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.AMAP_KEY
        if not self.api_key:
            logger.warning("未配置 AMAP_KEY，请在 .env 文件中设置")

    def search_places(
        self,
        keywords: str,
        city: Optional[str] = None,
        citylimit: bool = True,
        page_size: int = 25,
        max_pages: int = 10,
    ) -> List[Dict]:
        """
        按关键词搜索地点

        Args:
            keywords: 搜索关键词，如"瑞幸咖啡"
            city: 城市名称，如"北京"
            citylimit: 是否强制城市内搜索
            page_size: 每页数量，最大 25
            max_pages: 最大页数

        Returns:
            地点列表
        """
        all_places = []

        for page in range(1, max_pages + 1):
            params = {
                "key": self.api_key,
                "keywords": keywords,
                "offset": page_size,
                "page": page,
                "output": "JSON",
            }
            if city:
                params["city"] = city
                params["citylimit"] = "true" if citylimit else "false"

            try:
                response = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "1":
                    logger.error(f"高德 API 返回错误: {data.get('info', '未知错误')}")
                    break

                places = data.get("pois", [])
                if not places:
                    break

                all_places.extend(places)
                logger.info(f"{keywords} {city or '全国'} 第 {page} 页采集 {len(places)} 条")

                # 如果不足一页，说明已经到末尾
                if len(places) < page_size:
                    break

                time.sleep(0.2)

            except Exception as e:
                logger.error(f"请求高德 API 失败: {e}")
                break

        return all_places

    @staticmethod
    def parse_place(place: Dict, brand_id: str) -> Dict:
        """解析高德 POI 为标准化门店数据"""
        location = place.get("location", ",")
        lng, lat = location.split(",") if "," in location else (None, None)

        return {
            "store_id": f"{brand_id}_{place.get('id', '')}",
            "brand_id": brand_id,
            "store_name": place.get("name", ""),
            "province": place.get("pname", ""),
            "city": place.get("cityname", ""),
            "district": place.get("adname", ""),
            "mall_name": AmapCollector._extract_mall_name(place.get("address", "")),
            "address": place.get("address", ""),
            "floor": "",
            "longitude": float(lng) if lng else None,
            "latitude": float(lat) if lat else None,
            "store_area": None,
            "opening_date": None,
            "store_status": "营业中",
            "store_type": "",
            "is_our_mall": False,
            "data_source": "amap",
            "source_url": "",
        }

    @staticmethod
    def _extract_mall_name(address: str) -> str:
        """从地址中提取商场名称（简单规则）"""
        mall_keywords = ["商场", "购物中心", "广场", "大厦", "中心", "MALL"]
        for kw in mall_keywords:
            if kw in address:
                parts = address.split(kw)
                if len(parts) > 1:
                    return parts[0][-10:] + kw
        return ""

    def collect_brand_stores(
        self,
        brand_id: str,
        keywords: str,
        cities: Optional[List[str]] = None,
        max_pages: int = 10,
    ) -> List[Dict]:
        """采集某个品牌的门店数据"""
        all_stores = []

        if cities:
            for city in cities:
                places = self.search_places(keywords, city=city, max_pages=max_pages)
                stores = [self.parse_place(p, brand_id) for p in places]
                all_stores.extend(stores)
                logger.info(f"{brand_id} 在 {city} 采集 {len(stores)} 家门店")
        else:
            places = self.search_places(keywords, max_pages=max_pages)
            stores = [self.parse_place(p, brand_id) for p in places]
            all_stores.extend(stores)
            logger.info(f"{brand_id} 全国采集 {len(stores)} 家门店")

        return all_stores
