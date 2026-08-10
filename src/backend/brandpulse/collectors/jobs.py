"""采集任务的持久化与入队服务，供 CLI 以外的 API 入口复用。"""
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from brandpulse.collectors.queue import enqueue_crawl
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.crawl_job_repository import CrawlJobRepository
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository


class CrawlJobEnqueueError(RuntimeError):
    """任务记录已创建、但无法投递到 RQ 时抛出。"""


def create_crawl_job(
    *,
    brand_id: str,
    mall: str,
    category: str,
    cities: List[str],
    scope_id: str | None = None,
    schedule_id: str | None = None,
    trigger_type: str = "manual",
    max_attempts: int = 2,
) -> Dict[str, Any]:
    """创建持久化任务并投递 RQ，返回给调用方的任务摘要。"""
    job_id = str(uuid4())
    client = PostgresClient()
    created_at = datetime.now()
    city = next((value.strip() for value in cities if value and value.strip()), "")
    if not city:
        raise ValueError("至少需要一个非空城市")
    scope_repository = MonitoringScopeRepository()
    scope = scope_repository.get(scope_id) if scope_id else None
    if scope_id and scope is None:
        raise ValueError("监测范围不存在")
    if scope is None:
        scope = scope_repository.register(
            brand_id=brand_id,
            city=city,
            mall_name=mall,
            category=category,
            data_origin="external_webbridge",
        )
    if scope["brand_id"] != brand_id:
        raise ValueError("采集任务品牌/数据集与监测范围不一致")

    client.execute(
        """
        INSERT INTO crawl_jobs
            (job_id, brand_id, mall, category, cities, scope_id, schedule_id, trigger_type, status, created_at)
        VALUES
            (:job_id, :brand_id, :mall, :category, :cities, :scope_id, :schedule_id, :trigger_type, 'pending', :created_at)
        """,
        {
            "job_id": job_id,
            "brand_id": brand_id,
            "mall": mall,
            "category": category,
            "cities": cities,
            "scope_id": scope["scope_id"],
            "schedule_id": schedule_id,
            "trigger_type": trigger_type,
            "created_at": created_at,
        },
    )

    task_meta = {
        "job_id": job_id,
        "brand_id": brand_id,
        "mall": mall,
        "category": category,
        "cities": cities,
        "scope_id": scope["scope_id"],
        "schedule_id": schedule_id,
        "max_attempts": max_attempts,
    }
    try:
        rq_job_id = enqueue_crawl(task_meta)
        CrawlJobRepository().set_rq_job(job_id, rq_job_id)
    except Exception as exc:
        CrawlJobRepository().finish(job_id, status="failed", result={"error": f"入队失败: {exc}"})
        raise CrawlJobEnqueueError(f"任务入队失败，请检查 Redis: {exc}") from exc

    return {
        "job_id": job_id,
        "rq_job_id": rq_job_id,
        "status": "pending",
        "scope_id": scope["scope_id"],
        "created_at": str(created_at),
    }
