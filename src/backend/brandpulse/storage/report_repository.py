"""报告运行与定时报告计划的持久化仓储。"""

from __future__ import annotations

import json
from datetime import date, datetime
from email.utils import parseaddr
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
        for key, value in list(item.items()):
            if isinstance(value, (datetime, date)):
                item[key] = str(value)
        return item

    def create(
        self,
        *,
        scope_id: str,
        file_format: str,
        trigger_type: str = "manual",
        report_type: str = "snapshot",
        schedule_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        template_id: str = "trusted_snapshot_brief",
        template_version: str = "v1",
        audience: Optional[List[str]] = None,
        notification_channel: str = "download",
        requested_by: str = "system",
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
        result = self._row(row)
        if snapshot_id:
            ReportPublicationRepository().create(
                report_id=report_id,
                snapshot_id=snapshot_id,
                scope_id=scope_id,
                template_id=template_id,
                template_version=template_version,
                audience=audience or [],
                notification_channel=notification_channel,
                requested_by=requested_by,
            )
        return self.get(report_id) or result

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT run.*, publication.snapshot_id, publication.publication_id,
                           publication.status AS publication_status, publication.template_id,
                           publication.template_version, publication.audience,
                           publication.notification_channel, publication.data_cutoff_at,
                           publication.source_coverage, publication.quality_grade,
                           publication.metric_version, publication.is_partial, publication.watermark,
                           publication.approved_by, publication.approved_at, publication.sent_at,
                           COALESCE(config.require_approval, TRUE) AS require_approval
                    FROM report_runs AS run
                    LEFT JOIN report_publications AS publication ON publication.report_id = run.report_id
                    LEFT JOIN report_schedule_publication_configs AS config ON config.schedule_id = run.schedule_id
                    WHERE run.report_id = :report_id
                    """
                ),
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
                    SELECT run.*, COALESCE(scope.city, legacy_scope.city) AS city,
                           COALESCE(scope.mall_name, legacy_scope.mall_name) AS mall_name,
                           COALESCE(scope.category, legacy_scope.category) AS category,
                           publication.snapshot_id, publication.publication_id,
                           publication.status AS publication_status, publication.template_id,
                           publication.template_version, publication.audience,
                           publication.notification_channel, publication.data_cutoff_at,
                           publication.source_coverage, publication.quality_grade,
                           publication.metric_version, publication.is_partial, publication.watermark,
                           publication.approved_by, publication.approved_at, publication.sent_at,
                           COALESCE(config.require_approval, TRUE) AS require_approval
                    FROM report_runs AS run
                    LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = run.scope_id
                    LEFT JOIN monitoring_scopes AS legacy_scope ON legacy_scope.scope_id = run.scope_id
                    LEFT JOIN report_publications AS publication ON publication.report_id = run.report_id
                    LEFT JOIN report_schedule_publication_configs AS config ON config.schedule_id = run.schedule_id
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
        started = bool(result.rowcount)
        if started:
            ReportPublicationRepository().set_status_for_report(report_id, "running")
        return started

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
        ReportPublicationRepository().mark_ready_for_review(
            report_id,
            snapshot_date=snapshot_date,
            metadata=metadata,
        )

    def finish_failure(self, report_id: str, error: str, *, status: str = "failed") -> None:
        self._update(report_id, status=status, error=error, finished=True)
        ReportPublicationRepository().set_status_for_report(
            report_id, "skipped" if status == "skipped" else "failed", note=error,
        )

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


class ReportPublicationRepository:
    """报告模板、快照绑定、审核与分发记录；不修改兼容 report_runs 表。"""

    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key, value in list(item.items()):
            if hasattr(value, "as_tuple"):
                item[key] = float(value)
            elif isinstance(value, (datetime, date)):
                item[key] = str(value)
        return item

    def create(
        self,
        *,
        report_id: str,
        snapshot_id: str,
        scope_id: str,
        template_id: str,
        template_version: str,
        audience: List[str],
        notification_channel: str,
        requested_by: str,
    ) -> Dict[str, Any]:
        publication_id = f"publication_{uuid4().hex}"
        with self.client.engine.begin() as conn:
            snapshot = conn.execute(
                text(
                    """
                    SELECT observed_at, source_coverage, quality_grade
                    FROM data_snapshots WHERE snapshot_id = :snapshot_id AND scope_id = :scope_id
                    """
                ),
                {"snapshot_id": snapshot_id, "scope_id": scope_id},
            ).mappings().first()
            if not snapshot:
                raise ValueError("报告快照不存在或不属于当前范围")
            template = conn.execute(
                text("SELECT template_version FROM report_templates WHERE template_id = :template_id AND is_active = TRUE"),
                {"template_id": template_id},
            ).mappings().first()
            if not template:
                raise ValueError("报告模板不存在或已停用")
            row = conn.execute(
                text(
                    """
                    INSERT INTO report_publications (
                        publication_id, report_id, snapshot_id, scope_id, template_id, template_version,
                        audience, notification_channel, data_cutoff_at, source_coverage, quality_grade,
                        metric_version, requested_by
                    ) VALUES (
                        :publication_id, :report_id, :snapshot_id, :scope_id, :template_id, :template_version,
                        CAST(:audience AS jsonb), :notification_channel, :data_cutoff_at,
                        CAST(:source_coverage AS jsonb), :quality_grade, 'snapshot-v2', :requested_by
                    )
                    RETURNING *
                    """
                ),
                {
                    "publication_id": publication_id,
                    "report_id": report_id,
                    "snapshot_id": snapshot_id,
                    "scope_id": scope_id,
                    "template_id": template_id,
                    "template_version": template_version or template["template_version"],
                    "audience": json.dumps(audience, ensure_ascii=False),
                    "notification_channel": notification_channel,
                    "data_cutoff_at": snapshot["observed_at"],
                    "source_coverage": json.dumps(snapshot["source_coverage"] or {}, ensure_ascii=False, default=str),
                    "quality_grade": snapshot["quality_grade"],
                    "requested_by": requested_by,
                },
            ).mappings().one()
            conn.execute(
                text(
                    """
                    INSERT INTO report_snapshot_links (report_id, snapshot_id, created_by)
                    VALUES (:report_id, :snapshot_id, :created_by)
                    ON CONFLICT (report_id) DO UPDATE SET snapshot_id = EXCLUDED.snapshot_id,
                        created_by = EXCLUDED.created_by
                    """
                ),
                {"report_id": report_id, "snapshot_id": snapshot_id, "created_by": requested_by},
            )
            self._event(conn, publication_id, "submitted", requested_by, "报告已绑定可信快照并进入队列")
        return self._row(row)

    @staticmethod
    def _event(conn, publication_id: str, action: str, actor_id: str, note: str = "") -> None:
        conn.execute(
            text(
                """
                INSERT INTO report_review_events (review_event_id, publication_id, action, actor_id, note)
                VALUES (:review_event_id, :publication_id, :action, :actor_id, :note)
                """
            ),
            {"review_event_id": f"report_event_{uuid4().hex}", "publication_id": publication_id,
             "action": action, "actor_id": actor_id, "note": note},
        )

    def _publication_id(self, conn, report_id: str) -> Optional[str]:
        row = conn.execute(
            text("SELECT publication_id FROM report_publications WHERE report_id = :report_id"),
            {"report_id": report_id},
        ).mappings().first()
        return str(row["publication_id"]) if row else None

    def set_status_for_report(self, report_id: str, status: str, *, note: str = "") -> None:
        with self.client.engine.begin() as conn:
            publication_id = self._publication_id(conn, report_id)
            if not publication_id:
                return
            conn.execute(
                text("UPDATE report_publications SET status = :status, updated_at = CURRENT_TIMESTAMP WHERE publication_id = :publication_id"),
                {"status": status, "publication_id": publication_id},
            )
            if status in {"failed", "skipped"}:
                self._event(conn, publication_id, "rejected", "system", note)

    def mark_ready_for_review(self, report_id: str, *, snapshot_date: str, metadata: Dict[str, Any]) -> None:
        with self.client.engine.begin() as conn:
            publication_id = self._publication_id(conn, report_id)
            if not publication_id:
                return
            conn.execute(
                text(
                    """
                    UPDATE report_publications
                    SET status = 'ready_for_review', data_cutoff_at = :snapshot_date,
                        source_coverage = CAST(:source_coverage AS jsonb), quality_grade = :quality_grade,
                        metric_version = :metric_version, updated_at = CURRENT_TIMESTAMP
                    WHERE publication_id = :publication_id
                    """
                ),
                {
                    "publication_id": publication_id,
                    "snapshot_date": snapshot_date,
                    "source_coverage": json.dumps(metadata.get("source_coverage") or {}, ensure_ascii=False, default=str),
                    "quality_grade": metadata.get("quality_grade") or "unrated",
                    "metric_version": metadata.get("metric_version") or "snapshot-v2",
                },
            )

    def approve_automatically(self, report_id: str) -> Optional[Dict[str, Any]]:
        """仅供明确配置为免人工审核的计划使用，仍保留审核事件。"""
        return self.approve(report_id, actor_id="system:schedule", note="计划配置为免人工审核")

    def approve(self, report_id: str, *, actor_id: str, note: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE report_publications
                    SET status = 'approved', approved_by = :actor_id, approved_at = CURRENT_TIMESTAMP,
                        approval_note = :note, updated_at = CURRENT_TIMESTAMP
                    WHERE report_id = :report_id AND status = 'ready_for_review'
                    RETURNING *
                    """
                ),
                {"report_id": report_id, "actor_id": actor_id, "note": note},
            ).mappings().first()
            if row:
                self._event(conn, row["publication_id"], "approved", actor_id, note)
        return self._row(row) if row else None

    def record_download(self, report_id: str, *, actor_id: str) -> None:
        with self.client.engine.begin() as conn:
            publication_id = self._publication_id(conn, report_id)
            if publication_id:
                self._event(conn, publication_id, "downloaded", actor_id, "下载报告文件")

    def queue_delivery_jobs(self, report_id: str) -> List[Dict[str, Any]]:
        """为已审核报告创建每个收件人的可重试投递任务，不直接发送。"""
        with self.client.engine.begin() as conn:
            publication = conn.execute(
                text(
                    """
                    SELECT publication_id, status, audience, notification_channel
                    FROM report_publications
                    WHERE report_id = :report_id
                    FOR UPDATE
                    """
                ),
                {"report_id": report_id},
            ).mappings().first()
            if not publication:
                raise ValueError("报告缺少可信快照发布记录，不能分发")
            if publication["status"] != "approved":
                raise ValueError("报告必须完成审核后才能分发")
            channel = str(publication["notification_channel"])
            if channel not in {"smtp", "webhook"}:
                raise ValueError("当前报告仅支持下载，不存在可发送的通知渠道")
            audience = publication["audience"] or []
            if not audience:
                raise ValueError("请先在生成报告时填写至少一个收件人或 Webhook 地址")

            result: List[Dict[str, Any]] = []
            for raw_recipient in audience:
                recipient = str(raw_recipient).strip()
                if not recipient:
                    continue
                if channel == "smtp" and not parseaddr(recipient)[1]:
                    raise ValueError(f"无效的邮件地址: {recipient}")
                if channel == "webhook" and not recipient.startswith(("http://", "https://")):
                    raise ValueError(f"无效的 Webhook 地址: {recipient}")
                row = conn.execute(
                    text(
                        """
                        INSERT INTO report_delivery_jobs (
                            delivery_job_id, publication_id, channel, recipient
                        ) VALUES (
                            :delivery_job_id, :publication_id, :channel, :recipient
                        )
                        ON CONFLICT (publication_id, channel, recipient)
                        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                        RETURNING *
                        """
                    ),
                    {
                        "delivery_job_id": f"report_delivery_{uuid4().hex}",
                        "publication_id": publication["publication_id"],
                        "channel": channel,
                        "recipient": recipient,
                    },
                ).mappings().one()
                result.append(self._row(row))
            if not result:
                raise ValueError("没有可用的报告接收方")
        return result

    def list_delivery_jobs(self, report_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT job.*
                    FROM report_delivery_jobs AS job
                    JOIN report_publications AS publication ON publication.publication_id = job.publication_id
                    WHERE publication.report_id = :report_id
                    ORDER BY job.created_at DESC, job.delivery_job_id DESC
                    LIMIT :limit
                    """
                ),
                {"report_id": report_id, "limit": limit},
            ).mappings().all()
        return [self._row(row) for row in rows]

    def list_all_delivery_jobs(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        """自动化中心统一展示报告通知记录；不暴露邮件正文或附件内容。"""
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT job.*, publication.report_id, publication.snapshot_id,
                           COALESCE(scope.city, legacy_scope.city) AS city,
                           COALESCE(scope.mall_name, legacy_scope.mall_name) AS mall_name,
                           COALESCE(scope.category, legacy_scope.category) AS category
                    FROM report_delivery_jobs AS job
                    JOIN report_publications AS publication ON publication.publication_id = job.publication_id
                    LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = publication.scope_id
                    LEFT JOIN monitoring_scopes AS legacy_scope ON legacy_scope.scope_id = publication.scope_id
                    ORDER BY job.updated_at DESC, job.delivery_job_id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [self._row(row) for row in rows]

    def retry_failed_delivery_jobs(self, report_id: str) -> int:
        """仅显式重试已失败项，成功投递不会被重复发送。"""
        with self.client.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE report_delivery_jobs AS job
                    SET status = 'pending', attempt_count = 0, next_attempt_at = CURRENT_TIMESTAMP,
                        last_error = '', updated_at = CURRENT_TIMESTAMP
                    FROM report_publications AS publication
                    WHERE job.publication_id = publication.publication_id
                      AND publication.report_id = :report_id
                      AND publication.status = 'approved'
                      AND job.status = 'failed'
                    """
                ),
                {"report_id": report_id},
            )
        return int(result.rowcount or 0)

    def claim_due_delivery_job(self) -> Optional[Dict[str, Any]]:
        """用行锁领取一个到期任务，多个调度进程也不会重复发送。"""
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    WITH due AS (
                        SELECT job.delivery_job_id
                        FROM report_delivery_jobs AS job
                        JOIN report_publications AS publication ON publication.publication_id = job.publication_id
                        WHERE job.status IN ('pending', 'retry')
                          AND job.next_attempt_at <= CURRENT_TIMESTAMP
                          AND publication.status = 'approved'
                        ORDER BY job.next_attempt_at, job.created_at, job.delivery_job_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE report_delivery_jobs AS job
                    SET status = 'sending', attempt_count = attempt_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    FROM due
                    WHERE job.delivery_job_id = due.delivery_job_id
                    RETURNING job.*
                    """
                )
            ).mappings().first()
        return self._row(row) if row else None

    def report_for_delivery(self, delivery_job_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT run.*, publication.snapshot_id, publication.publication_id,
                           publication.status AS publication_status, publication.data_cutoff_at,
                           publication.source_coverage, publication.quality_grade,
                           publication.metric_version, publication.notification_channel,
                           COALESCE(scope.city, legacy_scope.city) AS city,
                           COALESCE(scope.mall_name, legacy_scope.mall_name) AS mall_name,
                           COALESCE(scope.category, legacy_scope.category) AS category
                    FROM report_delivery_jobs AS job
                    JOIN report_publications AS publication ON publication.publication_id = job.publication_id
                    JOIN report_runs AS run ON run.report_id = publication.report_id
                    LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = run.scope_id
                    LEFT JOIN monitoring_scopes AS legacy_scope ON legacy_scope.scope_id = run.scope_id
                    WHERE job.delivery_job_id = :delivery_job_id
                      AND job.status = 'sending'
                    """
                ),
                {"delivery_job_id": delivery_job_id},
            ).mappings().first()
        return ReportRunRepository._row(row) if row else None

    def finish_delivery_job(
        self,
        delivery_job_id: str,
        *,
        success: bool,
        response: Dict[str, Any],
        error: str = "",
    ) -> Optional[Dict[str, Any]]:
        with self.client.engine.begin() as conn:
            job = conn.execute(
                text(
                    """
                    SELECT job.*, publication.report_id, publication.publication_id
                    FROM report_delivery_jobs AS job
                    JOIN report_publications AS publication ON publication.publication_id = job.publication_id
                    WHERE job.delivery_job_id = :delivery_job_id
                    FOR UPDATE
                    """
                ),
                {"delivery_job_id": delivery_job_id},
            ).mappings().first()
            if not job or job["status"] != "sending":
                return None
            if success:
                status = "sent"
                # 字段为 NOT NULL；已发送任务不会再被领取，保留完成时间即可。
                next_attempt_at = "CURRENT_TIMESTAMP"
            else:
                status = "failed" if job["attempt_count"] >= job["max_attempts"] else "retry"
                delay_seconds = min(3600, 60 * (2 ** max(job["attempt_count"] - 1, 0)))
                next_attempt_at = f"CURRENT_TIMESTAMP + INTERVAL '{delay_seconds} seconds'"
            update_sql = """
                UPDATE report_delivery_jobs
                SET status = :status, response = CAST(:response AS jsonb), last_error = :last_error,
                    sent_at = CASE WHEN :status = 'sent' THEN CURRENT_TIMESTAMP ELSE sent_at END,
                    next_attempt_at = {next_attempt_at}, updated_at = CURRENT_TIMESTAMP
                WHERE delivery_job_id = :delivery_job_id
                RETURNING *
            """.format(next_attempt_at=next_attempt_at)
            updated = conn.execute(
                text(update_sql),
                {
                    "delivery_job_id": delivery_job_id,
                    "status": status,
                    "response": json.dumps(response, ensure_ascii=False, default=str),
                    "last_error": error[:4000],
                },
            ).mappings().one()
            conn.execute(
                text(
                    """
                    INSERT INTO report_delivery_events (
                        delivery_event_id, publication_id, channel, recipient, status, attempt_no,
                        error_message, metadata
                    ) VALUES (
                        :delivery_event_id, :publication_id, :channel, :recipient, :status, :attempt_no,
                        :error_message, CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "delivery_event_id": f"report_delivery_event_{uuid4().hex}",
                    "publication_id": job["publication_id"],
                    "channel": job["channel"],
                    "recipient": job["recipient"],
                    "status": status,
                    "attempt_no": job["attempt_count"],
                    "error_message": error[:4000],
                    "metadata": json.dumps(response, ensure_ascii=False, default=str),
                },
            )
            remaining = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM report_delivery_jobs
                    WHERE publication_id = :publication_id AND status != 'sent'
                    """
                ),
                {"publication_id": job["publication_id"]},
            ).scalar_one()
            if success and remaining == 0:
                conn.execute(
                    text(
                        """
                        UPDATE report_publications
                        SET status = 'sent', sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE publication_id = :publication_id AND status = 'approved'
                        """
                    ),
                    {"publication_id": job["publication_id"]},
                )
                self._event(conn, job["publication_id"], "sent", "system", "全部收件人投递成功")
        return self._row(updated)


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
        template_id: str = "trusted_snapshot_brief",
        template_version: str = "v1",
        audience: Optional[List[str]] = None,
        notification_channel: str = "download",
        require_approval: bool = True,
        updated_by: str = "system",
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
        self.upsert_publication_config(
            schedule_id=schedule_id,
            template_id=template_id,
            template_version=template_version,
            audience=audience or [],
            notification_channel=notification_channel,
            require_approval=require_approval,
            updated_by=updated_by,
        )
        return self.get(schedule_id) or self._row(row)

    def list(self) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT schedule.*, COALESCE(scope.city, legacy_scope.city) AS city,
                           COALESCE(scope.mall_name, legacy_scope.mall_name) AS mall_name,
                           COALESCE(scope.category, legacy_scope.category) AS category,
                           COALESCE(config.template_id, 'trusted_snapshot_brief') AS template_id,
                           COALESCE(config.template_version, 'v1') AS template_version,
                           COALESCE(config.audience, '[]'::jsonb) AS audience,
                           COALESCE(config.notification_channel, 'download') AS notification_channel,
                           COALESCE(config.require_approval, TRUE) AS require_approval
                    FROM report_schedules AS schedule
                    LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = schedule.scope_id
                    LEFT JOIN monitoring_scopes AS legacy_scope ON legacy_scope.scope_id = schedule.scope_id
                    LEFT JOIN report_schedule_publication_configs AS config ON config.schedule_id = schedule.schedule_id
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
                text(
                    """
                    SELECT schedule.*, COALESCE(config.template_id, 'trusted_snapshot_brief') AS template_id,
                           COALESCE(config.template_version, 'v1') AS template_version,
                           COALESCE(config.audience, '[]'::jsonb) AS audience,
                           COALESCE(config.notification_channel, 'download') AS notification_channel,
                           COALESCE(config.require_approval, TRUE) AS require_approval
                    FROM report_schedules AS schedule
                    LEFT JOIN report_schedule_publication_configs AS config ON config.schedule_id = schedule.schedule_id
                    WHERE schedule.schedule_id = :schedule_id
                    """
                ),
                {"schedule_id": schedule_id},
            ).mappings().first()
        return self._row(row) if row else None

    def upsert_publication_config(
        self,
        *,
        schedule_id: str,
        template_id: str,
        template_version: str,
        audience: List[str],
        notification_channel: str,
        require_approval: bool,
        updated_by: str,
    ) -> None:
        with self.client.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO report_schedule_publication_configs (
                        schedule_id, template_id, template_version, audience, notification_channel,
                        require_approval, updated_by
                    ) VALUES (
                        :schedule_id, :template_id, :template_version, CAST(:audience AS jsonb),
                        :notification_channel, :require_approval, :updated_by
                    )
                    ON CONFLICT (schedule_id) DO UPDATE SET
                        template_id = EXCLUDED.template_id,
                        template_version = EXCLUDED.template_version,
                        audience = EXCLUDED.audience,
                        notification_channel = EXCLUDED.notification_channel,
                        require_approval = EXCLUDED.require_approval,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "schedule_id": schedule_id,
                    "template_id": template_id,
                    "template_version": template_version,
                    "audience": json.dumps(audience, ensure_ascii=False),
                    "notification_channel": notification_channel,
                    "require_approval": require_approval,
                    "updated_by": updated_by,
                },
            )

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
