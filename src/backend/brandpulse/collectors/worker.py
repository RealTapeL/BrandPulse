"""
RQ worker 实际执行函数：运行商场×品类采集，并把结果摘要写入数据库 crawl_jobs 记录。

因为 Prompt A 决定不新增 Scrapy/Playwright 模板，worker 直接复用现有品牌情报采集入口
main.run_mall_crawl（Kimi WebBridge 驱动大众点评 + 小红书）。
TODO: 后端 /api/v1/data/raw 就绪后，把原始 JSON 通过 POST 上传而非仅更新 job 摘要。
"""
import sys
from pathlib import Path

# main.py 不在 brandpulse 包内，把 src/backend 加入 path
src_dir = str(Path(__file__).resolve().parents[2])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
import main  # noqa: E402

from brandpulse.logger.logger import get_logger
from brandpulse.collectors.queue import enqueue_crawl
from brandpulse.storage.crawl_job_repository import CrawlJobRepository
from brandpulse.storage.monitoring_repository import CrawlScheduleRepository
from brandpulse.storage.trusted_data_repository import CollectionRunRepository

logger = get_logger(__name__)


def _source_warning(stats: dict) -> str | None:
    """把来源级空结果/失败压缩成计划可读的提示。"""
    source_results = stats.get("source_results") or {}
    incomplete = [
        f"{site_id}:{result.get('status')}"
        for site_id, result in source_results.items()
        if result.get("status") != "success"
    ]
    return "来源未完整成功：" + ", ".join(incomplete) if incomplete else None


def run_crawl_job(task_meta: dict) -> dict:
    """
    RQ 任务函数：执行一次采集任务。

    Args:
        task_meta: { brand_id, mall, category, cities? }

    Returns:
        { raw, heat, cached, sites } 采集摘要
    """
    job_id = task_meta.get("job_id")
    brand_id = task_meta["brand_id"]
    mall = task_meta["mall"]
    category = task_meta["category"]
    city = (task_meta.get("cities") or ["苏州"])[0]
    schedule_id = task_meta.get("schedule_id")
    collection_run_id = task_meta.get("collection_run_id")

    logger.info(f"[worker] start crawl job: id={job_id}, brand_id={brand_id}, mall={mall}, category={category}, city={city}")
    repository = CrawlJobRepository()
    if job_id and not repository.mark_running(job_id):
        logger.warning(f"[worker] skip terminal or missing crawl job: {job_id}")
        return {"status": "skipped", "job_id": job_id}
    try:
        crawl_kwargs = {
            "mall": mall,
            "category": category,
            "city": city,
            "brand_id": task_meta.get("requested_brand_id") or task_meta.get("legacy_dataset_key") or brand_id,
        }
        if job_id:
            crawl_kwargs["crawl_job_id"] = job_id
        if task_meta.get("scope_id"):
            crawl_kwargs["scope_id"] = task_meta["scope_id"]
        if collection_run_id:
            crawl_kwargs["collection_run_id"] = collection_run_id
            crawl_kwargs["trigger_type"] = task_meta.get("trigger_type") or "manual"
        stats = main.run_mall_crawl(
            **crawl_kwargs,
        )
        if not stats.get("raw"):
            warning = _source_warning(stats)
            detail = f"；{warning}" if warning else ""
            raise RuntimeError(f"采集未取得任何可验证记录，拒绝将空结果标记为成功{detail}")
    except Exception as exc:
        job = repository.get(job_id) if job_id else None
        attempts = int((job or {}).get("attempt_count") or 0)
        max_attempts = int(task_meta.get("max_attempts", 2))
        if job_id and attempts < max_attempts and repository.prepare_retry(job_id, str(exc)):
            delay_seconds = min(300, 30 * (2 ** max(attempts - 1, 0)))
            try:
                retry_job_id = enqueue_crawl(task_meta, delay_seconds=delay_seconds)
                repository.set_rq_job(job_id, retry_job_id)
                if schedule_id:
                    CrawlScheduleRepository().record_result(schedule_id, success=False, error=str(exc))
                logger.warning("[worker] crawl retry queued: id=%s attempt=%s/%s", job_id, attempts, max_attempts)
                return {"status": "retry_pending", "job_id": job_id, "error": str(exc)}
            except Exception as retry_exc:
                exc = RuntimeError(f"采集失败且延迟重试入队失败: {retry_exc}")
        if job_id:
            repository.finish(job_id, status="failed", result={"error": str(exc)})
        if collection_run_id:
            CollectionRunRepository().finish_collection(
                collection_run_id,
                status="failed",
                failure_reason=str(exc),
            )
        if schedule_id:
            CrawlScheduleRepository().record_result(schedule_id, success=False, error=str(exc))
        raise

    if job_id:
        repository.finish(job_id, status="completed", result=stats)
    if schedule_id:
        CrawlScheduleRepository().record_result(
            schedule_id,
            success=True,
            error=_source_warning(stats),
        )
    return stats
