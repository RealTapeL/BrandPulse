"""报告投递队列：只消费已领取任务，失败会交由仓储记录成 retry/failed。"""

from brandpulse.reporting import delivery
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.report_repository import ReportPublicationRepository, ReportRunRepository
from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository


class _Repository:
    def __init__(self, *, completion_status="sent"):
        self.jobs = [{"delivery_job_id": "delivery_test", "channel": "smtp", "recipient": "ops@example.com"}]
        self.completion_status = completion_status
        self.finished = []

    def claim_due_delivery_job(self):
        return self.jobs.pop(0) if self.jobs else None

    def report_for_delivery(self, _job_id):
        return {"report_id": "report_test", "scope_id": "scope_test", "file_format": "xlsx"}

    def finish_delivery_job(self, job_id, *, success, response, error=""):
        self.finished.append({"job_id": job_id, "success": success, "response": response, "error": error})
        return {"status": "sent" if success else self.completion_status}


def test_report_delivery_process_records_real_sender_result(monkeypatch):
    repository = _Repository()
    monkeypatch.setattr(delivery, "ReportPublicationRepository", lambda: repository)
    monkeypatch.setattr(delivery, "send_report", lambda channel, recipient, report: {
        "channel": channel, "recipient": recipient, "status": "sent",
    })

    assert delivery.process_due_report_deliveries() == {"sent": 1, "retry": 0, "failed": 0}
    assert repository.finished[0]["success"] is True


def test_report_delivery_process_keeps_failure_for_retry(monkeypatch):
    repository = _Repository(completion_status="retry")
    monkeypatch.setattr(delivery, "ReportPublicationRepository", lambda: repository)
    monkeypatch.setattr(delivery, "send_report", lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp unavailable")))

    assert delivery.process_due_report_deliveries() == {"sent": 0, "retry": 1, "failed": 0}
    assert repository.finished[0]["success"] is False
    assert "smtp unavailable" in repository.finished[0]["error"]


def test_report_delivery_job_is_bound_to_approved_snapshot_report():
    scopes = TrustedScopeRepository().list()
    assert scopes, "测试库需要至少一个已登记监测范围"
    scope = scopes[0]
    snapshot = SnapshotRepository().latest_released(scope["scope_id"])
    assert snapshot, "测试库需要至少一个 ready/published 快照"
    run_repository = ReportRunRepository()
    publication_repository = ReportPublicationRepository()
    run = run_repository.create(
        scope_id=scope["scope_id"], file_format="csv", snapshot_id=snapshot["snapshot_id"],
        audience=["report-test@example.com"], notification_channel="smtp", requested_by="pytest",
    )
    try:
        run_repository.finish_success(
            run["report_id"], snapshot_date=str(snapshot["observed_at"]),
            file_path="/tmp/brandpulse-report-delivery-test.csv", row_count=0,
            metadata={"source_coverage": snapshot.get("source_coverage") or {}, "quality_grade": snapshot["quality_grade"], "metric_version": "snapshot-v2"},
        )
        assert publication_repository.approve(run["report_id"], actor_id="pytest-admin", note="测试审核")
        jobs = publication_repository.queue_delivery_jobs(run["report_id"])
        assert len(jobs) == 1
        claimed = publication_repository.claim_due_delivery_job()
        assert claimed and claimed["delivery_job_id"] == jobs[0]["delivery_job_id"]
        report = publication_repository.report_for_delivery(claimed["delivery_job_id"])
        assert report and report["snapshot_id"] == snapshot["snapshot_id"]
        finished = publication_repository.finish_delivery_job(
            claimed["delivery_job_id"], success=True, response={"status": "sent", "test": True},
        )
        assert finished and finished["status"] == "sent"
        assert ReportRunRepository().get(run["report_id"])["publication_status"] == "sent"
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text("DELETE FROM report_snapshot_links WHERE report_id = :report_id"), {"report_id": run["report_id"]})
            conn.execute(text("DELETE FROM report_runs WHERE report_id = :report_id"), {"report_id": run["report_id"]})
