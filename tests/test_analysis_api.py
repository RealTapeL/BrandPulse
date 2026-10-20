"""Phase 2～4 统一分析 API 回归测试。"""

import pytest
from fastapi.testclient import TestClient

from brandpulse.api.app import app
from brandpulse.analysis.service import parse_brand_ids
from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository
from tests.conftest import AUTH_HEADERS


def _scope_with_snapshot():
    return next(
        (scope for scope in TrustedScopeRepository().list() if scope.get("latest_snapshot_id")),
        None,
    )


def test_parse_brand_ids_is_bounded_and_deduplicated():
    assert parse_brand_ids("LK001, KD001, LK001, SB001, X001, X002") == [
        "LK001", "KD001", "SB001", "X001", "X002",
    ]


def test_analysis_requires_explicit_scope():
    response = TestClient(app, headers=AUTH_HEADERS).get("/api/v1/analysis")
    assert response.status_code == 422


def test_analysis_overview_returns_reproducible_evidence_boundary():
    scope = _scope_with_snapshot()
    if not scope:
        pytest.skip("测试数据库没有 ready/published 快照")

    response = TestClient(app, headers=AUTH_HEADERS).get(
        "/api/v1/analysis",
        params={"scope_id": scope["scope_id"], "view": "overview"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"]["scope_id"] == scope["scope_id"]
    assert payload["snapshot"]["snapshot_id"] == scope["latest_snapshot_id"]
    assert payload["filters"]["scope_id"] == scope["scope_id"]
    assert payload["metrics"]
    assert all(item["snapshot_id"] in {payload["snapshot"]["snapshot_id"], None} for item in payload["metrics"])
    assert all("snapshot_id" in item for item in payload["evidence"])
    assert all(not str(item.get("brand_id", "")).startswith("MALL_") for item in payload["ranking"])


def test_analysis_trend_has_no_fake_points_when_data_is_missing():
    scope = _scope_with_snapshot()
    if not scope:
        pytest.skip("测试数据库没有 ready/published 快照")

    response = TestClient(app, headers=AUTH_HEADERS).get(
        "/api/v1/analysis",
        params={
            "scope_id": scope["scope_id"],
            "view": "trend",
            "metric_key": "xhs_content_count_observed",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert all(point["snapshot_id"] for point in payload["series"])
    assert payload["comparison"]["available"] is False or len(payload["series"]) >= 2


def test_metric_catalog_exposes_quality_and_prediction_gates():
    response = TestClient(app, headers=AUTH_HEADERS).get("/api/v1/analysis/metrics")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert {"formula", "minimum_sample_size", "quality_requirements", "allow_alert", "allow_prediction"}.issubset(items[0])
