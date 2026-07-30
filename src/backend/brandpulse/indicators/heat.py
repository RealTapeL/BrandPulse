"""
热度指标：对数加权热度指数（0~100）

点赞/评价数是长尾分布，先取 log 再加权，避免爆款绑架指数。

关键设计：用**固定参考值**归一，而不是组内 min-max。
组内归一化会让"当天最高值永远是 100"，跨天不可比，动量也就没法算；
固定基准下指数跨天、跨商场都可比。

门店级：heat = 100 * ln(1+review_count) / ln(1+REVIEW_REF)
商场级：heat = 100 * (w1*ln(1+dp_review) + w2*ln(1+likes) + w3*ln(1+mentions) + w4*ln(1+shops)) / RAW_REF
"""
import math
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

# ---- 可调权重与参考基准（以后用历史数据回归校准） ----
W_DP_REVIEW = 0.35   # 点评评价数
W_XHS_LIKES = 0.35   # 小红书点赞总量
W_XHS_MENTIONS = 0.15  # 小红书提及量
W_DP_SHOPS = 0.15    # 点评门店数

# 参考基准：评价数 5 万 / 点赞 1 万 / 提及 50 条 / 门店 20 家 视为"满分热度"
REVIEW_REF = 50000
_LIKES_REF = 10000
_MENTIONS_REF = 50
_SHOPS_REF = 20
RAW_REF = (
    W_DP_REVIEW * math.log1p(REVIEW_REF)
    + W_XHS_LIKES * math.log1p(_LIKES_REF)
    + W_XHS_MENTIONS * math.log1p(_MENTIONS_REF)
    + W_DP_SHOPS * math.log1p(_SHOPS_REF)
)


def shop_heat(review_count: int) -> float:
    """门店级热度纯函数（0~100，便于单测）"""
    return min(100.0, 100.0 * math.log1p(max(review_count, 0)) / math.log1p(REVIEW_REF))


def mall_heat(dp_review_count: int, total_likes: int, mentions: int, dp_shop_count: int) -> float:
    """商场×品类级热度纯函数（0~100，便于单测）"""
    raw = (
        W_DP_REVIEW * math.log1p(max(dp_review_count, 0))
        + W_XHS_LIKES * math.log1p(max(total_likes, 0))
        + W_XHS_MENTIONS * math.log1p(max(mentions, 0))
        + W_DP_SHOPS * math.log1p(max(dp_shop_count, 0))
    )
    return min(100.0, 100.0 * raw / RAW_REF)


def _latest_crawl_date(client: PostgresClient) -> Optional[str]:
    with client.engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(crawl_date) FROM dp_shop_metrics")).first()
        return str(row[0]) if row and row[0] else None


def compute_heat(stat_date: Optional[str] = None) -> List[Dict]:
    """
    计算热度指数：门店级（点评评价数）+ 商场级（brand_heat_daily 双平台）。

    Returns:
        指标行列表（entity_type='shop' / 'mall'）
    """
    client = PostgresClient()
    if not stat_date:
        stat_date = _latest_crawl_date(client)
    if not stat_date:
        logger.warning("无数据，跳过热度指标")
        return []

    indicators = []

    # ---- 门店级 ----
    sql = """
    SELECT shop_name, city, COALESCE(place, '') AS mall_name, brand_id, review_count
    FROM dp_shop_metrics
    WHERE crawl_date = :stat_date
    """
    with client.engine.connect() as conn:
        shops = [dict(r) for r in conn.execute(text(sql), {"stat_date": stat_date}).mappings().all()]
    for r in shops:
        v = r["review_count"] or 0
        indicators.append({
            "stat_date": stat_date,
            "city": r["city"],
            "mall_name": r["mall_name"],
            "entity_type": "shop",
            "entity_name": r["shop_name"],
            "brand_id": r["brand_id"],
            "heat_index": round(shop_heat(v), 2),
            "detail": {"metric": "shop_heat", "review_count": v, "review_ref": REVIEW_REF},
        })

    # ---- 商场×品类级（brand_heat_daily 双平台汇总） ----
    sql = """
    SELECT city, mall_name, brand_id,
           COALESCE(SUM(dp_review_count), 0) AS dp_review_count,
           COALESCE(SUM(total_likes), 0) AS total_likes,
           COALESCE(SUM(mentions), 0) AS mentions,
           COALESCE(SUM(dp_shop_count), 0) AS dp_shop_count
    FROM brand_heat_daily
    WHERE stat_date = :stat_date
    GROUP BY city, mall_name, brand_id
    """
    with client.engine.connect() as conn:
        malls = [dict(r) for r in conn.execute(text(sql), {"stat_date": stat_date}).mappings().all()]
    for r in malls:
        indicators.append({
            "stat_date": stat_date,
            "city": r["city"],
            "mall_name": r["mall_name"] or "",
            "entity_type": "mall",
            "entity_name": r["mall_name"] or "(全城)",
            "brand_id": r["brand_id"],
            "heat_index": round(mall_heat(
                int(r["dp_review_count"]), int(r["total_likes"]),
                int(r["mentions"]), int(r["dp_shop_count"]),
            ), 2),
            "detail": {
                "metric": "mall_heat",
                "dp_review_count": int(r["dp_review_count"]),
                "total_likes": int(r["total_likes"]),
                "mentions": int(r["mentions"]),
                "dp_shop_count": int(r["dp_shop_count"]),
                "weights": {
                    "dp_review": W_DP_REVIEW, "xhs_likes": W_XHS_LIKES,
                    "xhs_mentions": W_XHS_MENTIONS, "dp_shops": W_DP_SHOPS,
                },
            },
        })

    logger.info(f"[热度] {stat_date} 计算 {len(shops)} 家门店 + {len(malls)} 个商场级指标")
    return indicators
