"""操作审计中间件与查询 API 契约。"""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.config.config import Config
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS


def test_mutating_request_is_audited_without_body(monkeypatch):
    monkeypatch.setattr(Config, "AUDIT_ENABLED", True)
    client = TestClient(app, headers=AUTH_HEADERS)
    formula_id = None
    request_ids = []
    payload = {
        "name": f"审计测试公式_{uuid4().hex[:10]}",
        "description": "审计契约测试",
        "expression": "100 * ln(1 + review_count)",
        "params": [],
        "enabled": True,
        "remark": "不应进入审计详情",
    }
    try:
        created = client.post("/api/v1/formulas", json=payload)
        assert created.status_code == 200
        request_ids.append(created.headers["x-request-id"])
        formula_id = created.json()["id"]

        response = client.get(
            "/api/v1/audit/events",
            params={"request_id": request_ids[0]},
        )
        assert response.status_code == 200
        event = response.json()["items"][0]
        assert event["actor_id"] == "test-operator"
        assert event["action"] == "POST /api/v1/formulas"
        assert event["outcome"] == "success"
        assert event["status_code"] == 200
        assert "remark" not in str(event["details"])
        assert "审计契约测试" not in str(event["details"])
    finally:
        if formula_id:
            deleted = client.delete(f"/api/v1/formulas/{formula_id}")
            if deleted.headers.get("x-request-id"):
                request_ids.append(deleted.headers["x-request-id"])
        if request_ids:
            with PostgresClient().engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM audit_events WHERE request_id = ANY(:request_ids)
                """), {"request_ids": request_ids})
