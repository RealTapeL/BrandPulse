"""告警 API：CRUD + 手动触发检查。

周期性检查由独立的 ``brandpulse.alerts.runner`` 进程负责；本 API 只提供
规则管理和显式的立即检查入口。
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from brandpulse.alerts.models import AlertCreate, AlertResponse, AlertUpdate
from brandpulse.alerts.scheduler import check_all_alerts
from brandpulse.db_clients.postgres_client import PostgresClient

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_ALERT_SELECT = """
    SELECT alert.*,
           COALESCE(policy.cooldown_minutes, 60) AS cooldown_minutes,
           COALESCE(policy.notify_recovery, TRUE) AS notify_recovery
    FROM alerts AS alert
    LEFT JOIN alert_delivery_policies AS policy ON policy.alert_id = alert.id
"""


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
        "cooldown_minutes": row["cooldown_minutes"],
        "notify_recovery": row["notify_recovery"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("", response_model=AlertResponse)
def create_alert(payload: AlertCreate):
    sql = """
        INSERT INTO alerts (
            name, brand_id, metric, operator, threshold, destinations, enabled
        ) VALUES (
            :name, :brand_id, :metric, :operator, :threshold, :destinations, :enabled
        )
        RETURNING id, created_at, updated_at
    """
    client = PostgresClient()
    try:
        with client.engine.begin() as conn:
            row = conn.execute(text(sql), {
                "name": payload.name,
                "brand_id": payload.brand_id,
                "metric": payload.metric,
                "operator": payload.operator,
                "threshold": payload.threshold,
                "destinations": json.dumps([d.model_dump() for d in payload.destinations]),
                "enabled": payload.enabled,
            }).first()
            conn.execute(text("""
                INSERT INTO alert_delivery_policies (
                    alert_id, cooldown_minutes, notify_recovery
                ) VALUES (
                    :alert_id, :cooldown_minutes, :notify_recovery
                )
            """), {
                "alert_id": row[0],
                "cooldown_minutes": payload.cooldown_minutes,
                "notify_recovery": payload.notify_recovery,
            })
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
    sql = _ALERT_SELECT
    params = {}
    if enabled is not None:
        sql += " WHERE alert.enabled = :enabled"
        params["enabled"] = enabled
    sql += " ORDER BY alert.id DESC"

    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [_row_to_alert(r) for r in rows]


@router.get("/history")
def list_alert_history(limit: int = 100):
    """返回真实告警检查历史，包括未触发检查，便于校准阈值。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT history.id, history.alert_id, history.checked_at, history.triggered,
                   history.metric_value, history.message, history.sent_log,
                   COALESCE(event.event_type, 'check') AS event_type,
                   COALESCE(event.notification_status, 'not_requested') AS notification_status,
                   alert.name AS alert_name
            FROM alert_history AS history
            JOIN alerts AS alert ON alert.id = history.alert_id
            LEFT JOIN alert_delivery_events AS event ON event.history_id = history.id
            ORDER BY history.checked_at DESC, history.id DESC
            LIMIT :limit
        """), {"limit": min(max(limit, 1), 200)}).mappings().all()
    output = []
    for row in rows:
        item = dict(row)
        item["checked_at"] = str(item["checked_at"])
        item["metric_value"] = float(item["metric_value"]) if item["metric_value"] is not None else None
        item["sent_log"] = item.get("sent_log") or []
        output.append(item)
    return {"items": output}


@router.get("/deliveries/list")
def list_alert_deliveries(
    alert_id: Optional[int] = None,
    limit: int = 100,
):
    """查看真实通知投递、重试和失败记录。"""
    conditions = ["1=1"]
    params = {"limit": min(max(limit, 1), 200)}
    if alert_id is not None:
        conditions.append("delivery.alert_id = :alert_id")
        params["alert_id"] = alert_id
    client = PostgresClient()
    with client.engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT delivery.delivery_id, delivery.history_id, delivery.alert_id,
                   alert.name AS alert_name, delivery.event_type,
                   delivery.destination_type, delivery.destination_value,
                   delivery.status, delivery.attempt_count, delivery.max_attempts,
                   delivery.next_attempt_at, delivery.last_error, delivery.response,
                   delivery.sent_at, delivery.created_at, delivery.updated_at
            FROM alert_notification_deliveries AS delivery
            JOIN alerts AS alert ON alert.id = delivery.alert_id
            WHERE {' AND '.join(conditions)}
            ORDER BY delivery.created_at DESC, delivery.delivery_id DESC
            LIMIT :limit
        """), params).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/check-now")
