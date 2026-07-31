"""
告警 API：CRUD + 手动触发检查。
TODO: 接入 lifespan 后自动启动 APScheduler。
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from brandpulse.alerts.models import AlertCreate, AlertResponse, AlertUpdate
from brandpulse.alerts.scheduler import check_all_alerts
from brandpulse.db_clients.postgres_client import PostgresClient

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _row_to_alert(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "brand_id": row["brand_id"],
        "metric": row["metric"],
        "operator": row["operator"],
        "threshold": float(row["threshold"]),
        "destinations": row["destinations"] or [],
        "enabled": row["enabled"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("", response_model=AlertResponse)
def create_alert(payload: AlertCreate):
    sql = """
        INSERT INTO alerts (name, brand_id, metric, operator, threshold, destinations, enabled)
        VALUES (:name, :brand_id, :metric, :operator, :threshold, :destinations, :enabled)
        RETURNING id, created_at, updated_at
    """
    client = PostgresClient()
    try:
        result = client.execute(sql, {
            "name": payload.name,
            "brand_id": payload.brand_id,
            "metric": payload.metric,
            "operator": payload.operator,
            "threshold": payload.threshold,
            "destinations": json.dumps([d.model_dump() for d in payload.destinations]),
            "enabled": payload.enabled,
        })
        row = result.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建告警失败: {e}") from e

    return AlertResponse(
        **payload.model_dump(),
        id=row[0],
        created_at=row[1],
        updated_at=row[2],
    )


@router.get("", response_model=List[AlertResponse])
def list_alerts(enabled: Optional[bool] = None):
    sql = "SELECT * FROM alerts"
    params = {}
    if enabled is not None:
        sql += " WHERE enabled = :enabled"
        params["enabled"] = enabled
    sql += " ORDER BY id DESC"

    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [_row_to_alert(r) for r in rows]


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int):
    client = PostgresClient()
    with client.engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM alerts WHERE id = :id"), {"id": alert_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="告警不存在")
    return _row_to_alert(row)


@router.put("/{alert_id}", response_model=AlertResponse)
def update_alert(alert_id: int, payload: AlertUpdate):
    updates = []
    params = {"id": alert_id}
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新字段")
    for k, v in data.items():
        if k == "destinations":
            v = json.dumps([d.model_dump() for d in v])
        updates.append(f"{k} = :{k}")
        params[k] = v
    updates.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE alerts SET {', '.join(updates)} WHERE id = :id RETURNING *"

    client = PostgresClient()
    with client.engine.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="告警不存在")
    return _row_to_alert(row)


@router.delete("/{alert_id}")
def delete_alert(alert_id: int):
    client = PostgresClient()
    result = client.execute("DELETE FROM alerts WHERE id = :id RETURNING id", {"id": alert_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="告警不存在")
    return {"deleted": True}


@router.post("/check-now")
def check_now():
    """立即执行一次告警检查，返回触发数。"""
    try:
        triggered = check_all_alerts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"告警检查失败: {e}") from e
    return {"triggered": triggered}
