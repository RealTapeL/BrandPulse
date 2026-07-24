"""
大众点评爬虫单元测试
"""
from brandpulse.collectors.modules.dianping_crawler import (
    DianpingCrawler,
    generate_mock_metrics,
)
from brandpulse.storage.modules.pg_repository import MetricsRepository


class TestDianpingCrawler:
    def test_search_url_construction(self):
        crawler = DianpingCrawler()
        url = crawler._search_url("瑞幸咖啡", "北京")
        assert url is not None
        assert "1" in url
        assert "%E7%91%9E%E5%B9%B8%E5%92%96%E5%95%A1" in url

    def test_search_url_unknown_city_returns_none(self):
        crawler = DianpingCrawler()
        assert crawler._search_url("瑞幸咖啡", "火星") is None

    def test_extract_search_result_handles_empty_html(self):
        crawler = DianpingCrawler()
        result = crawler._extract_search_result("<html></html>")
        assert result is None

    def test_mock_metrics_shape(self):
        metrics = generate_mock_metrics("LK001", "瑞幸咖啡", cities=["北京"])
        assert len(metrics) == 1
        m = metrics[0]
        assert m["brand_id"] == "LK001"
        assert m["platform"] == "大众点评-mock"
        assert 0 <= m["overall_score"] <= 5
        assert m["review_count"] > 0
        assert m["avg_price"] > 0


class TestMetricsRepository:
    def test_upsert_and_list_metric(self):
        repo = MetricsRepository()
        metric = {
            "metric_id": "TEST_001",
            "brand_id": "TEST_BRAND",
            "metric_date": "2026-07-24",
            "platform": "大众点评-mock",
            "overall_score": 4.5,
            "review_count": 100,
            "avg_price": 25,
            "city_count": 1,
            "data_source": "test",
        }
        assert repo.upsert_metric(metric) is True

        metrics = repo.list_metrics(brand_id="TEST_BRAND")
        assert len(metrics) >= 1
        assert metrics[0]["brand_id"] == "TEST_BRAND"
