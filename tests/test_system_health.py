"""系统探针和 Prometheus 暴露契约。"""

from fastapi.testclient import TestClient

from brandpulse.api.app import app
from tests.conftest import ADMIN_AUTH_HEADERS


def test_liveness_does_not_require_login():
    response = TestClient(app).get("/api/v1/system/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_checks_required_dependencies():
    response = TestClient(app).get("/api/v1/system/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["components"]["postgres"]["status"] == "ok"
    assert payload["components"]["redis"]["status"] == "ok"


def test_prometheus_metrics_are_exposed():
    client = TestClient(app)
    client.get("/api/v1/system/health/live")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "brandpulse_http_requests_total" in response.text


def test_configuration_status_is_protected_and_contains_no_secrets():
    anonymous = TestClient(app).get("/api/v1/system/configuration")
    assert anonymous.status_code == 401

    response = TestClient(app, headers=ADMIN_AUTH_HEADERS).get("/api/v1/system/configuration")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["production_ready"], bool)
    keys = {item["key"] for item in payload["checks"]}
    assert {"auth_mode", "auth_secret", "auth_account", "audit", "backup"} <= keys
    serialized = response.text.lower()
    assert "smtp_password" not in serialized
    assert "llm_api_key" not in serialized
    assert "postgres_password" not in serialized
