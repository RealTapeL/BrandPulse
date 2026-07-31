"""
指标聚合 job：从 brand_indicators_daily（门店/笔记级指标）按 mall+date 聚合，
写入 indicators 表，为 GET /api/v1/indicators 提供时序数据。

按采集数据集（brand_id）和商场维度聚合，保留采集链路的真实归属。
"""
from typing import Dict, List

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

# 需要从 brand_indicators_daily 聚合的指标名 -> 聚合字段
METRICS = {
    "reputation": "AVG(weighted_score)",
    "heat": "AVG(heat_index)",
    "sov": "AVG(sov)",
}


def aggregate(date: str | None = None) -> Dict[str, int]:
    """
    聚合 indicators。不传 date 时聚合库中最新的指标日。

    Returns:
        { indicator: 写入行数 }
    """
    client = PostgresClient()
    stats: Dict[str, int] = {}

    # 确定要聚合的日期列表
    if date:
        dates = [date]
    else:
        with client.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT stat_date FROM brand_indicators_daily ORDER BY stat_date DESC LIMIT 30")
            ).fetchall()
            dates = [str(r[0]) for r in rows]

    if not dates:
        logger.warning("[aggregate] brand_indicators_daily 无数据，跳过聚合")
        return stats

    for d in dates:
        # 查询该日所有门店级指标
        with client.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT brand_id, mall_name, city,
                           AVG(weighted_score) AS reputation,
                           AVG(heat_index) AS heat,
                           AVG(sov) AS sov
                    FROM brand_indicators_daily
                    WHERE stat_date = :d
                    GROUP BY brand_id, mall_name, city
                """),
                {"d": d},
            ).mappings().all()

        # 写入 indicators（brand_id 与原始采集/指标行保持一致）
        inserted = 0
        upsert_sql = """
            INSERT INTO indicators (brand_id, indicator, date, value)
            VALUES (:brand_id, :indicator, :date, :value)
            ON CONFLICT (brand_id, indicator, date) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
        """
        for r in rows:
            brand_id = r["brand_id"]
            if not brand_id:
                logger.warning("[aggregate] %s/%s 缺少 brand_id，跳过", r["mall_name"], r["city"])
                continue
            for indicator, field in METRICS.items():
                value = r[indicator]
                if value is None:
                    continue
                try:
                    client.execute(upsert_sql, {
                        "brand_id": brand_id,
                        "indicator": indicator,
                        "date": d,
                        "value": float(value),
                    })
                    inserted += 1
                except Exception as e:
                    logger.error(f"[aggregate] 写入 {brand_id}/{indicator}/{d} 失败: {e}")
        stats[d] = inserted
        logger.info(f"[aggregate] {d}: 写入 {inserted} 行")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="指标聚合 job")
    parser.add_argument("--date", type=str, default=None, help="指定聚合日期 YYYY-MM-DD")
    args = parser.parse_args()
    print(aggregate(args.date))
