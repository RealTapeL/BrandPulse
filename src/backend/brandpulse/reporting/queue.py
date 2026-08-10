"""报告生成任务队列。"""

from redis import Redis

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)
QUEUE_NAME = "brandpulse-report"


class ReportEnqueueError(RuntimeError):
    pass


def enqueue_report(report_id: str) -> str:
    try:
        from rq import Queue

        queue = Queue(name=QUEUE_NAME, connection=Redis.from_url(Config.REDIS_URL, decode_responses=True))
        job = queue.enqueue(
            "brandpulse.reporting.runner.run_report",
            report_id=report_id,
            job_timeout=180,
            result_ttl=86400,
        )
    except Exception as exc:
        raise ReportEnqueueError(f"报告任务入队失败，请检查 Redis/Worker 配置: {exc}") from exc
    logger.info("[report-queue] report_id=%s rq_job_id=%s", report_id, job.id)
    return job.id
