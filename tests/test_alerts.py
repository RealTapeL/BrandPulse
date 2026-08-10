"""
alerts API 单元测试：CRUD + 手动触发。
依赖 PostgresClient，使用真实数据库 brandpulse。
"""
import pytest
from fastapi.testclient import TestClient

from brandpulse.api.app import app
from tests.conftest import AUTH_HEADERS

client = TestClient(app, headers=AUTH_HEADERS)


@pytest.fixture
def alert_payload():
    return {
        "name": "热度低于阈值测试",
        "brand_id": "MALL:苏州中心:苏州",
        "metric": "heat",
        "operator": "<",
        "threshold": 10,
        "destinations": [{"type": "email", "value": "ops@example.com"}],
    }


def test_alert_crud(alert_payload):
    # create
    resp = client.post("/api/v1/alerts", json=alert_payload)
    assert resp.status_code == 200
    data = resp.json()
    alert_id = data["id"]
    assert data["metric"] == "heat"

    # list
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    assert any(a["id"] == alert_id for a in resp.json())

    # update
    resp = client.put(f"/api/v1/alerts/{alert_id}", json={"threshold": 5})
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 5

    # delete
    resp = client.delete(f"/api/v1/alerts/{alert_id}")
    assert resp.status_code == 200


def test_check_now_does_not_crash():
    resp = client.post("/api/v1/alerts/check-now")
    # 即便 indicators 无数据，也不应 500
    assert resp.status_code == 200
    assert "triggered" in resp.json()
