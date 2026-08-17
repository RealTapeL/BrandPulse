"""持久化自动采集与报告计划调度器。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from brandpulse.collectors.jobs import CrawlJobEnqueueError, create_crawl_job
from brandpulse.logger.logger import get_logger
from brandpulse.storage.monitoring_repository import CrawlScheduleRepository

logger = get_logger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def process_due_crawl_schedules() -> int:
    """领取到期采集计划并投递真实采集任务；没有计划时不会产生任何请求。"""
    repository = CrawlScheduleRepository()
    schedules = repository.claim_due()
    submitted = 0
    for schedule in schedules:
        try:
            create_crawl_job(
                brand_id=schedule["brand_id"],
                mall=schedule["mall_name"],
                category=schedule["category"],
                cities=[schedule["city"]],
                scope_id=schedule["scope_id"],
                schedule_id=schedule["schedule_id"],
                trigger_type="schedule",
                max_attempts=int(schedule["max_attempts"]),
            )
            submitted += 1
        except (CrawlJobEnqueueError, ValueError, RuntimeError) as exc:
            repository.record_result(schedule["schedule_id"], success=False, error=str(exc))
            logger.exception("[monitoring] 自动采集计划入队失败: %s", schedule["schedule_id"])
    return submitted


def process_due_report_schedules() -> int:
    """处理到期报告，并消费已审核报告的持久化分发重试队列。"""
    from brandpulse.reporting.scheduler import process_due_report_schedules as process_reports
    from brandpulse.reporting.delivery import process_due_report_deliveries

    submitted = process_reports(datetime.now())
    delivery_summary = process_due_report_deliveries()
    if any(delivery_summary.values()):
        logger.info("[monitoring] 报告分发队列已处理: %s", delivery_summary)
    return submitted


def start_monitoring_scheduler(interval_seconds: int = 60) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        process_due_crawl_schedules,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="brandpulse-crawl-schedules",
        replace_existing=True,
    )
    _scheduler.add_job(
        process_due_report_schedules,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="brandpulse-report-schedules",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("[monitoring] 自动采集/报告调度器已启动，检查间隔 %s 秒", interval_seconds)
    return _scheduler


def shutdown_monitoring_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("[monitoring] 自动采集/报告调度器已关闭")
