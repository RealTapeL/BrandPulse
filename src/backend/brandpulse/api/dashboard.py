"""按真实项目/品类监测范围聚合看板数据。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.trusted_data_repository import SnapshotRepository

logger = get_logger(__name__)
router = APIRouter(tags=["dashboard"])


def to_jsonable(rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """将 PostgreSQL decimal/date 等值转换为 API JSON 标量。"""
    def convert(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "as_tuple"):
            return float(value)
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return str(value)

    output = []
    for row in rows:
        output.append({key: convert(value) for key, value in row.items()})
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


def build_dashboard(
    scope_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """读取一个范围内明确绑定的可信快照。

    旧表的 ``brand_id + city + mall`` 组合不再作为范围条件，避免遗漏 category
    后混入其他品类。Phase 2 指标重算完成前不返回旧指标表的混合结果。
    """
    scope = _resolve_scope(scope_id)
    if not scope:
        return {
            "scope": None,
            "snapshot": None,
            "stat_date": None,
            "crawl_date": None,
            "indicators": [],
            "dp_shops": [],
            "xhs_notes": [],
            "data_status": "unavailable",
            "message": "尚未登记可信监测范围",
        }
    client = PostgresClient()
    snapshots = SnapshotRepository()
    snapshot = snapshots.get(snapshot_id) if snapshot_id else snapshots.latest_released(scope["scope_id"])
    if snapshot and snapshot["scope_id"] != scope["scope_id"]:
        raise ValueError("数据快照不属于当前监测范围")
    if snapshot and snapshot["status"] not in {"ready", "published"}:
        raise ValueError("当前快照不可用于正式看板")
    if not snapshot:
        return {
            "scope": scope,
            "snapshot": None,
            "stat_date": None,
            "crawl_date": None,
            "indicators": [],
            "dp_shops": [],
            "xhs_notes": [],
            "data_status": "unavailable",
            "message": "当前范围没有 ready 或 published 的可信快照",
        }

    params = {"scope_id": scope["scope_id"], "collection_run_id": snapshot["collection_run_id"]}
    dp_shops = _query(
        client,
        """
        SELECT payload ->> 'shop_name' AS shop_name,
               source_record_key,
               entity_mapping_status,
               brand_id,
               store_id,
               NULLIF(payload ->> 'score', '')::numeric AS score,
               NULLIF(payload ->> 'review_count', '')::int AS review_count,
               NULLIF(payload ->> 'avg_price', '')::numeric AS avg_price,
               payload ->> 'business_area' AS business_area,
               payload ->> 'place' AS place,
               source_url,
               observed_date AS crawl_date
        FROM raw_observations
        WHERE scope_id = :scope_id
          AND collection_run_id = :collection_run_id
          AND source_name = 'dianping_webbridge'
          AND record_type = 'dp_shop_metric'
          AND quality_status = 'accepted'
        ORDER BY NULLIF(payload ->> 'score', '')::numeric DESC NULLS LAST,
                 NULLIF(payload ->> 'review_count', '')::int DESC NULLS LAST,
                 payload ->> 'shop_name'
        """,
        params,
    )
    xhs_notes = _query(
        client,
        """
        SELECT payload ->> 'title' AS title,
               payload ->> 'author_name' AS author_name,
               NULLIF(payload ->> 'likes', '')::int AS likes,
               payload ->> 'publish_time' AS publish_time,
               source_url AS note_url,
               observed_date AS crawl_date
        FROM raw_observations
        WHERE scope_id = :scope_id
          AND collection_run_id = :collection_run_id
          AND source_name = 'xiaohongshu_webbridge'
          AND record_type = 'xhs_note'
          AND quality_status = 'accepted'
        ORDER BY NULLIF(payload ->> 'likes', '')::int DESC NULLS LAST, observed_date DESC
        LIMIT 100
        """,
        params,
    )
    metric_rows = _query(
        client,
        """
        SELECT entity_key,
               MAX(value) FILTER (WHERE metric_key = 'bayesian_reputation') AS weighted_score,
               MAX(value) FILTER (WHERE metric_key = 'dianping_review_share') AS sov,
               MAX(quality_status) FILTER (WHERE metric_key = 'bayesian_reputation') AS reputation_quality,
               (ARRAY_AGG(evidence) FILTER (WHERE metric_key = 'bayesian_reputation'))[1] AS reputation_evidence,
               (ARRAY_AGG(evidence) FILTER (WHERE metric_key = 'dianping_review_share'))[1] AS share_evidence
        FROM metric_observations
        WHERE snapshot_id = :snapshot_id
          AND entity_type = 'shop'
          AND source_name = 'dianping_webbridge'
        GROUP BY entity_key
        """,
        {"snapshot_id": snapshot["snapshot_id"]},
    )
    metric_by_record = {str(row["entity_key"]): row for row in metric_rows}
    indicators = []
    for shop in dp_shops:
        metric = metric_by_record.get(str(shop["source_record_key"]))
        if not metric:
            continue
        indicators.append({
            "entity_name": shop["shop_name"],
            "entity_type": "shop_observation",
            "entity_mapping_status": shop.get("entity_mapping_status"),
            "brand_id": shop.get("brand_id"),
            "store_id": shop.get("store_id"),
            "review_count": shop.get("review_count"),
            "weighted_score": metric.get("weighted_score"),
            # 已废弃的旧综合热度字段在兼容输出中显式保持空值。前端不得将其转成 0。
            "heat_index": None,
            "sov": metric.get("sov"),
            "wow_momentum": None,
            "volatility": None,
            "detail": {
                "snapshot_id": snapshot["snapshot_id"],
                "metric_version": "snapshot-v2",
                "reputation_quality": metric.get("reputation_quality"),
                "reputation_evidence": metric.get("reputation_evidence") or {},
                "share_evidence": metric.get("share_evidence") or {},
            },
        })
    scope_metrics = _query(
        client,
        """
        SELECT metric_key, value, unit, quality_status, evidence
        FROM metric_observations
        WHERE snapshot_id = :snapshot_id
          AND entity_type = 'scope'
        ORDER BY metric_key
        """,
        {"snapshot_id": snapshot["snapshot_id"]},
    )
    stat_date = snapshot.get("observed_at")
    crawl_date = max((row.get("crawl_date") for row in dp_shops if row.get("crawl_date")), default=None)
    logger.info(
        "[看板] scope=%s snapshot=%s stat_date=%s indicators=%s dp_shops=%s xhs_notes=%s",
        scope["scope_id"],
        snapshot["snapshot_id"],
        stat_date,
        len(indicators),
        len(dp_shops),
        len(xhs_notes),
    )
    return {
        "scope": scope,
        "snapshot": snapshot,
        "stat_date": str(stat_date) if stat_date else None,
        "crawl_date": str(crawl_date) if crawl_date else None,
        "indicators": to_jsonable(indicators),
        "dp_shops": to_jsonable(dp_shops),
        "xhs_notes": to_jsonable(xhs_notes),
        "metric_summary": to_jsonable(scope_metrics),
        "source_results": snapshot.get("source_results", []),
        "data_status": "ready",
        "message": (
            "当前为点评单源快照；跨来源综合指标未计算。"
            if snapshot.get("data_mode") == "dianping_single_source"
            else "当前数据来自已发布/就绪快照。"
        ),
    }


@router.get("/api/v1/dashboard/scopes")
def dashboard_scopes() -> Dict[str, Any]:
    """返回由真实采集任务和数据表登记的项目/品类范围。"""
    return {"items": MonitoringScopeRepository().list()}


@router.get("/api/v1/dashboard")
@router.get("/api/dashboard", include_in_schema=False)
def dashboard(
    scope_id: Optional[str] = Query(default=None, max_length=64),
    snapshot_id: Optional[str] = Query(default=None, max_length=64),
) -> Dict[str, Any]:
    try:
        return build_dashboard(scope_id=scope_id, snapshot_id=snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