def check_now():
    """立即执行一次告警检查，返回触发数。"""
    try:
        triggered = check_all_alerts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"告警检查失败: {e}") from e
    return {"triggered": triggered}


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int):
    client = PostgresClient()
    with client.engine.connect() as conn:
        row = conn.execute(
            text(_ALERT_SELECT + " WHERE alert.id = :id"),
            {"id": alert_id},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="告警不存在")
    return _row_to_alert(row)


@router.get("/{alert_id}/history")
def get_alert_history(alert_id: int, limit: int = 100):
    client = PostgresClient()
    with client.engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM alerts WHERE id = :id"), {"id": alert_id}).first()
        if not exists:
            raise HTTPException(status_code=404, detail="告警不存在")
        rows = conn.execute(text("""
            SELECT history.id, history.alert_id, history.checked_at, history.triggered,
                   history.metric_value, history.message, history.sent_log,
                   COALESCE(event.event_type, 'check') AS event_type,
                   COALESCE(event.notification_status, 'not_requested') AS notification_status
            FROM alert_history AS history
            LEFT JOIN alert_delivery_events AS event ON event.history_id = history.id
            WHERE history.alert_id = :alert_id
            ORDER BY history.checked_at DESC, history.id DESC
            LIMIT :limit
        """), {"alert_id": alert_id, "limit": min(max(limit, 1), 200)}).mappings().all()
    return {"items": [
        {
            **dict(row),
            "checked_at": str(row["checked_at"]),
            "metric_value": float(row["metric_value"]) if row["metric_value"] is not None else None,
            "sent_log": row["sent_log"] or [],
        }
        for row in rows
    ]}


@router.put("/{alert_id}", response_model=AlertResponse)
def update_alert(alert_id: int, payload: AlertUpdate):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新字段")
    policy_fields = {"cooldown_minutes", "notify_recovery"}
    alert_data = {key: value for key, value in data.items() if key not in policy_fields}
    policy_data = {key: value for key, value in data.items() if key in policy_fields}

    updates = []
    params = {"id": alert_id}
    for k, v in alert_data.items():
        if k == "destinations":
            # payload.model_dump() 已经递归地把 AlertDestination 转成 dict。
            v = json.dumps(v)
        updates.append(f"{k} = :{k}")
        params[k] = v

    client = PostgresClient()
    with client.engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM alerts WHERE id = :id"), {"id": alert_id}
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="告警不存在")
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(text(
                f"UPDATE alerts SET {', '.join(updates)} WHERE id = :id"
            ), params)
        if policy_data:
            conn.execute(text("""
                INSERT INTO alert_delivery_policies (alert_id)
                VALUES (:id)
                ON CONFLICT (alert_id) DO NOTHING
            """), {"id": alert_id})
            policy_updates = [f"{key} = :{key}" for key in policy_data]
            policy_updates.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(text(f"""
                UPDATE alert_delivery_policies
                SET {', '.join(policy_updates)}
                WHERE alert_id = :id
            """), {"id": alert_id, **policy_data})
        if set(alert_data) & {
            "brand_id", "metric", "operator", "threshold", "destinations", "enabled"
        }:
            conn.execute(text("DELETE FROM alert_states WHERE alert_id = :id"), {"id": alert_id})
            conn.execute(text("""
                UPDATE alert_notification_deliveries
                SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE alert_id = :id AND status IN ('pending', 'retry', 'sending')
            """), {"id": alert_id})
        row = conn.execute(
            text(_ALERT_SELECT + " WHERE alert.id = :id"), {"id": alert_id}
        ).mappings().one()
    return _row_to_alert(row)


@router.delete("/{alert_id}")
def delete_alert(alert_id: int):
    client = PostgresClient()
    result = client.execute("DELETE FROM alerts WHERE id = :id RETURNING id", {"id": alert_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="告警不存在")
    return {"deleted": True}
