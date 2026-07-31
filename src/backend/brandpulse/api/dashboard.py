"""看板聚合查询；保留旧 URL 作为兼容别名，逻辑只维护一份。"""
from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["dashboard"])


def to_jsonable(rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """将 PostgreSQL decimal/date 等值转换为 API JSON 标量。"""
    output = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if value is None or isinstance(value, (str, int, float, bool)):
                item[key] = value
            elif hasattr(value, "as_tuple"):
                item[key] = float(value)
            else:
                item[key] = str(value)
        output.append(item)
    return output


def _query(client: PostgresClient, sql: str, params: Optional[dict] = None) -> list[Dict[str, Any]]:
    with client.engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]


def build_dashboard() -> Dict[str, Any]:
    """读取最新采集和指标快照，生成看板所需的完整数据。"""
    client = PostgresClient()
    stat_row = _query(client, "SELECT MAX(stat_date) AS d FROM brand_indicators_daily WHERE entity_type = 'shop'")
    stat_date = stat_row[0]["d"] if stat_row else None
    indicators = []
    if stat_date:
        indicators = _query(client, """
            SELECT entity_name, weighted_score, heat_index, sov
            FROM brand_indicators_daily
            WHERE stat_date = :stat_date AND entity_type = 'shop'
            ORDER BY weighted_score DESC NULLS LAST
        """, {"stat_date": stat_date})

    crawl_row = _query(client, "SELECT MAX(crawl_date) AS d FROM dp_shop_metrics")
    crawl_date = crawl_row[0]["d"] if crawl_row else None
    dp_shops = []
    if crawl_date:
        dp_shops = _query(client, """
            SELECT shop_name, score, review_count, avg_price, business_area, place
            FROM dp_shop_metrics
            WHERE crawl_date = :crawl_date
            ORDER BY score DESC NULLS LAST, review_count DESC NULLS LAST
        """, {"crawl_date": crawl_date})

    xhs_notes = _query(client, """
        SELECT title, author_name, likes, publish_time
        FROM xhs_notes
        ORDER BY likes DESC NULLS LAST
        LIMIT 100
    """)
    logger.info("[看板] stat_date=%s crawl_date=%s indicators=%s dp_shops=%s xhs_notes=%s",
                stat_date, crawl_date, len(indicators), len(dp_shops), len(xhs_notes))
    return {
        "stat_date": str(stat_date) if stat_date else None,
        "crawl_date": str(crawl_date) if crawl_date else None,
        "indicators": to_jsonable(indicators),
        "dp_shops": to_jsonable(dp_shops),
        "xhs_notes": to_jsonable(xhs_notes),
    }


@router.get("/api/v1/dashboard")
@router.get("/api/dashboard", include_in_schema=False)
def dashboard() -> Dict[str, Any]:
    return build_dashboard()
