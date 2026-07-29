"""
大众点评 WebBridge Extractor 单元测试
"""
from brandpulse.collectors.extractors.dianping.webbridge_extractor import (
    _parse_search_text,
    _search_url,
)
from brandpulse.storage.pg_repository import MetricsRepository


class TestDianpingExtractor:
    def test_search_url_construction(self):
        url = _search_url("瑞幸咖啡", "北京")
        assert url is not None
        assert "/2/0_" in url  # 北京的城市 ID 实测为 2
        assert "%E7%91%9E%E5%B9%B8%E5%92%96%E5%95%A1" in url

    def test_search_url_suzhou_uses_verified_id(self):
        url = _search_url("瑞幸咖啡", "苏州")
        assert url is not None
        assert "/6/0_" in url  # 苏州的城市 ID 实测为 6

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

    def test_parse_search_text_fullwidth_yen(self):
        text = "瑞幸咖啡(长江新能源店) 暂停营业 1025 条评价 人均 ￥15"
        result = _parse_search_text(text)
        assert result["review_count"] == 1025
        assert result["avg_price"] == 15


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
