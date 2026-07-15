"""
阶段一：采集咖啡品牌门店数据
"""
from typing import List

from brandpulse.utils.config.modules.config import Config
from brandpulse.utils.data_collection.modules.amap_api import AmapCollector
from brandpulse.utils.data_collection.modules.mock_amap_api import (
    collect_brand_stores as mock_collect,
)
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)

COFFEE_BRANDS = [
    {"brand_id": "LK001", "keywords": "瑞幸咖啡", "brand_name": "瑞幸咖啡"},
    {"brand_id": "KD001", "keywords": "库迪咖啡", "brand_name": "库迪咖啡"},
    {"brand_id": "SB001", "keywords": "星巴克", "brand_name": "星巴克"},
]


def run(
    cities: List[str] = None,
    max_pages: int = 2,
    use_mock: bool = False,
) -> dict:
    """
    采集咖啡品牌门店数据

    Args:
        cities: 目标城市列表
        max_pages: 每个城市最大采集页数（仅真实 API）
        use_mock: 是否使用 Mock 数据

    Returns:
        dict: {brand_id: [store_list]}
    """
    Config.ensure_dirs()

    if cities is None:
        cities = ["北京", "上海", "广州"]

    result = {}

    # 判断是否使用 Mock：显式指定 或 未配置 AMAP_KEY
    if not use_mock and not Config.AMAP_KEY:
        logger.warning("未配置 AMAP_KEY，自动切换到 Mock 数据模式")
        use_mock = True

    if use_mock:
        for brand_config in COFFEE_BRANDS:
            stores = mock_collect(
                brand_id=brand_config["brand_id"],
                brand_name=brand_config["brand_name"],
                cities=cities,
            )
            result[brand_config["brand_id"]] = stores
    else:
        collector = AmapCollector()
        for brand_config in COFFEE_BRANDS:
            brand_id = brand_config["brand_id"]
            keywords = brand_config["keywords"]

            logger.info(f"开始采集 {brand_id} - {keywords}")
            stores = collector.collect_brand_stores(
                brand_id=brand_id,
                keywords=keywords,
                cities=cities,
                max_pages=max_pages,
            )
            result[brand_id] = stores
            logger.info(f"{brand_id} 共采集 {len(stores)} 家门店")

    return result
