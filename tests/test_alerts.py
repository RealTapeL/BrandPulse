"""
alerts API 单元测试：CRUD + 手动触发。
依赖 PostgresClient，使用真实数据库 brandpulse。
"""
import pytest
from fastapi.testclient import TestClient

from brandpulse.alerts.service import process_due_deliveries, record_evaluation
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
    assert data["cooldown_minutes"] == 60
    assert data["notify_recovery"] is True

    try:
        # list
        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        assert any(a["id"] == alert_id for a in resp.json())

        # update
        updated_destinations = [{"type": "email", "value": "updated-ops@example.com"}]
        resp = client.put(
            f"/api/v1/alerts/{alert_id}",
            json={
                "threshold": 5,
                "destinations": updated_destinations,
                "cooldown_minutes": 120,
                "notify_recovery": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["threshold"] == 5
        assert resp.json()["destinations"] == updated_destinations
        assert resp.json()["cooldown_minutes"] == 120
        assert resp.json()["notify_recovery"] is False
    finally:
        client.delete(f"/api/v1/alerts/{alert_id}")


def test_alert_state_machine_deduplicates_and_recovers(alert_payload, monkeypatch):
    payload = {
        **alert_payload,
        "name": "告警状态机测试",
        "enabled": False,
    }
    resp = client.post("/api/v1/alerts", json=payload)
    assert resp.status_code == 200
    alert = resp.json()
    alert_id = alert["id"]
    monkeypatch.setattr(
        "brandpulse.alerts.service.send",
        lambda *args, **kwargs: [{"type": "email", "status": "sent"}],
    )
    try:
        first = record_evaluation(alert, triggered=True, value=5)
        duplicate = record_evaluation(alert, triggered=True, value=5)
        assert first["event_type"] == "trigger"
        assert len(first["delivery_ids"]) == 1
        assert duplicate["event_type"] == "check"
        assert duplicate["delivery_ids"] == []
        assert process_due_deliveries()["sent"] == 1

        recovery = record_evaluation(alert, triggered=False, value=20)
        assert recovery["event_type"] == "recovery"
        assert len(recovery["delivery_ids"]) == 1
        assert process_due_deliveries()["sent"] == 1

        history = client.get(f"/api/v1/alerts/{alert_id}/history").json()["items"]
        assert [item["event_type"] for item in history[:3]] == [
            "recovery", "check", "trigger",
        ]
        assert history[0]["notification_status"] == "sent"
        assert history[1]["notification_status"] == "suppressed"
        assert history[2]["notification_status"] == "sent"
    finally:
        client.delete(f"/api/v1/alerts/{alert_id}")


def test_alert_delivery_failure_is_retried(alert_payload, monkeypatch):
    payload = {
        **alert_payload,
        "name": "告警重试测试",
        "enabled": False,
    }
    resp = client.post("/api/v1/alerts", json=payload)
    assert resp.status_code == 200
    alert = resp.json()
    alert_id = alert["id"]
    monkeypatch.setattr(
        "brandpulse.alerts.service.send",
        lambda *args, **kwargs: [{"type": "email", "error": "test failure"}],
    )
    try:
        record_evaluation(alert, triggered=True, value=5)
        assert process_due_deliveries()["retry"] == 1
        delivery = client.get(
            "/api/v1/alerts/deliveries/list", params={"alert_id": alert_id}
        ).json()["items"][0]
        assert delivery["status"] == "retry"
        assert delivery["attempt_count"] == 1
        assert delivery["last_error"] == "test failure"
    finally:
        client.delete(f"/api/v1/alerts/{alert_id}")


def test_check_now_does_not_crash():
    resp = client.post("/api/v1/alerts/check-now")
    # 即便 indicators 无数据，也不应 500
    assert resp.status_code == 200
    assert "triggered" in resp.json()


@pytest.mark.parametrize("destination", [
    {"type": "email", "value": "not-an-email"},
    {"type": "webhook", "value": "example.com/hook"},
    {"type": "unknown", "value": "anything"},
])
def test_alert_rejects_invalid_destination(alert_payload, destination):
    response = client.post(
        "/api/v1/alerts",
        json={**alert_payload, "destinations": [destination]},
    )
    assert response.status_code == 422
