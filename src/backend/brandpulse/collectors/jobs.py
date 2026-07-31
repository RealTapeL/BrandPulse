"""采集任务的持久化与入队服务，供 CLI 以外的 API 入口复用。"""
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from brandpulse.collectors.queue import enqueue_crawl
from brandpulse.db_clients.postgres_client import PostgresClient


class CrawlJobEnqueueError(RuntimeError):
    """任务记录已创建、但无法投递到 RQ 时抛出。"""


def create_crawl_job(
    *,
    brand_id: str,
    mall: str,
    category: str,
    cities: List[str],
) -> Dict[str, Any]:
    """创建持久化任务并投递 RQ，返回给调用方的任务摘要。"""
    job_id = str(uuid4())
    client = PostgresClient()
    created_at = datetime.now()

    client.execute(
        """
        INSERT INTO crawl_jobs (job_id, brand_id, mall, category, cities, status, created_at)
        VALUES (:job_id, :brand_id, :mall, :category, :cities, 'pending', :created_at)
        """,
        {
            "job_id": job_id,
            "brand_id": brand_id,
            "mall": mall,
            "category": category,
            "cities": cities,
            "created_at": created_at,
        },
    )

    task_meta = {
        "job_id": job_id,
        "brand_id": brand_id,
        "mall": mall,
        "category": category,
        "cities": cities,
    }
    try:
        rq_job_id = enqueue_crawl(task_meta)
    except Exception as exc:
        client.execute(
            """
            UPDATE crawl_jobs
            SET status = 'failed', result = :result, finished_at = CURRENT_TIMESTAMP
            WHERE job_id = :job_id
            """,
            {"job_id": job_id, "result": f"入队失败: {exc}"},
        )
        raise CrawlJobEnqueueError(f"任务入队失败，请检查 Redis: {exc}") from exc

    return {
        "job_id": job_id,
        "rq_job_id": rq_job_id,
        "status": "pending",
        "created_at": str(created_at),
    }
