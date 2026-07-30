"""
抓取任务队列（RQ）封装。

依赖：Redis + rq。开发环境请先启动 redis-server。
TODO: 生产环境 REDIS_URL 从环境变量读取；本地若 Redis 未启动可临时切 fakeredis。
"""
from typing import Any

from redis import Redis

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

QUEUE_NAME = "brandpulse-crawl"


def _redis_conn() -> Redis:
    """从 REDIS_URL 构造 Redis 连接。"""
    return Redis.from_url(Config.REDIS_URL, decode_responses=True)


def enqueue_crawl(task_meta: dict[str, Any]) -> str:
    """
    将抓取任务入队，返回 RQ job_id。

    Args:
        task_meta: 必须包含 brand_id, mall, category, cities?；会被序列化为 RQ job kwargs。
    """
    from rq import Queue

    queue = Queue(name=QUEUE_NAME, connection=_redis_conn())
    # 避免循环依赖：字符串导入 job 函数
    job = queue.enqueue(
        "brandpulse.collectors.worker.run_crawl_job",
        task_meta=task_meta,
        job_timeout=600,
        result_ttl=86400,
    )
    logger.info(f"[queue] crawl job enqueued: {job.id}, meta={task_meta}")
    return job.id


def get_queue():
    """返回队列实例，供 worker/状态查询使用。"""
    from rq import Queue

    return Queue(name=QUEUE_NAME, connection=_redis_conn())
