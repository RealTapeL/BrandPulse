"""自定义公式必须绑定真实 scope 快照，不能回退到旧 brand/date 聚合。"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS

client = TestClient(app, headers=AUTH_HEADERS)


@pytest.fixture
def snapshot_scope():
    with PostgresClient().engine.connect() as conn:
        row = conn.execute(text("""
            SELECT snapshot.scope_id, snapshot.snapshot_id
            FROM data_snapshots AS snapshot
            JOIN metric_observations AS metric ON metric.snapshot_id = snapshot.snapshot_id
            WHERE snapshot.status IN ('ready', 'published')
              AND metric.entity_type = 'scope'
              AND metric.metric_key = 'source_coverage_ratio'
              AND metric.quality_status = 'valid'
              AND metric.value IS NOT NULL
            ORDER BY snapshot.observed_at DESC
            LIMIT 1
        """)).mappings().first()
    if not row:
        pytest.skip("暂无包含可信 scope 指标的实际快照")
    return dict(row)


def test_formula_runs_against_scope_snapshot_and_persists_evidence(snapshot_scope):
    name = f"pytest-snapshot-formula-{uuid4().hex[:12]}"
    created = client.post("/api/v1/formulas", json={
        "name": name,
        "description": "测试：使用真实快照来源覆盖率",
        "expression": "source_coverage_ratio * 100",
        "params": [],
        "enabled": True,
    })
    assert created.status_code == 200, created.text
    formula_id = created.json()["id"]
    try:
        missing_scope = client.post(f"/api/v1/formulas/{formula_id}/run")
        assert missing_scope.status_code == 422

        response = client.post(
            f"/api/v1/formulas/{formula_id}/run",
            params={"scope_id": snapshot_scope["scope_id"], "snapshot_id": snapshot_scope["snapshot_id"]},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["saved"] == 1
        assert result["snapshot_id"] == snapshot_scope["snapshot_id"]
        assert result["evaluations"][0]["status"] == "completed"
        assert result["evaluations"][0]["scope_id"] == snapshot_scope["scope_id"]

        values = client.get(
            f"/api/v1/formulas/{formula_id}/values",
            params={"scope_id": snapshot_scope["scope_id"]},
        )
        assert values.status_code == 200
        payload = values.json()
        assert payload["mode"] == "snapshot"
        assert payload["values"][0]["snapshot_id"] == snapshot_scope["snapshot_id"]
        assert "source_coverage_ratio" in payload["values"][0]["input_metrics"]
    finally:
        client.delete(f"/api/v1/formulas/{formula_id}")
