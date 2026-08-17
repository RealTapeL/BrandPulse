"""把可信来源对象转为可分派的业务事项，不制造不存在的业务结论。"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


CASE_TYPES = {
    "data_quality", "collection_exception", "brand_risk", "operations_risk", "opportunity", "manual",
}
SOURCE_TYPES = {
    "alert_history", "opportunity_signal", "data_quality_issue", "collection_run", "source_run",
    "report_publication", "brand", "store", "manual",
}
CASE_STATUSES = {
    "open", "acknowledged", "investigating", "action_planned", "in_progress", "resolved", "closed",
}
CASE_FEEDBACK = {"pending", "valid", "false_positive", "no_action_required", "data_problem"}
CASE_PRIORITIES = {"critical", "high", "normal", "low"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _row(row: Any) -> Dict[str, Any]:
    item = dict(row)
    for key, value in list(item.items()):
        if isinstance(value, (datetime, date)):
            item[key] = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return item


class BusinessCaseService:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _event(conn, case_id: str, action: str, actor_id: str, note: str, payload: Dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO business_case_events (event_id, case_id, action, actor_id, note, payload)
                VALUES (:event_id, :case_id, :action, :actor_id, :note, CAST(:payload AS jsonb))
                """
            ),
            {
                "event_id": f"case_event_{uuid4().hex}", "case_id": case_id, "action": action,
                "actor_id": actor_id, "note": note, "payload": _json(payload),
            },
        )

    def create(
        self,
        *,
        case_type: str,
        source_type: str,
        source_id: str,
        title: str,
        description: str = "",
        priority: str = "normal",
        scope_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        due_at: Optional[datetime] = None,
        evidence: Optional[Dict[str, Any]] = None,
        external_links: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> Dict[str, Any]:
        if case_type not in CASE_TYPES or source_type not in SOURCE_TYPES:
            raise ValueError("事项类型或来源类型不合法")
        if priority not in CASE_PRIORITIES:
            raise ValueError("事项优先级不合法")
        if not source_id.strip() or not title.strip():
            raise ValueError("事项必须关联来源且包含标题")
        case_id = f"case_{uuid4().hex}"
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO business_cases (
                        case_id, scope_id, case_type, source_type, source_id, title, description,
                        priority, owner_id, due_at, evidence, external_links, created_by
                    ) VALUES (
                        :case_id, :scope_id, :case_type, :source_type, :source_id, :title, :description,
                        :priority, :owner_id, :due_at, CAST(:evidence AS jsonb), CAST(:external_links AS jsonb),
                        :created_by
                    )
                    RETURNING *
                    """
                ),
                {
                    "case_id": case_id, "scope_id": scope_id, "case_type": case_type,
                    "source_type": source_type, "source_id": source_id, "title": title.strip(),
                    "description": description.strip(), "priority": priority, "owner_id": owner_id or None,
                    "due_at": due_at, "evidence": _json(evidence or {}),
                    "external_links": _json(external_links or []), "created_by": created_by,
                },
            ).mappings().one()
            self._event(conn, case_id, "created", created_by, "创建业务事项", {
                "source_type": source_type, "source_id": source_id, "scope_id": scope_id,
            })
            if owner_id:
                self._event(conn, case_id, "assigned", created_by, "创建时分派负责人", {"owner_id": owner_id})
        return _row(row)

    def find_open_by_source(self, source_type: str, source_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM business_cases
                    WHERE source_type = :source_type AND source_id = :source_id
                      AND status NOT IN ('resolved', 'closed')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"source_type": source_type, "source_id": source_id},
            ).mappings().first()
        return _row(row) if row else None

    def create_from_source(
        self,
        *,
        source_type: str,
        source_id: str,
        created_by: str,
        priority: Optional[str] = None,
        owner_id: Optional[str] = None,
        due_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        existing = self.find_open_by_source(source_type, source_id)
        if existing:
            return {**existing, "reused": True}
        source = self._source_context(source_type, source_id)
        return self.create(
            case_type=source["case_type"], source_type=source_type, source_id=source_id,
            title=source["title"], description=source["description"],
            priority=priority or source["priority"], scope_id=source.get("scope_id"),
            owner_id=owner_id, due_at=due_at, evidence=source["evidence"], created_by=created_by,
        )

    def _source_context(self, source_type: str, source_id: str) -> Dict[str, Any]:
        if source_type not in SOURCE_TYPES - {"manual", "brand", "store"}:
            raise ValueError("该来源类型不支持自动创建事项")
        with self.client.engine.connect() as conn:
            if source_type == "opportunity_signal":
                row = conn.execute(text("SELECT * FROM opportunity_signals WHERE signal_id = :id"), {"id": source_id}).mappings().first()
                if row:
                    return {
                        "case_type": "opportunity" if row["signal_class"] == "opportunity" else "data_quality",
                        "title": f"处理信号：{row['entity_name']} · {row['signal_type']}",
                        "description": row["recommended_action"], "priority": "high" if row["signal_class"] == "risk" else "normal",
                        "scope_id": row["scope_id"],
                        "evidence": {"signal_id": source_id, "snapshot_id": row["snapshot_id"], "trigger_rule": row["trigger_rule"], "metric_evidence": row["metric_evidence"], "source_evidence": row["source_evidence"], "quality_grade": row["quality_grade"]},
                    }
            elif source_type == "data_quality_issue":
                row = conn.execute(text("SELECT * FROM data_quality_issues WHERE issue_id = :id"), {"id": source_id}).mappings().first()
                if row:
                    details = row["details"] or {}
                    return {
                        "case_type": "data_quality", "title": f"数据质量：{row['message']}",
                        "description": "请按来源证据核对并完成治理，不要通过猜测补齐实体归属。",
                        "priority": "high" if row["severity"] == "error" else "normal",
                        "scope_id": details.get("scope_id"),
                        "evidence": {"issue_id": source_id, "issue_type": row["issue_type"], "severity": row["severity"], "details": details},
                    }
            elif source_type == "collection_run":
                row = conn.execute(text("SELECT * FROM collection_runs WHERE collection_run_id = :id"), {"id": source_id}).mappings().first()
                if row:
                    return {
                        "case_type": "collection_exception", "title": f"采集任务异常：{row['scope_id']}",
                        "description": row.get("failure_reason") or "请核对来源运行状态和登录/解析异常。",
                        "priority": "high", "scope_id": row["scope_id"],
                        "evidence": {"collection_run_id": source_id, "status": row["status"], "failure_reason": row.get("failure_reason")},
                    }
            elif source_type == "source_run":
                row = conn.execute(text("""
                    SELECT source.*, collection.scope_id
                    FROM source_runs AS source
                    JOIN collection_runs AS collection ON collection.collection_run_id = source.collection_run_id
                    WHERE source.source_run_id = :id
                """), {"id": source_id}).mappings().first()
                if row:
                    return {
                        "case_type": "collection_exception", "title": f"来源采集异常：{row['source_name']}",
                        "description": row.get("failure_reason") or "请核对来源登录态、网络和解析状态。",
                        "priority": "high", "scope_id": row["scope_id"],
                        "evidence": {"source_run_id": source_id, "collection_run_id": row["collection_run_id"], "source_name": row["source_name"], "status": row["status"], "record_count": row["record_count"], "failure_reason": row.get("failure_reason")},
                    }
            elif source_type == "report_publication":
                row = conn.execute(text("SELECT * FROM report_publications WHERE publication_id = :id"), {"id": source_id}).mappings().first()
                if row:
                    return {
                        "case_type": "data_quality", "title": f"报告发布异常：{row['report_id']}",
                        "description": "请核对报告快照、审核状态和分发记录。", "priority": "normal",
                        "scope_id": row["scope_id"],
                        "evidence": {"publication_id": source_id, "report_id": row["report_id"], "status": row["status"], "snapshot_id": row["snapshot_id"]},
                    }
            elif source_type == "alert_history":
                row = conn.execute(text("""
                    SELECT history.*, alert.name AS alert_name, alert.metric, alert.operator, alert.threshold,
                           trusted_rule.scope_id AS rule_scope_id,
                           evaluation.scope_id AS evaluation_scope_id, evaluation.snapshot_id,
                           evaluation.metric_key, evaluation.metric_quality,
                           evaluation.evidence AS metric_evidence
                    FROM alert_history AS history JOIN alerts AS alert ON alert.id = history.alert_id
                    LEFT JOIN trusted_alert_rules AS trusted_rule ON trusted_rule.alert_id = alert.id
                    LEFT JOIN trusted_alert_evaluations AS evaluation ON evaluation.history_id = history.id
                    WHERE history.id = :id
                """), {"id": int(source_id)}).mappings().first()
                if row:
                    return {
                        "case_type": "data_quality" if row["metric"] == "data_freshness_hours" else "brand_risk",
                        "title": f"告警待处理：{row['alert_name']}", "description": row["message"] or "请确认告警有效性并记录处置结果。",
                        "priority": "high" if row["triggered"] else "normal",
                        "scope_id": row["evaluation_scope_id"] or row["rule_scope_id"],
                        "evidence": {
                            "alert_history_id": int(source_id), "alert_id": row["alert_id"],
                            "metric": row["metric"], "metric_key": row["metric_key"] or row["metric"],
                            "metric_value": row["metric_value"], "threshold": f"{row['operator']}{row['threshold']}",
                            "snapshot_id": row["snapshot_id"], "metric_quality": row["metric_quality"],
                            "metric_evidence": row["metric_evidence"] or {},
                        },
                    }
        raise ValueError("来源对象不存在或不支持转为事项")

    def list(self, *, scope_id: Optional[str] = None, status: Optional[str] = None, owner_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        clauses = ["1=1"]
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 200)}
        if scope_id:
            clauses.append("business_case.scope_id = :scope_id"); params["scope_id"] = scope_id
        if status:
            if status not in CASE_STATUSES:
                raise ValueError("事项状态不合法")
            clauses.append("business_case.status = :status"); params["status"] = status
        if owner_id:
            clauses.append("business_case.owner_id = :owner_id"); params["owner_id"] = owner_id
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT business_case.*, COUNT(event.event_id) AS event_count
                FROM business_cases AS business_case
                LEFT JOIN business_case_events AS event ON event.case_id = business_case.case_id
                WHERE {' AND '.join(clauses)}
                GROUP BY business_case.case_id
                ORDER BY CASE business_case.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,
                         business_case.updated_at DESC
                LIMIT :limit
            """), params).mappings().all()
        return {"items": [_row(row) for row in rows]}

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            case = conn.execute(text("SELECT * FROM business_cases WHERE case_id = :case_id"), {"case_id": case_id}).mappings().first()
            if not case:
                return None
            events = conn.execute(text("SELECT * FROM business_case_events WHERE case_id = :case_id ORDER BY created_at DESC"), {"case_id": case_id}).mappings().all()
        return {**_row(case), "events": [_row(event) for event in events]}

    def update(self, case_id: str, *, actor_id: str, status: Optional[str] = None, owner_id: Optional[str] = None, due_at: Optional[datetime] = None, outcome: Optional[str] = None, feedback: Optional[str] = None, rule_adjustment_requested: Optional[bool] = None, note: str = "") -> Optional[Dict[str, Any]]:
        if status and status not in CASE_STATUSES:
            raise ValueError("事项状态不合法")
        if feedback and feedback not in CASE_FEEDBACK:
            raise ValueError("反馈类型不合法")
        updates: Dict[str, Any] = {}
        if status is not None: updates["status"] = status
        if owner_id is not None: updates["owner_id"] = owner_id or None
        if due_at is not None: updates["due_at"] = due_at
        if outcome is not None: updates["outcome"] = outcome
        if feedback is not None: updates["feedback"] = feedback
        if rule_adjustment_requested is not None: updates["rule_adjustment_requested"] = rule_adjustment_requested
        if not updates and not note.strip():
            raise ValueError("没有可更新的字段")
        with self.client.engine.begin() as conn:
            current = conn.execute(text("SELECT * FROM business_cases WHERE case_id = :case_id FOR UPDATE"), {"case_id": case_id}).mappings().first()
            if not current:
                return None
            assignments = ["updated_at = CURRENT_TIMESTAMP"]
            params: Dict[str, Any] = {"case_id": case_id}
            for key, value in updates.items():
                assignments.append(f"{key} = :{key}"); params[key] = value
            terminal = status in {"resolved", "closed"}
            if terminal:
                assignments.extend(["closed_by = :closed_by", "closed_at = CURRENT_TIMESTAMP"]); params["closed_by"] = actor_id
            elif status and current["status"] in {"resolved", "closed"}:
                assignments.extend(["closed_by = NULL", "closed_at = NULL"])
            row = conn.execute(text(f"UPDATE business_cases SET {', '.join(assignments)} WHERE case_id = :case_id RETURNING *"), params).mappings().one()
            if status and status != current["status"]:
                self._event(conn, case_id, "closed" if terminal else ("reopened" if current["status"] in {"resolved", "closed"} else "status_changed"), actor_id, note, {"from": current["status"], "to": status})
            if owner_id is not None and owner_id != current["owner_id"]:
                self._event(conn, case_id, "assigned", actor_id, note, {"owner_id": owner_id})
            if feedback is not None:
                self._event(conn, case_id, "feedback_recorded", actor_id, note, {"feedback": feedback, "rule_adjustment_requested": rule_adjustment_requested})
            elif note.strip() and not (status or owner_id is not None):
                self._event(conn, case_id, "commented", actor_id, note, {})
        return _row(row)

    def feedback_metrics(self) -> Dict[str, Any]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT source_type, source_id, feedback, status, created_at, closed_at
                FROM business_cases
                WHERE source_type = 'alert_history'
            """)).mappings().all()
        total = len(rows); valid = sum(row["feedback"] == "valid" for row in rows); false_positive = sum(row["feedback"] == "false_positive" for row in rows)
        durations = [(row["closed_at"] - row["created_at"]).total_seconds() / 3600 for row in rows if row["closed_at"]]
        return {"alert_case_count": total, "confirmed_count": valid, "false_positive_count": false_positive, "confirmation_rate": valid / total if total else None, "false_positive_rate": false_positive / total if total else None, "average_resolution_hours": sum(durations) / len(durations) if durations else None}
