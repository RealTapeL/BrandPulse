"""采集任务的持久化与入队服务，供 CLI 以外的 API 入口复用。"""
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from brandpulse.collectors.queue import enqueue_crawl
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.crawl_job_repository import CrawlJobRepository
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.trusted_data_repository import CollectionRunRepository


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

    # crawl_jobs.brand_id 是历史兼容字段：保留调用方传入的值，不能再把它当作
    # 范围唯一键或真实品牌事实。可信关系由 collection_run.scope_id 单独保存。
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

    requested_brand_id = brand_id if not brand_id.startswith("MALL_") else None
    collection_run = CollectionRunRepository().create(
        scope_id=scope["scope_id"],
        crawl_job_id=job_id,
        trigger_type=trigger_type if trigger_type in {"manual", "schedule", "agent", "cli", "retry"} else "manual",
        requested_brand_id=requested_brand_id,
    )

    task_meta = {
        "job_id": job_id,
        "brand_id": brand_id,
        "mall": mall,
        "category": category,
        "cities": cities,
        "scope_id": scope["scope_id"],
        "collection_run_id": collection_run["collection_run_id"],
        "legacy_dataset_key": scope.get("legacy_dataset_key") or scope.get("brand_id"),
        "requested_brand_id": requested_brand_id,
        "schedule_id": schedule_id,
        "max_attempts": max_attempts,
    }
    try:
        rq_job_id = enqueue_crawl(task_meta)
        CrawlJobRepository().set_rq_job(job_id, rq_job_id)
    except Exception as exc:
        CrawlJobRepository().finish(job_id, status="failed", result={"error": f"入队失败: {exc}"})
        CollectionRunRepository().finish_collection(
            collection_run["collection_run_id"],
            status="failed",
            failure_reason=f"任务入队失败: {exc}",
        )
        raise CrawlJobEnqueueError(f"任务入队失败，请检查 Redis: {exc}") from exc

    return {
        "job_id": job_id,
        "rq_job_id": rq_job_id,
        "status": "pending",
        "scope_id": scope["scope_id"],
        "collection_run_id": collection_run["collection_run_id"],
        "created_at": str(created_at),
    }
