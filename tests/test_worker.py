"""
worker.run_crawl_job 单元测试：把 run_mall_crawl 打桩，验证传入参数与返回值。
"""
from uuid import uuid4

import pytest
from brandpulse.collectors import worker
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.crawl_job_repository import CrawlJobRepository
from sqlalchemy import text


def test_run_crawl_job_calls_mall_crawl(monkeypatch):
    calls = []

    def fake_run(mall, category, city, brand_id=None):
        calls.append((mall, category, city))
        return {"raw": 19, "heat": 2, "cached": 19, "sites": ["dianping", "xiaohongshu"]}

    monkeypatch.setattr(worker.main, "run_mall_crawl", fake_run)

    stats = worker.run_crawl_job({
        "brand_id": "LK001",
        "mall": "苏州中心",
        "category": "咖啡",
        "cities": ["苏州"],
    })

    assert stats["raw"] == 19
    assert calls == [("苏州中心", "咖啡", "苏州")]


def test_run_crawl_job_persists_terminal_status(monkeypatch):
    job_id = str(uuid4())
    PostgresClient().execute("""
        INSERT INTO crawl_jobs (job_id, brand_id, mall, category, cities, status, rq_job_id)
        VALUES (:job_id, 'LK001', '苏州中心', '咖啡', ARRAY['苏州'], 'pending', 'rq-worker-test')
    """, {"job_id": job_id})
    monkeypatch.setattr(worker.main, "run_mall_crawl", lambda **_kwargs: {"raw": 1, "heat": 1, "cached": 1, "sites": []})
    try:
        result = worker.run_crawl_job({
            "job_id": job_id,
            "brand_id": "LK001",
            "mall": "苏州中心",
            "category": "咖啡",
            "cities": ["苏州"],
        })
        row = CrawlJobRepository().get(job_id)
        assert result["raw"] == 1
        assert row["status"] == "completed"
        assert row["attempt_count"] == 1
        assert row["started_at"] is not None
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text("DELETE FROM crawl_jobs WHERE job_id = :job_id"), {"job_id": job_id})


def test_mall_scope_dataset_id_does_not_require_brand_master_record(monkeypatch):
    """MALL_* 是商场×品类范围 ID，重采时不能误校验为 brands 表品牌。"""

    class EmptyCrawler:
        def list_sites(self):
            return []

    monkeypatch.setattr("brandpulse.collectors.crawler.GenericWebCrawler", EmptyCrawler)
    with PostgresClient().engine.connect() as conn:
        before = set(conn.execute(text(
            "SELECT collection_run_id FROM collection_runs"
        )).scalars())
    try:
        with pytest.raises(RuntimeError, match="没有已启用的站点"):
            worker.main.run_mall_crawl(
                mall="苏州中心",
                category="咖啡",
                city="苏州",
                brand_id="MALL_906d5b65",
            )
    finally:
        with PostgresClient().engine.begin() as conn:
            created = list(conn.execute(text("""
                SELECT collection_run_id FROM collection_runs
                WHERE crawl_job_id IS NULL
            """)).scalars())
            created = [run_id for run_id in created if run_id not in before]
            if created:
                conn.execute(text(
                    "DELETE FROM data_snapshots WHERE collection_run_id = ANY(:run_ids)"
                ), {"run_ids": created})
                conn.execute(text(
                    "DELETE FROM collection_runs WHERE collection_run_id = ANY(:run_ids)"
                ), {"run_ids": created})
