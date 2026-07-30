"""
worker.run_crawl_job 单元测试：把 run_mall_crawl 打桩，验证传入参数与返回值。
"""
from brandpulse.collectors import worker


def test_run_crawl_job_calls_mall_crawl(monkeypatch):
    calls = []

    def fake_run(mall, category, city):
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
