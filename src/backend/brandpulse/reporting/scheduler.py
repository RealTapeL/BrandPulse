"""定时报告计划执行；计划只生成已通过数据新鲜度门禁的报告。"""

from __future__ import annotations

from datetime import datetime

from brandpulse.reporting.queue import ReportEnqueueError, enqueue_report
from brandpulse.reporting.service import ReportDataNotReadyError, require_report_ready
from brandpulse.storage.report_repository import ReportRunRepository, ReportScheduleRepository


def process_due_report_schedules(now: datetime) -> int:
    report_schedules = ReportScheduleRepository()
    run_repository = ReportRunRepository()
    submitted = 0
    for schedule in report_schedules.list():
        if not schedule["enabled"]:
            continue
        due_today = schedule["frequency"] == "daily" or schedule.get("weekday") == now.weekday()
        due_time = (now.hour, now.minute) >= (int(schedule["hour"]), int(schedule["minute"]))
        if not due_today or not due_time:
            continue
        try:
            require_report_ready(schedule["scope_id"])
        except ReportDataNotReadyError as exc:
            # 保持未领取状态；当同一天稍后采集补齐数据时仍可生成正式报告。
            report_schedules.record_error(schedule["schedule_id"], str(exc))
            continue
        if not report_schedules.claim_for_date(schedule["schedule_id"], now.date()):
            continue
        run = run_repository.create(
            scope_id=schedule["scope_id"],
            schedule_id=schedule["schedule_id"],
            trigger_type="schedule",
            report_type=schedule["frequency"],
            file_format=schedule["file_format"],
        )
        try:
            run_repository.set_rq_job(run["report_id"], enqueue_report(run["report_id"]))
            submitted += 1
        except ReportEnqueueError as exc:
            run_repository.finish_failure(run["report_id"], str(exc), status="skipped")
            report_schedules.release_claim(schedule["schedule_id"], now.date(), str(exc))
    return submitted
