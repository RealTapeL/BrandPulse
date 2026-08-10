"""Agent RQ 队列：把任务从 FastAPI 进程交给常驻 Worker。"""
from redis import Redis

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

QUEUE_NAME = "brandpulse-agent"


def _redis_conn() -> Redis:
    return Redis.from_url(Config.REDIS_URL, decode_responses=True)


class AgentTaskEnqueueError(RuntimeError):
    """Agent 任务已持久化，但没有成功投递到 RQ。"""


def enqueue_agent(task_id: str) -> str:
    """投递 Agent 任务，返回 RQ job ID。"""
    from rq import Queue

    try:
        queue = Queue(name=QUEUE_NAME, connection=_redis_conn())
        job = queue.enqueue(
            "brandpulse.agent.task_runner.run_agent_task",
            task_id=task_id,
            job_timeout=900,
            result_ttl=86400,
            failure_ttl=86400,
        )
    except Exception as exc:
        raise AgentTaskEnqueueError(f"Agent 任务入队失败，请检查 Redis/Worker 配置: {exc}") from exc
    logger.info("[agent-queue] task enqueued: task_id=%s, rq_job_id=%s", task_id, job.id)
    return job.id


def get_agent_queue():
    """返回 Agent 队列实例，供诊断和测试使用。"""
    from rq import Queue

    return Queue(name=QUEUE_NAME, connection=_redis_conn())
