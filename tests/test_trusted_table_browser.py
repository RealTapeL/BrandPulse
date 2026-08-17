"""数据中心浏览器只允许按可信 scope 读取原始观测与快照指标。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS

client = TestClient(app, headers=AUTH_HEADERS)


@pytest.fixture
def scope_id():
    with PostgresClient().engine.connect() as conn:
        value = conn.execute(text("""
            SELECT scope_id FROM trusted_monitoring_scopes
            WHERE status = 'active'
            ORDER BY created_at
            LIMIT 1
        """)).scalar()
    if not value:
        pytest.skip("暂无可信监测范围")
    return value


def test_scope_bound_tables_require_and_apply_scope(scope_id):
    missing_scope = client.get("/api/v1/tables/raw_observations")
    assert missing_scope.status_code == 422

    raw = client.get("/api/v1/tables/raw_observations", params={"scope_id": scope_id})
    assert raw.status_code == 200, raw.text
    assert "rows" in raw.json()

    metrics = client.get("/api/v1/tables/metric_observations", params={"scope_id": scope_id})
    assert metrics.status_code == 200, metrics.text
    assert "rows" in metrics.json()


def test_legacy_indicator_table_is_not_exposed_by_new_browser():
    response = client.get("/api/v1/tables/brand_indicators_daily")
    assert response.status_code == 404
