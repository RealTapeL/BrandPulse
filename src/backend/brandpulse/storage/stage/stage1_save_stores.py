"""
阶段一：将采集的门店数据保存到 PostgreSQL
"""
from typing import Dict, List
from uuid import uuid4

from brandpulse.logger.logger import get_logger
from brandpulse.storage.pg_repository import StoreRepository
from brandpulse.data_governance.service import DataGovernanceService

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
    governance = DataGovernanceService()

    stats = {"pg_stores": 0}

    for brand_id, stores in stores_by_brand.items():
        if not stores:
            continue

        pg_count = store_repo.batch_upsert_stores(stores)
        stats["pg_stores"] += pg_count

        logger.info(f"{brand_id}: PG 入库 {pg_count} 条")
        cities = sorted({str(item.get("city") or "") for item in stores if item.get("city")})
        try:
            governance.record_source_log(
                run_id=f"stage1_{uuid4().hex}",
                trace_id=None,
                source_name="amap",
                source_type="api",
                entity_type="stores",
                entity_id=brand_id,
                record_count=len(stores),
                status="completed",
                metadata={"cities": cities, "pg_saved": pg_count},
            )
        except Exception as exc:
            logger.error(f"{brand_id}: 写入高德采集血缘失败: {exc}")

    return stats
