"""
RQ worker 实际执行函数：运行商场×品类采集，并把结果摘要写入数据库 crawl_jobs 记录。

因为 Prompt A 决定不新增 Scrapy/Playwright 模板，worker 直接复用现有品牌情报采集入口
main.run_mall_crawl（Kimi WebBridge 驱动大众点评 + 小红书）。
TODO: 后端 /api/v1/data/raw 就绪后，把原始 JSON 通过 POST 上传而非仅更新 job 摘要。
"""
import sys
import json
from pathlib import Path

# main.py 不在 brandpulse 包内，把 src/backend 加入 path
src_dir = str(Path(__file__).resolve().parents[2])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
import main  # noqa: E402

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


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

    logger.info(f"[worker] start crawl job: id={job_id}, brand_id={brand_id}, mall={mall}, category={category}, city={city}")
    if job_id:
        _update_job(job_id, status="running")
    try:
        stats = main.run_mall_crawl(mall=mall, category=category, city=city)
    except Exception as exc:
        if job_id:
            _update_job(job_id, status="failed", result={"error": str(exc)})
        raise

    if job_id:
        _update_job(job_id, status="completed", result=stats)
    return stats


def _update_job(job_id: str, status: str, result: dict | None = None) -> None:
    """按唯一 job_id 更新任务状态，避免并发任务互相覆盖。"""
    sql = """
        UPDATE crawl_jobs
        SET status = :status,
            result = COALESCE(:result, result),
            finished_at = CASE
                WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP
                ELSE finished_at
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = :job_id
        RETURNING job_id
    """
    try:
        client = PostgresClient()
        result = client.execute(sql, {
            "job_id": job_id,
            "status": status,
            "result": json.dumps(result, ensure_ascii=False) if result is not None else None,
        })
        rows = result.fetchall() if result else []
        logger.info(f"[worker] updated {len(rows)} crawl_jobs for {job_id}: {status}")
    except Exception as e:
        logger.error(f"[worker] failed to update crawl_jobs: {e}")
