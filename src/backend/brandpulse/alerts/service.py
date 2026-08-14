"""持久化告警状态机与可靠通知投递。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from brandpulse.alerts.sender import send
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

_EVENT_SUBJECTS = {
    "trigger": "BrandPulse 告警",
    "reminder": "BrandPulse 告警持续提醒",
    "recovery": "BrandPulse 告警恢复",
}


def _event_message(alert: Dict[str, Any], event_type: str, value: Optional[float]) -> str:
    value_text = "无可用值" if value is None else f"{value:.4f}".rstrip("0").rstrip(".")
    threshold = f"{alert['operator']}{alert['threshold']}"
    if event_type == "recovery":
        return (
            f"告警恢复 [{alert['name']}]: {alert['metric']}={value_text}，"
            f"当前已不满足告警阈值 {threshold}"
        )
    if event_type == "reminder":
        return (
            f"告警持续 [{alert['name']}]: {alert['metric']}={value_text}，"
            f"阈值 {threshold}"
        )
    return f"告警 [{alert['name']}]: {alert['metric']}={value_text}，阈值 {threshold}"


def record_evaluation(
    alert: Dict[str, Any],
    *,
    triggered: bool,
    value: Optional[float],
) -> Dict[str, Any]:
    """记录一次检查，并在状态转换时创建幂等的目的地投递记录。"""
    client = PostgresClient()
    with client.engine.begin() as conn:
        # 手动检查和定时检查可能并发；每条规则使用事务级 advisory lock 串行化。
        locked = conn.execute(
            text("SELECT pg_try_advisory_xact_lock(731204, :alert_id)"),
            {"alert_id": int(alert["id"])},
        ).scalar_one()
        if not locked:
            return {"triggered": triggered, "skipped": True, "event_type": "check"}

        conn.execute(text("""
            INSERT INTO alert_states (alert_id)
            VALUES (:alert_id)
            ON CONFLICT (alert_id) DO NOTHING
        """), {"alert_id": alert["id"]})
        state = conn.execute(text("""
            SELECT *, LOCALTIMESTAMP AS checked_now
            FROM alert_states
            WHERE alert_id = :alert_id
            FOR UPDATE
        """), {"alert_id": alert["id"]}).mappings().one()
        now = state["checked_now"]

        event_type = "check"
        notification_status = "not_requested"
        message: Optional[str]
        if value is None:
            message = f"告警 [{alert['name']}] 暂无可用指标值，保持原状态"
        elif triggered:
            if not state["is_active"]:
                event_type = "trigger"
                conn.execute(text("""
                    UPDATE alert_states
                    SET is_active = TRUE,
                        activated_at = :now,
                        last_event_at = :now,
                        last_checked_at = :now,
                        last_value = :value,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE alert_id = :alert_id
                """), {"alert_id": alert["id"], "now": now, "value": value})
            else:
                elapsed_seconds = (
                    (now - state["last_event_at"]).total_seconds()
                    if state["last_event_at"] is not None else None
                )
                cooldown_seconds = int(alert.get("cooldown_minutes") or 60) * 60
                if elapsed_seconds is None or elapsed_seconds >= cooldown_seconds:
                    event_type = "reminder"
                    conn.execute(text("""
                        UPDATE alert_states
                        SET last_event_at = :now,
                            last_checked_at = :now,
                            last_value = :value,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE alert_id = :alert_id
                    """), {"alert_id": alert["id"], "now": now, "value": value})
                else:
                    notification_status = "suppressed"
                    conn.execute(text("""
                        UPDATE alert_states
                        SET last_checked_at = :now,
                            last_value = :value,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE alert_id = :alert_id
                    """), {"alert_id": alert["id"], "now": now, "value": value})
            message = _event_message(alert, event_type if event_type != "check" else "trigger", value)
        else:
            if state["is_active"]:
                conn.execute(text("""
                    UPDATE alert_states
                    SET is_active = FALSE,
                        activated_at = NULL,
                        last_event_at = :now,
                        last_checked_at = :now,
                        last_value = :value,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE alert_id = :alert_id
                """), {"alert_id": alert["id"], "now": now, "value": value})
                if alert.get("notify_recovery", True):
                    event_type = "recovery"
            else:
                conn.execute(text("""
                    UPDATE alert_states
                    SET last_checked_at = :now,
                        last_value = :value,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE alert_id = :alert_id
                """), {"alert_id": alert["id"], "now": now, "value": value})
            message = (
                _event_message(alert, "recovery", value)
                if event_type == "recovery"
                else f"告警 [{alert['name']}] 未触发，当前值={value}"
            )

        destinations = alert.get("destinations") or []
        should_notify = event_type in _EVENT_SUBJECTS and bool(destinations)
        if should_notify:
            notification_status = "queued"
        history_id = conn.execute(text("""
            INSERT INTO alert_history (
                alert_id, triggered, metric_value, message, sent_log
            ) VALUES (
                :alert_id, :triggered, :metric_value, :message, '[]'::jsonb
            )
            RETURNING id
        """), {
            "alert_id": alert["id"],
            "triggered": triggered,
            "metric_value": value,
            "message": message,
        }).scalar_one()
        conn.execute(text("""
            INSERT INTO alert_delivery_events (
                history_id, alert_id, event_type, notification_status
            ) VALUES (
                :history_id, :alert_id, :event_type, :notification_status
            )
        """), {
            "history_id": history_id,
            "alert_id": alert["id"],
            "event_type": event_type,
            "notification_status": notification_status,
        })

        delivery_ids = []
        if should_notify:
            subject = _EVENT_SUBJECTS[event_type]
            for destination in destinations:
                delivery_id = conn.execute(text("""
                    INSERT INTO alert_notification_deliveries (
                        history_id, alert_id, event_type, destination_type,
                        destination_value, subject, message
                    ) VALUES (
                        :history_id, :alert_id, :event_type, :destination_type,
                        :destination_value, :subject, :message
                    )
                    ON CONFLICT (history_id, destination_type, destination_value)
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING delivery_id
                """), {
                    "history_id": history_id,
                    "alert_id": alert["id"],
                    "event_type": event_type,
                    "destination_type": destination["type"],
                    "destination_value": destination["value"],
                    "subject": subject,
                    "message": message,
                }).scalar_one()
                delivery_ids.append(int(delivery_id))
            conn.execute(text("""
                UPDATE alert_history
                SET sent_log = CAST(:sent_log AS jsonb)
                WHERE id = :history_id
            """), {
                "history_id": history_id,
                "sent_log": json.dumps([
                    {"delivery_id": item, "status": "queued"} for item in delivery_ids
                ]),
            })

    return {
        "triggered": triggered,
        "skipped": False,
        "event_type": event_type,
        "history_id": int(history_id),
        "delivery_ids": delivery_ids,
    }


def _refresh_history(conn, history_id: int) -> None:
    rows = conn.execute(text("""
        SELECT delivery_id, destination_type, destination_value, status,
               attempt_count, last_error, response, sent_at
        FROM alert_notification_deliveries
        WHERE history_id = :history_id
        ORDER BY delivery_id
    """), {"history_id": history_id}).mappings().all()
    if not rows:
        return
    statuses = [row["status"] for row in rows]
    if all(status == "sent" for status in statuses):
        notification_status = "sent"
    elif all(status in {"failed", "cancelled"} for status in statuses):
        notification_status = "failed"
    elif any(status == "sent" for status in statuses):
        notification_status = "partial"
    else:
        notification_status = "retrying"
    logs = []
    for row in rows:
        logs.append({
            "delivery_id": int(row["delivery_id"]),
            "type": row["destination_type"],
            "value": row["destination_value"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "error": row["last_error"],
            "sent_at": str(row["sent_at"]) if row["sent_at"] else None,
        })
    conn.execute(text("""
        UPDATE alert_delivery_events
        SET notification_status = :notification_status,
            updated_at = CURRENT_TIMESTAMP
        WHERE history_id = :history_id
    """), {
        "history_id": history_id,
        "notification_status": notification_status,
    })
    conn.execute(text("""
        UPDATE alert_history
        SET sent_log = CAST(:sent_log AS jsonb)
        WHERE id = :history_id
    """), {
        "history_id": history_id,
        "sent_log": json.dumps(logs, ensure_ascii=False),
    })


def process_due_deliveries(limit: int = 100) -> Dict[str, int]:
    """发送到期通知；每个目的地独立指数退避，最多尝试五次。"""
    client = PostgresClient()
    with client.engine.begin() as conn:
        conn.execute(text("""
            UPDATE alert_notification_deliveries
            SET status = 'retry',
                next_attempt_at = CURRENT_TIMESTAMP,
                last_error = COALESCE(last_error, '发送进程中断，自动恢复'),
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'sending'
              AND updated_at < CURRENT_TIMESTAMP - INTERVAL '10 minutes'
        """))

    summary = {"sent": 0, "retry": 0, "failed": 0}
    for _ in range(max(1, min(limit, 500))):
        with client.engine.begin() as conn:
            delivery = conn.execute(text("""
                WITH due AS (
                    SELECT delivery_id
                    FROM alert_notification_deliveries
                    WHERE status IN ('pending', 'retry')
                      AND next_attempt_at <= CURRENT_TIMESTAMP
                    ORDER BY next_attempt_at, delivery_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE alert_notification_deliveries AS delivery
                SET status = 'sending',
                    attempt_count = attempt_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                FROM due
                WHERE delivery.delivery_id = due.delivery_id
                RETURNING delivery.*
            """)).mappings().first()
        if not delivery:
            break

        result = send(
            [{"type": delivery["destination_type"], "value": delivery["destination_value"]}],
            delivery["message"],
            subject=delivery["subject"],
            event_type=delivery["event_type"],
        )
        item = result[0] if result else {"error": "通知发送器未返回结果"}
        success = item.get("status") == "sent"
        with client.engine.begin() as conn:
            if success:
                conn.execute(text("""
                    UPDATE alert_notification_deliveries
                    SET status = 'sent', response = CAST(:response AS jsonb),
                        last_error = NULL, sent_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE delivery_id = :delivery_id
                """), {
                    "delivery_id": delivery["delivery_id"],
                    "response": json.dumps(item, ensure_ascii=False),
                })
                summary["sent"] += 1
            else:
                terminal = delivery["attempt_count"] >= delivery["max_attempts"]
                status = "failed" if terminal else "retry"
                delay_seconds = min(3600, 60 * (2 ** max(delivery["attempt_count"] - 1, 0)))
                conn.execute(text("""
                    UPDATE alert_notification_deliveries
                    SET status = :status,
                        response = CAST(:response AS jsonb),
                        last_error = :last_error,
                        next_attempt_at = CURRENT_TIMESTAMP + (:delay_seconds * INTERVAL '1 second'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE delivery_id = :delivery_id
                """), {
                    "delivery_id": delivery["delivery_id"],
                    "status": status,
                    "response": json.dumps(item, ensure_ascii=False),
                    "last_error": str(item.get("error") or "通知发送失败"),
                    "delay_seconds": delay_seconds,
                })
                summary[status] += 1
            _refresh_history(conn, int(delivery["history_id"]))

    if any(summary.values()):
        logger.info("[alerts] 通知投递完成: %s", summary)
    return summary
