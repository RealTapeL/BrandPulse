"""
口碑指标：贝叶斯加权评分（IMDB 同款算法）

解决"5 条评价的 5.0 分" vs "3000 条评价的 4.3 分"谁更好的问题：
    WR = (v/(v+m)) * R + (m/(v+m)) * C
    R = 门店评分, v = 门店评价数
    C = 当日全城加权平均评分, m = 当日全城门店评价数中位数（可信度阈值）

评价数越少，评分越被拉回全城均值；评价数越多，越接近真实评分。
"""
import statistics
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def bayesian_weight(r: float, v: int, c: float, m: float) -> float:
    """贝叶斯加权评分纯函数（便于单测）"""
    return (v / (v + m)) * r + (m / (v + m)) * c


def _latest_crawl_date(client: PostgresClient) -> Optional[str]:
    with client.engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(crawl_date) FROM dp_shop_metrics"))
        row = result.first()
        return str(row[0]) if row and row[0] else None


def compute_weighted_scores(stat_date: Optional[str] = None) -> List[Dict]:
    """
    计算指定日期（默认最新采集日）全部门店的贝叶斯加权评分。

    Returns:
        指标行列表（entity_type='shop'）
    """
    client = PostgresClient()
    if not stat_date:
        stat_date = _latest_crawl_date(client)
    if not stat_date:
        logger.warning("dp_shop_metrics 无数据，跳过口碑指标")
        return []

    sql = """
    SELECT shop_name, city, COALESCE(place, '') AS mall_name, brand_id,
           score, review_count, avg_price
    FROM dp_shop_metrics
    WHERE crawl_date = :stat_date
    """
    with client.engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), {"stat_date": stat_date}).mappings().all()]
    if not rows:
        return []

    # 全城基准：C = 评价数加权平均评分；m = 评价数中位数
    scored = [r for r in rows if r["score"] is not None and r["review_count"]]
    if scored:
        total_sv = sum(float(r["score"]) * r["review_count"] for r in scored)
        total_v = sum(r["review_count"] for r in scored)
        c = total_sv / total_v
    else:
        c = 0.0
    m = statistics.median([r["review_count"] or 0 for r in rows]) or 1.0

    indicators = []
    for r in rows:
        v = r["review_count"] or 0
        score = float(r["score"]) if r["score"] is not None else None
        weighted = round(bayesian_weight(score, v, c, m), 3) if score is not None else None
        indicators.append({
            "stat_date": stat_date,
            "city": r["city"],
            "mall_name": r["mall_name"],
            "entity_type": "shop",
            "entity_name": r["shop_name"],
            "brand_id": r["brand_id"],
            "weighted_score": weighted,
            "detail": {
                "metric": "bayesian_weighted_score",
                "R": score, "v": v, "C": round(c, 3), "m": m,
                "formula": "WR=(v/(v+m))*R+(m/(v+m))*C",
            },
        })

    logger.info(f"[口碑] {stat_date} 计算 {len(indicators)} 家门店，C={c:.3f}, m={m}")
    return indicators
