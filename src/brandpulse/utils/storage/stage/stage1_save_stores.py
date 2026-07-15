"""
阶段一：将采集的门店数据保存到 PostgreSQL 和 Neo4j
"""
from typing import Dict, List

from brandpulse.utils.logger.modules.logger import get_logger
from brandpulse.utils.storage.modules.neo4j_repository import Neo4jRepository
from brandpulse.utils.storage.modules.pg_repository import BrandRepository, StoreRepository

logger = get_logger(__name__)


def run(stores_by_brand: Dict[str, List[dict]]) -> dict:
    """
    保存门店数据

    Args:
        stores_by_brand: {brand_id: [store_list]}

    Returns:
        dict: 统计信息
    """
    brand_repo = BrandRepository()
    store_repo = StoreRepository()
    neo4j_repo = Neo4jRepository()

    stats = {"pg_stores": 0, "neo4j_brands": 0, "neo4j_stores": 0}

    for brand_id, stores in stores_by_brand.items():
        if not stores:
            continue

        # 确保 PG 中有品牌节点
        pg_brand = brand_repo.get_brand(brand_id)
        if pg_brand:
            neo4j_repo.create_brand_node(pg_brand)
            stats["neo4j_brands"] += 1

        # 保存到 PostgreSQL
        pg_count = store_repo.batch_upsert_stores(stores)
        stats["pg_stores"] += pg_count

        # 保存到 Neo4j
        neo_count = 0
        for store in stores:
            if neo4j_repo.create_store_node(store):
                neo_count += 1
        stats["neo4j_stores"] += neo_count

        logger.info(
            f"{brand_id}: PG 入库 {pg_count} 条, Neo4j 入库 {neo_count} 个节点"
        )

    return stats
