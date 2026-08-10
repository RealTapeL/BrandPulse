"""按真实项目/品类监测范围聚合看板数据。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository

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


def _resolve_scope(scope_id: Optional[str]) -> Optional[Dict[str, Any]]:
    repository = MonitoringScopeRepository()
    if scope_id:
        scope = repository.get(scope_id)
        if not scope:
            raise ValueError("监测项目不存在")
        return scope
    scopes = repository.list()
    if not scopes:
        return None
    # 默认优先选择确实已有指标数据的范围，避免返回一个空的历史任务范围。
    return next((scope for scope in scopes if scope.get("latest_indicator_date")), scopes[0])


def _scope_params(scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not scope:
        return {}
    return {
        "brand_id": scope["brand_id"],
        "city": scope["city"],
        "mall_name": scope["mall_name"],
    }


def _scope_clause(prefix: str = "") -> str:
    return (
        f"{prefix}brand_id = :brand_id "
        f"AND {prefix}city = :city "
        f"AND {prefix}mall_name = :mall_name"
    )


def build_dashboard(scope_id: Optional[str] = None) -> Dict[str, Any]:
    """读取一个明确项目/品类范围内的最新真实数据快照。"""
    scope = _resolve_scope(scope_id)
    client = PostgresClient()
    params = _scope_params(scope)
    if scope:
        indicator_filter = _scope_clause()
        dp_filter = "brand_id = :brand_id AND city = :city AND place = :mall_name"
        xhs_filter = "brand_id = :brand_id AND city = :city AND COALESCE(mall_name, '') = :mall_name"
    else:
        indicator_filter = "entity_type = 'shop'"
        dp_filter = "1=1"
        xhs_filter = "1=1"

    stat_row = _query(
        client,
        f"SELECT MAX(stat_date) AS d FROM brand_indicators_daily WHERE {indicator_filter}",
        params,
    )
    stat_date = stat_row[0]["d"] if stat_row else None
    indicators = []
    if stat_date:
        indicators = _query(
            client,
            f"""
            SELECT entity_name, weighted_score, heat_index, sov, wow_momentum, volatility, detail
            FROM brand_indicators_daily
            WHERE {indicator_filter} AND stat_date = :stat_date AND entity_type = 'shop'
            ORDER BY weighted_score DESC NULLS LAST, entity_name
            """,
            {**params, "stat_date": stat_date},
        )

    crawl_row = _query(
        client,
        f"SELECT MAX(crawl_date) AS d FROM dp_shop_metrics WHERE {dp_filter}",
        params,
    )
    crawl_date = crawl_row[0]["d"] if crawl_row else None
    dp_shops = []
    if crawl_date:
        dp_shops = _query(
            client,
            f"""
            SELECT shop_name, score, review_count, avg_price, business_area, place, source_url
            FROM dp_shop_metrics
            WHERE {dp_filter} AND crawl_date = :crawl_date
            ORDER BY score DESC NULLS LAST, review_count DESC NULLS LAST, shop_name
            """,
            {**params, "crawl_date": crawl_date},
        )

    xhs_notes = _query(
        client,
        f"""
        SELECT title, author_name, likes, publish_time, note_url, crawl_date
        FROM xhs_notes
        WHERE {xhs_filter}
        ORDER BY likes DESC NULLS LAST, crawl_date DESC
        LIMIT 100
        """,
        params,
    )
    logger.info(
        "[看板] scope=%s stat_date=%s crawl_date=%s indicators=%s dp_shops=%s xhs_notes=%s",
        scope["scope_id"] if scope else None,
        stat_date,
        crawl_date,
        len(indicators),
        len(dp_shops),
        len(xhs_notes),
    )
    return {
        "scope": scope,
        "stat_date": str(stat_date) if stat_date else None,
        "crawl_date": str(crawl_date) if crawl_date else None,
        "indicators": to_jsonable(indicators),
        "dp_shops": to_jsonable(dp_shops),
        "xhs_notes": to_jsonable(xhs_notes),
    }


@router.get("/api/v1/dashboard/scopes")
def dashboard_scopes() -> Dict[str, Any]:
    """返回由真实采集任务和数据表登记的项目/品类范围。"""
    return {"items": MonitoringScopeRepository().list()}


@router.get("/api/v1/dashboard")
@router.get("/api/dashboard", include_in_schema=False)
def dashboard(scope_id: Optional[str] = Query(default=None, max_length=64)) -> Dict[str, Any]:
    try:
        return build_dashboard(scope_id=scope_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
