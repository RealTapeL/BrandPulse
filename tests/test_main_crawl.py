from brandpulse.collectors import worker
from brandpulse.db_clients.postgres_client import PostgresClient
from sqlalchemy import text


def test_mall_crawl_keeps_source_level_results(monkeypatch):
    """商场级任务应保留每个来源的状态，不能用一个总 raw 数掩盖空来源。"""

    class FakeCrawler:
        def list_sites(self):
            return ["dianping_webbridge", "xiaohongshu_webbridge"]

    calls = []

    def fake_run_from_config(*, site_id, **_kwargs):
        calls.append(site_id)
        if site_id == "dianping_webbridge":
            return {"records": [{"shop_name": "门店 A"}], "raw_saved": 1, "heat_saved": 1, "cached": 1}
        return {"records": [], "raw_saved": 0, "heat_saved": 1, "cached": 0}

    class FakeGovernance:
        def scan(self, trigger_type):
            return {"status": "completed", "trigger_type": trigger_type}

    monkeypatch.setattr("brandpulse.collectors.crawler.GenericWebCrawler", FakeCrawler)
    monkeypatch.setattr("brandpulse.collectors.crawler.run_from_config", fake_run_from_config)
    monkeypatch.setattr("brandpulse.data_governance.service.DataGovernanceService", FakeGovernance)
    monkeypatch.setattr("brandpulse.indicators.pipeline.run", lambda: {"口碑": 1})

    result = None
    try:
        result = worker.main.run_mall_crawl(
            mall="苏州中心",
            category="咖啡",
            city="苏州",
            brand_id="MALL_906d5b65",
        )

        assert calls == ["dianping_webbridge", "xiaohongshu_webbridge"]
        assert result["raw"] == 1
        assert result["source_results"]["dianping_webbridge"]["status"] == "success"
        assert result["source_results"]["xiaohongshu_webbridge"]["status"] == "empty_validated"
        # 假 connector 只伪造返回值而没有写入 raw_observations；快照必须拒绝发布。
        assert result["snapshot"]["status"] == "failed"
    finally:
        if result and result.get("collection_run_id"):
            with PostgresClient().engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM data_snapshots WHERE collection_run_id = :collection_run_id"
                ), {"collection_run_id": result["collection_run_id"]})
                conn.execute(text(
                    "DELETE FROM collection_runs WHERE collection_run_id = :collection_run_id"
                ), {"collection_run_id": result["collection_run_id"]})
