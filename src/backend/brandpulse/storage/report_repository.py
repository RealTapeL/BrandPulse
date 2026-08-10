"""报告运行与定时报告计划的持久化仓储。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class ReportRunRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["metadata"] = item.get("metadata") or {}
        for key in ("created_at", "updated_at", "started_at", "finished_at", "snapshot_date"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        *,
        scope_id: str,
        file_format: str,
        trigger_type: str = "manual",
        report_type: str = "snapshot",
        schedule_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        report_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO report_runs
                        (report_id, scope_id, schedule_id, trigger_type, report_type, file_format)
                    VALUES
                        (:report_id, :scope_id, :schedule_id, :trigger_type, :report_type, :file_format)
                    RETURNING *
                    """
                ),
                {
                    "report_id": report_id,
                    "scope_id": scope_id,
                    "schedule_id": schedule_id,
                    "trigger_type": trigger_type,
                    "report_type": report_type,
                    "file_format": file_format,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM report_runs WHERE report_id = :report_id"),
                {"report_id": report_id},
            ).mappings().first()
        return self._row(row) if row else None

    def list(self, *, scope_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        condition = "WHERE run.scope_id = :scope_id" if scope_id else ""
        params: Dict[str, Any] = {"limit": limit}
        if scope_id:
            params["scope_id"] = scope_id
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT run.*, scope.city, scope.mall_name, scope.category
                    FROM report_runs AS run
                    JOIN monitoring_scopes AS scope ON scope.scope_id = run.scope_id
                    {condition}
                    ORDER BY run.created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._row(row) for row in rows]

    def set_rq_job(self, report_id: str, rq_job_id: str) -> None:
        self._update(report_id, rq_job_id=rq_job_id)

    def mark_running(self, report_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE report_runs
                    SET status = 'running', started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE report_id = :report_id AND status = 'pending'
                    """
                ),
                {"report_id": report_id},
            )
            conn.commit()
        return bool(result.rowcount)

    def finish_success(
        self,
        report_id: str,
        *,
        snapshot_date: str,
        file_path: str,
        row_count: int,
        metadata: Dict[str, Any],
    ) -> None:
        self._update(
            report_id,
            status="success",
            snapshot_date=snapshot_date,
            file_path=file_path,
            row_count=row_count,
            metadata=json.dumps(metadata, ensure_ascii=False, default=str),
            error=None,
            finished=True,
        )

    def finish_failure(self, report_id: str, error: str, *, status: str = "failed") -> None:
        self._update(report_id, status=status, error=error, finished=True)

    def _update(self, report_id: str, **values: Any) -> None:
        finished = bool(values.pop("finished", False))
        assignments = ["updated_at = CURRENT_TIMESTAMP"]
        params: Dict[str, Any] = {"report_id": report_id}
        for key, value in values.items():
            if key == "metadata":
                assignments.append("metadata = CAST(:metadata AS jsonb)")
            else:
                assignments.append(f"{key} = :{key}")
            params[key] = value
        if finished:
            assignments.append("finished_at = CURRENT_TIMESTAMP")
        with self.client.engine.connect() as conn:
            conn.execute(
                text(f"UPDATE report_runs SET {', '.join(assignments)} WHERE report_id = :report_id"),
                params,
            )
            conn.commit()


class ReportScheduleRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ("created_at", "updated_at", "last_enqueued_for"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        *,
        scope_id: str,
        frequency: str,
        hour: int,
        minute: int,
        weekday: Optional[int],
        file_format: str,
        enabled: bool = False,
    ) -> Dict[str, Any]:
        schedule_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO report_schedules
                        (schedule_id, scope_id, frequency, hour, minute, weekday, file_format, enabled)
                    VALUES
                        (:schedule_id, :scope_id, :frequency, :hour, :minute, :weekday, :file_format, :enabled)
                    RETURNING *
                    """
                ),
                {
                    "schedule_id": schedule_id,
                    "scope_id": scope_id,
                    "frequency": frequency,
                    "hour": hour,
                    "minute": minute,
                    "weekday": weekday,
                    "file_format": file_format,
                    "enabled": enabled,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def list(self) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT schedule.*, scope.city, scope.mall_name, scope.category
                    FROM report_schedules AS schedule
                    JOIN monitoring_scopes AS scope ON scope.scope_id = schedule.scope_id
                    ORDER BY schedule.created_at DESC
                    """
                )
            ).mappings().all()
        return [self._row(row) for row in rows]

    def update(self, schedule_id: str, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"frequency", "hour", "minute", "weekday", "file_format", "enabled"}
        payload = {key: value for key, value in values.items() if key in allowed}
        if not payload:
            return self.get(schedule_id)
        assignments = [f"{key} = :{key}" for key in payload]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        payload["schedule_id"] = schedule_id
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"UPDATE report_schedules SET {', '.join(assignments)} "
                    "WHERE schedule_id = :schedule_id RETURNING *"
                ),
                payload,
            ).mappings().first()
            conn.commit()
        return self._row(row) if row else None

    def get(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM report_schedules WHERE schedule_id = :schedule_id"),
                {"schedule_id": schedule_id},
            ).mappings().first()
        return self._row(row) if row else None

    def delete(self, schedule_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM report_schedules WHERE schedule_id = :schedule_id"),
                {"schedule_id": schedule_id},
            )
            conn.commit()
        return bool(result.rowcount)

    def claim_for_date(self, schedule_id: str, report_date: date) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE report_schedules
                    SET last_enqueued_for = :report_date,
                        last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = :schedule_id
                      AND enabled = TRUE
                      AND (last_enqueued_for IS NULL OR last_enqueued_for < :report_date)
                    """
                ),
                {"schedule_id": schedule_id, "report_date": report_date},
            )
            conn.commit()
        return bool(result.rowcount)

    def record_error(self, schedule_id: str, error: str) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE report_schedules SET last_error = :error, updated_at = CURRENT_TIMESTAMP "
                    "WHERE schedule_id = :schedule_id"
                ),
                {"schedule_id": schedule_id, "error": error},
            )
            conn.commit()

    def release_claim(self, schedule_id: str, report_date: date, error: str) -> None:
        """入队失败后释放当天占位，允许数据恢复后再次尝试。"""
        with self.client.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE report_schedules
                    SET last_enqueued_for = NULL,
                        last_error = :error,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = :schedule_id AND last_enqueued_for = :report_date
                    """
                ),
                {"schedule_id": schedule_id, "report_date": report_date, "error": error},
            )
            conn.commit()
