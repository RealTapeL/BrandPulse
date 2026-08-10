"""
竞争指标：声量份额 SOV（Share of Voice）

回答"同一商场同一品类里，谁占的声音最大"：
    SOV = 门店评价数 / 同商场当日总评价数

点评评价数代表真实消费后的发声量，比裸评分更接近市场份额体感。
"""
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def compute_sov(stat_date: Optional[str] = None) -> List[Dict]:
    """
    计算指定日期（默认最新采集日）各门店在同商场内的声量份额。

    Returns:
        指标行列表（entity_type='shop'，只填 sov 字段，与口碑/热度行按主键合并）
    """
    client = PostgresClient()
    if not stat_date:
        with client.engine.connect() as conn:
            row = conn.execute(text("SELECT MAX(crawl_date) FROM dp_shop_metrics")).first()
            stat_date = str(row[0]) if row and row[0] else None
    if not stat_date:
        logger.warning("dp_shop_metrics 无数据，跳过 SOV 指标")
        return []

    sql = """
    SELECT shop_name, city, COALESCE(place, '') AS mall_name, brand_id, review_count
    FROM dp_shop_metrics
    WHERE crawl_date = :stat_date
    """
    with client.engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), {"stat_date": stat_date}).mappings().all()]
    if not rows:
        return []

    # 按 商场 分组求总声量
    totals: Dict[tuple, int] = {}
    for r in rows:
        key = (r["city"], r["mall_name"])
        totals[key] = totals.get(key, 0) + (r["review_count"] or 0)

    indicators = []
    for r in rows:
        total = totals[(r["city"], r["mall_name"])] or 1
        v = r["review_count"] or 0
        indicators.append({
            "stat_date": stat_date,
            "city": r["city"],
            "mall_name": r["mall_name"],
            "entity_type": "shop",
            "entity_name": r["shop_name"],
            "brand_id": r["brand_id"],
            "sov": round(v / total, 4),
            "detail": {"metric": "sov", "shop_reviews": v, "mall_total_reviews": total},
        })

    logger.info(f"[SOV] {stat_date} 计算 {len(indicators)} 家门店")
    return indicators
