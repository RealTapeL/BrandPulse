"""
阶段一：采集品牌门店数据（品牌清单从 brands 表读取）
"""
from typing import List

from brandpulse.collectors.amap.api import AmapCollector
from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.storage.pg_repository import BrandRepository

logger = get_logger(__name__)


def run(
    cities: List[str] = None,
    max_pages: int = 2,
    use_mock: bool = False,
    brand_ids: List[str] = None,
) -> dict:
    """
    从 brands 表读取品牌清单，采集门店数据

    Args:
        cities: 目标城市列表
        max_pages: 每个城市最大采集页数（仅真实 API）
        use_mock: 已废弃。生产链路不接受 Mock 数据。
        brand_ids: 指定品牌 ID 列表；None 则读取所有 is_active 品牌

    Returns:
        dict: {brand_id: [store_list]}
    """
    Config.ensure_dirs()

    if cities is None:
        cities = ["北京", "上海", "广州"]

    # 从 brands 表读取品牌清单
    brand_repo = BrandRepository()
    brands = brand_repo.list_brands(is_active=True)
    if brand_ids:
        brands = [b for b in brands if b["brand_id"] in brand_ids]

    if not brands:
        logger.warning("brands 表中未找到可用品牌，跳过采集")
        return {}

    logger.info(f"从 brands 表读取到 {len(brands)} 个品牌: {[b['brand_id'] for b in brands]}")

    if use_mock:
        raise RuntimeError("已禁用 Mock 门店数据；请配置 AMAP_KEY 后采集真实高德数据")
    if not Config.AMAP_KEY:
        raise RuntimeError("未配置 AMAP_KEY，无法采集真实门店数据；请在 .env 中配置高德 API Key")

    result = {}

    collector = AmapCollector()
    for brand in brands:
        brand_id = brand["brand_id"]
        keywords = brand.get("search_keywords") or brand["brand_name_cn"]

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
