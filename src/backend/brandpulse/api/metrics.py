"""指标定义、快照指标和受控重算 API。"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.indicators.snapshot_metrics import SnapshotMetricService
from brandpulse.storage.trusted_data_repository import SnapshotRepository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    for key, value in list(item.items()):
        if hasattr(value, "as_tuple"):
            item[key] = float(value)
        elif key.endswith("_at") and value is not None:
            item[key] = str(value)
    return item


@router.get("/definitions")
def list_metric_definitions():
    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT * FROM metric_definitions
            WHERE is_active = TRUE
            ORDER BY metric_group, metric_key
        """)).mappings().all()
    return {"items": [_jsonable(dict(row)) for row in rows]}


@router.get("/snapshots/{snapshot_id}")
def list_snapshot_metrics(
    snapshot_id: str,
    entity_type: Optional[str] = Query(default=None, max_length=32),
    metric_key: Optional[str] = Query(default=None, max_length=128),
):
    if not SnapshotRepository().get(snapshot_id):
        raise HTTPException(status_code=404, detail="数据快照不存在")
    conditions = ["snapshot_id = :snapshot_id"]
    params: Dict[str, Any] = {"snapshot_id": snapshot_id}
    if entity_type:
        conditions.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if metric_key:
        conditions.append("metric_key = :metric_key")
        params["metric_key"] = metric_key
    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT * FROM metric_observations
            WHERE {' AND '.join(conditions)}
            ORDER BY entity_type, metric_key, entity_key
        """), params).mappings().all()
    return {"snapshot_id": snapshot_id, "items": [_jsonable(dict(row)) for row in rows]}


@router.post("/snapshots/{snapshot_id}/recalculate")
def recalculate_snapshot_metrics(snapshot_id: str):
    try:
        return SnapshotMetricService().calculate(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
