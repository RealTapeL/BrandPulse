"""告警 API：CRUD + 手动触发检查。

周期性检查由独立的 ``brandpulse.alerts.runner`` 进程负责；本 API 只提供
规则管理和显式的立即检查入口。
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from brandpulse.alerts.models import (
    TRUSTED_SCOPE_METRICS,
    AlertCreate,
    AlertResponse,
    AlertUpdate,
)
from brandpulse.alerts.scheduler import check_all_alerts
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_ALERT_SELECT = """
    SELECT alert.*,
           COALESCE(policy.cooldown_minutes, 60) AS cooldown_minutes,
           COALESCE(policy.notify_recovery, TRUE) AS notify_recovery,
           trusted_rule.scope_id,
           CASE WHEN trusted_rule.alert_id IS NULL THEN 'legacy_unscoped'
                ELSE 'trusted_scope' END AS rule_scope_status
    FROM alerts AS alert
    LEFT JOIN alert_delivery_policies AS policy ON policy.alert_id = alert.id
    LEFT JOIN trusted_alert_rules AS trusted_rule ON trusted_rule.alert_id = alert.id
"""


def _row_to_alert(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "scope_id": row["scope_id"],
        "brand_id": row["brand_id"],
        "metric": row["metric"],
        "operator": row["operator"],
        "threshold": float(row["threshold"]),
        "destinations": row["destinations"] or [],
        "enabled": row["enabled"],
        "cooldown_minutes": row["cooldown_minutes"],
        "notify_recovery": row["notify_recovery"],
        "rule_scope_status": row["rule_scope_status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _scope_or_404(scope_id: str) -> Dict[str, Any]:
    scope = TrustedScopeRepository().get(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="监测范围不存在")
    return scope


def _validate_scope_metric(scope_id: Optional[str], metric: str) -> None:
    if scope_id and metric not in TRUSTED_SCOPE_METRICS:
        raise HTTPException(
            status_code=422,
            detail=("可信范围告警只能使用快照指标：" + ", ".join(sorted(TRUSTED_SCOPE_METRICS))),
        )


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
    scope = _scope_or_404(payload.scope_id) if payload.scope_id else None
    _validate_scope_metric(payload.scope_id, payload.metric)
    client = PostgresClient()
    try:
        with client.engine.begin() as conn:
            row = conn.execute(text(sql), {
                "name": payload.name,
                # 旧表保留数据集键兼容字段；可信调度只使用 trusted_alert_rules.scope_id。
                "brand_id": scope["brand_id"] if scope else payload.brand_id,
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
            if scope:
                conn.execute(text("""
                    INSERT INTO trusted_alert_rules (alert_id, scope_id, metric_key)
                    VALUES (:alert_id, :scope_id, :metric_key)
                """), {
                    "alert_id": row[0], "scope_id": scope["scope_id"], "metric_key": payload.metric,
                })
            created = conn.execute(
                text(_ALERT_SELECT + " WHERE alert.id = :id"), {"id": row[0]}
            ).mappings().one()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"创建告警失败: {e}") from e

    return AlertResponse(**_row_to_alert(created))


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
                   alert.name AS alert_name,
                   evaluation.scope_id, evaluation.snapshot_id, evaluation.metric_key,
                   evaluation.metric_quality, evaluation.evidence AS metric_evidence
            FROM alert_history AS history
            JOIN alerts AS alert ON alert.id = history.alert_id
            LEFT JOIN alert_delivery_events AS event ON event.history_id = history.id
            LEFT JOIN trusted_alert_evaluations AS evaluation ON evaluation.history_id = history.id
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
                   COALESCE(event.notification_status, 'not_requested') AS notification_status,
                   evaluation.scope_id, evaluation.snapshot_id, evaluation.metric_key,
                   evaluation.metric_quality, evaluation.evidence AS metric_evidence
            FROM alert_history AS history
            LEFT JOIN alert_delivery_events AS event ON event.history_id = history.id
            LEFT JOIN trusted_alert_evaluations AS evaluation ON evaluation.history_id = history.id
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
    scope_is_updated = "scope_id" in data
    requested_scope_id = data.pop("scope_id", None)
    alert_data = {key: value for key, value in data.items() if key not in policy_fields}
    policy_data = {key: value for key, value in data.items() if key in policy_fields}

    client = PostgresClient()
    with client.engine.begin() as conn:
        current = conn.execute(
            text(_ALERT_SELECT + " WHERE alert.id = :id"), {"id": alert_id}
        ).mappings().first()
        if not current:
            raise HTTPException(status_code=404, detail="告警不存在")
        target_scope_id = requested_scope_id if scope_is_updated else current["scope_id"]
        target_metric = alert_data.get("metric", current["metric"])
        _validate_scope_metric(target_scope_id, target_metric)
        scope = _scope_or_404(target_scope_id) if target_scope_id else None
        # 可信规则的旧 brand_id 只保持兼容投影，不能被请求参数改写为实际筛选条件。
        if scope:
            alert_data["brand_id"] = scope["brand_id"]
        updates = []
        params = {"id": alert_id}
        for key, value in alert_data.items():
            if key == "destinations":
                # payload.model_dump() 已经递归地把 AlertDestination 转成 dict。
                value = json.dumps(value)
            updates.append(f"{key} = :{key}")
            params[key] = value
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
        if scope_is_updated:
            if scope:
                conn.execute(text("""
                    INSERT INTO trusted_alert_rules (alert_id, scope_id, metric_key)
                    VALUES (:alert_id, :scope_id, :metric_key)
                    ON CONFLICT (alert_id) DO UPDATE SET
                        scope_id = EXCLUDED.scope_id,
                        metric_key = EXCLUDED.metric_key,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "alert_id": alert_id, "scope_id": scope["scope_id"], "metric_key": target_metric,
                })
            else:
                conn.execute(text("DELETE FROM trusted_alert_rules WHERE alert_id = :id"), {"id": alert_id})
        elif current["scope_id"] and "metric" in alert_data:
            conn.execute(text("""
                UPDATE trusted_alert_rules
                SET metric_key = :metric_key, updated_at = CURRENT_TIMESTAMP
                WHERE alert_id = :alert_id
            """), {"alert_id": alert_id, "metric_key": target_metric})
        if scope_is_updated or set(alert_data) & {
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
