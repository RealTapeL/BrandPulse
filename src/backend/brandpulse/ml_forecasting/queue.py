"""机器学习训练 RQ 队列。"""

from redis import Redis

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

QUEUE_NAME = "brandpulse-ml"


def _redis_conn() -> Redis:
    return Redis.from_url(Config.REDIS_URL, decode_responses=True)


class MLTrainingEnqueueError(RuntimeError):
    """训练运行已落台账，但没有成功投递到 RQ。"""


class MLExportEnqueueError(RuntimeError):
    """预测导出已落台账，但没有成功投递到 RQ。"""


def enqueue_training(run_id: str) -> str:
    from rq import Queue

    try:
        queue = Queue(name=QUEUE_NAME, connection=_redis_conn())
        job = queue.enqueue(
            "brandpulse.ml_forecasting.runner.run_training_run",
            run_id=run_id,
            job_timeout=3600,
            result_ttl=86400,
            failure_ttl=86400,
        )
    except Exception as exc:
        raise MLTrainingEnqueueError(f"机器学习训练入队失败，请检查 Redis/Worker 配置: {exc}") from exc
    logger.info("[ml-queue] run_id=%s, rq_job_id=%s", run_id, job.id)
    return job.id


def enqueue_export(export_id: str) -> str:
    from rq import Queue

    try:
        queue = Queue(name=QUEUE_NAME, connection=_redis_conn())
        job = queue.enqueue(
            "brandpulse.ml_forecasting.runner.run_forecast_export",
            export_id=export_id,
            job_timeout=600,
            result_ttl=86400,
            failure_ttl=86400,
        )
    except Exception as exc:
        raise MLExportEnqueueError(f"预测导出入队失败，请检查 Redis/Worker 配置: {exc}") from exc
    logger.info("[ml-queue] export_id=%s, rq_job_id=%s", export_id, job.id)
    return job.id


def get_ml_queue():
    from rq import Queue

    return Queue(name=QUEUE_NAME, connection=_redis_conn())
