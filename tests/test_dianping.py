"""
大众点评爬虫单元测试
"""
from brandpulse.collectors.modules.dianping_crawler import (
    DianpingCrawler,
    _parse_search_text,
    _search_url,
    generate_mock_metrics,
)
from brandpulse.storage.modules.pg_repository import MetricsRepository


class TestDianpingCrawler:
    def test_search_url_construction(self):
        url = _search_url("瑞幸咖啡", "北京")
        assert url is not None
        assert "1" in url
        assert "%E7%91%9E%E5%B9%B8%E5%92%96%E5%95%A1" in url

    def test_search_url_unknown_city_returns_none(self):
        assert _search_url("瑞幸咖啡", "火星") is None

    def test_extract_search_result_handles_empty_html(self):
        result = _parse_search_text("")
        assert result is None or result["overall_score"] is None

    def test_parse_search_text(self):
        text = "瑞幸咖啡(国贸店) 4.5 1234条评论 人均¥18"
        result = _parse_search_text(text)
        assert result["overall_score"] == 4.5
        assert result["review_count"] == 1234
        assert result["avg_price"] == 18

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


class TestCookieLoader:
    def test_load_cookies_filters_by_domain(self, tmp_path, monkeypatch):
        from brandpulse.collectors.modules import cookie_loader
        from brandpulse.config.modules.config import Config

        monkeypatch.setattr(Config, "COOKIE_DIR", tmp_path)

        cookie_file = tmp_path / "dianping.json"
        cookie_file.write_text(
            '[{"name": "sess", "value": "abc", "domain": ".dianping.com", "path": "/"}, '
            '{"name": "other", "value": "xyz", "domain": ".example.com", "path": "/"}]',
            encoding="utf-8",
        )

        cookies = cookie_loader.load_cookies(domain_filter="dianping")
        assert len(cookies) == 1
        assert cookies[0]["name"] == "sess"
        assert cookies[0]["domain"] == ".dianping.com"
