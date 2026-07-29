"""
阶段一：将采集的门店数据保存到 PostgreSQL
"""
from typing import Dict, List

from brandpulse.logger.logger import get_logger
from brandpulse.storage.pg_repository import StoreRepository

logger = get_logger(__name__)


def run(stores_by_brand: Dict[str, List[dict]]) -> dict:
    """
    保存门店数据

    Args:
        stores_by_brand: {brand_id: [store_list]}

    Returns:
        dict: 统计信息
    """
    store_repo = StoreRepository()

    stats = {"pg_stores": 0}

    for brand_id, stores in stores_by_brand.items():
        if not stores:
            continue

        pg_count = store_repo.batch_upsert_stores(stores)
        stats["pg_stores"] += pg_count

        logger.info(f"{brand_id}: PG 入库 {pg_count} 条")

    return stats
