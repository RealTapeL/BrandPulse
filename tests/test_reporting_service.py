from datetime import date, timedelta

import pytest

from brandpulse.reporting import service


class _ScopeRepository:
    def __init__(self, scope):
        self.scope = scope

    def get(self, scope_id):
        return self.scope if scope_id == self.scope["scope_id"] else None


def _scope():
    return {
        "scope_id": "scope_test",
        "brand_id": "MALL_test",
        "city": "苏州",
        "mall_name": "测试项目",
        "category": "咖啡",
        "latest_xiaohongshu_date": date.today().isoformat(),
    }


def test_report_readiness_accepts_fresh_real_snapshot_shape(monkeypatch):
    scope = _scope()
    monkeypatch.setattr(service, "MonitoringScopeRepository", lambda: _ScopeRepository(scope))
    monkeypatch.setattr(service, "build_dashboard", lambda scope_id: {
        "scope": scope,
        "stat_date": date.today().isoformat(),
        "crawl_date": date.today().isoformat(),
        "indicators": [{"entity_name": "门店 A", "heat_index": 70}],
        "dp_shops": [{"shop_name": "门店 A", "review_count": 100}],
        "xhs_notes": [{"title": "真实来源记录"}],
    })

    readiness = service.report_readiness("scope_test")

    assert readiness["ready"] is True
    assert readiness["reasons"] == []


def test_report_readiness_rejects_stale_snapshot(monkeypatch):
    scope = {**_scope(), "latest_xiaohongshu_date": (date.today() - timedelta(days=10)).isoformat()}
    monkeypatch.setattr(service, "MonitoringScopeRepository", lambda: _ScopeRepository(scope))
    stale = (date.today() - timedelta(days=10)).isoformat()
    monkeypatch.setattr(service, "build_dashboard", lambda scope_id: {
        "scope": scope,
        "stat_date": stale,
        "crawl_date": stale,
        "indicators": [{"entity_name": "门店 A", "heat_index": 70}],
        "dp_shops": [{"shop_name": "门店 A", "review_count": 100}],
        "xhs_notes": [{"title": "真实来源记录"}],
    })

    with pytest.raises(service.ReportDataNotReadyError, match="超过"):
        service.require_report_ready("scope_test")
