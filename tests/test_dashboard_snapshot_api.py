"""看板只能读取一个明确的 released snapshot，且不回退到旧热度指标。"""

import pytest
from fastapi.testclient import TestClient

from brandpulse.api.app import app
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from tests.conftest import AUTH_HEADERS


def test_dashboard_returns_snapshot_bound_metrics_without_legacy_heat():
    scope = next(
        (item for item in MonitoringScopeRepository().list() if item.get("latest_snapshot_id")),
        None,
    )
    if not scope:
        pytest.skip("测试数据库没有已发布或就绪快照")

    response = TestClient(app, headers=AUTH_HEADERS).get(
        "/api/v1/dashboard", params={"scope_id": scope["scope_id"]}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["snapshot_id"] == scope["latest_snapshot_id"]
    assert payload["snapshot"]["scope_id"] == scope["scope_id"]
    assert all(item["heat_index"] is None for item in payload["indicators"])
    assert all(item["detail"]["snapshot_id"] == payload["snapshot"]["snapshot_id"] for item in payload["indicators"])
    assert any(item["metric_key"] == "source_coverage_ratio" for item in payload["metric_summary"])
