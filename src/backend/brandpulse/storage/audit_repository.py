"""不可变 API 操作审计台账。"""

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class AuditRepository:
    def __init__(self):
        self.client = PostgresClient()

    def record(self, event: Dict[str, Any]) -> None:
        with self.client.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO audit_events (
                    event_id, request_id, actor_id, actor_role, action,
                    method, route, request_path, status_code, outcome,
                    client_ip, duration_ms, details
                ) VALUES (
                    :event_id, :request_id, :actor_id, :actor_role, :action,
                    :method, :route, :request_path, :status_code, :outcome,
                    :client_ip, :duration_ms, CAST(:details AS jsonb)
                )
            """), {
                **event,
                "details": json.dumps(event.get("details") or {}, ensure_ascii=False),
            })

    def list(
        self,
        *,
        actor_id: Optional[str],
        method: Optional[str],
        outcome: Optional[str],
        action: Optional[str],
        request_id: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        exact_filters = {
            "actor_id": actor_id,
            "method": method.upper() if method else None,
            "outcome": outcome,
            "request_id": request_id,
        }
        for column, value in exact_filters.items():
            if value:
                conditions.append(f"{column} = :{column}")
                params[column] = value
        if action:
            conditions.append("action ILIKE :action")
            params["action"] = f"%{action}%"
        where = " AND ".join(conditions)
        with self.client.engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM audit_events WHERE {where}"), params
            ).scalar_one()
            rows = conn.execute(text(f"""
                SELECT event_id, request_id, actor_id, actor_role, action,
                       method, route, request_path, status_code, outcome,
                       client_ip, duration_ms, details, created_at
                FROM audit_events
                WHERE {where}
                ORDER BY created_at DESC, event_id DESC
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["duration_ms"] = float(item["duration_ms"])
            item["created_at"] = str(item["created_at"])
            items.append(item)
        return {"items": items, "total": int(total)}
