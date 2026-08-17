"""
alerts API 单元测试：CRUD + 手动触发。
依赖 PostgresClient，使用真实数据库 brandpulse。
"""
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from brandpulse.alerts.service import process_due_deliveries, record_evaluation
from brandpulse.alerts import scheduler as alert_scheduler
from brandpulse.api.app import app
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS

client = TestClient(app, headers=AUTH_HEADERS)


def _delete_test_case(case_id):
    if not case_id:
        return
    with PostgresClient().engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM business_cases WHERE case_id = :case_id"), {"case_id": case_id})


@pytest.fixture
def alert_payload():
    with PostgresClient().engine.connect() as conn:
        scope_id = conn.execute(text("""
            SELECT scope_id FROM trusted_monitoring_scopes
            WHERE status = 'active'
            ORDER BY created_at
            LIMIT 1
        """)).scalar()
    if not scope_id:
        pytest.skip("可信监测范围尚未初始化")
    return {
        "name": "来源覆盖率阈值测试",
        "scope_id": scope_id,
        "metric": "source_coverage_ratio",
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
    assert data["metric"] == "source_coverage_ratio"
    assert data["scope_id"] == alert_payload["scope_id"]
    assert data["rule_scope_status"] == "trusted_scope"
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
    first = {}
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
        _delete_test_case(first.get("case_id"))
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
    first = {}
    try:
        first = record_evaluation(alert, triggered=True, value=5)
        assert process_due_deliveries()["retry"] == 1
        delivery = client.get(
            "/api/v1/alerts/deliveries/list", params={"alert_id": alert_id}
        ).json()["items"][0]
        assert delivery["status"] == "retry"
        assert delivery["attempt_count"] == 1
        assert delivery["last_error"] == "test failure"
    finally:
        _delete_test_case(first.get("case_id"))
        client.delete(f"/api/v1/alerts/{alert_id}")


def test_check_now_does_not_crash(monkeypatch):
    monkeypatch.setattr("brandpulse.api.alerts.check_all_alerts", lambda: 0)
    resp = client.post("/api/v1/alerts/check-now")
    # 即便 indicators 无数据，也不应 500
    assert resp.status_code == 200
    assert "triggered" in resp.json()


def test_trusted_alert_check_uses_scope_snapshot_evidence(alert_payload, monkeypatch):
    resp = client.post("/api/v1/alerts", json={**alert_payload, "destinations": [], "enabled": False})
    assert resp.status_code == 200
    alert = resp.json()
    captured = {}
    try:
        def fake_evidence(metric_key, scope_id):
            captured["metric_key"] = metric_key
            captured["scope_id"] = scope_id
            return {
                "value": 0.2,
                "scope_id": scope_id,
                "snapshot_id": "snapshot_test_evidence",
                "metric_key": metric_key,
                "metric_quality": "valid",
                "evidence": {"source": "test"},
            }

        monkeypatch.setattr(alert_scheduler, "_fetch_metric_evidence", fake_evidence)
        monkeypatch.setattr(
            alert_scheduler,
            "record_evaluation",
            lambda checked_alert, **kwargs: {
                "event_type": "check", "skipped": False, "triggered": kwargs["triggered"],
            },
        )
        assert alert_scheduler._check_alert(dict(alert)) is True
        assert captured == {
            "metric_key": "source_coverage_ratio",
            "scope_id": alert_payload["scope_id"],
        }
    finally:
        client.delete(f"/api/v1/alerts/{alert['id']}")


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
