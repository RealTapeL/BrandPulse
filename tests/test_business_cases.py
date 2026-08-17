"""业务事项 API：可分派、可反馈并保留来源处理记录。"""

from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS


client = TestClient(app, headers=AUTH_HEADERS)


def test_manual_case_lifecycle_keeps_events():
    response = client.post("/api/v1/cases", json={
        "case_type": "manual", "source_type": "manual", "source_id": "pytest:business-case",
        "title": "pytest 事项生命周期", "description": "仅用于验证事项闭环", "priority": "normal",
    })
    assert response.status_code == 200
    case_id = response.json()["case_id"]
    try:
        progress = client.put(f"/api/v1/cases/{case_id}", json={
            "status": "in_progress", "owner_id": "test-operator", "note": "开始核对来源证据",
        })
        assert progress.status_code == 200
        assert progress.json()["status"] == "in_progress"

        closed = client.put(f"/api/v1/cases/{case_id}", json={
            "status": "resolved", "feedback": "valid", "outcome": "已完成验证", "note": "结案",
        })
        assert closed.status_code == 200
        assert closed.json()["feedback"] == "valid"

        detail = client.get(f"/api/v1/cases/{case_id}")
        assert detail.status_code == 200
        assert {event["action"] for event in detail.json()["events"]} >= {
            "created", "assigned", "status_changed", "feedback_recorded", "closed",
        }
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text("DELETE FROM business_cases WHERE case_id = :case_id"), {"case_id": case_id})
