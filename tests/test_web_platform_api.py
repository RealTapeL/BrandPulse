"""新增 Web 平台接口的持久化与轮询契约测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient

from brandpulse.api import agent as agent_api
from brandpulse.api.app import app
from brandpulse.storage.agent_task_repository import AgentTaskRepository
from tests.conftest import AUTH_HEADERS


def test_formula_crud():
    client = TestClient(app, headers=AUTH_HEADERS)
    name = f"测试公式_{uuid4().hex[:8]}"
    payload = {
        "name": name,
        "description": "用于 API 契约测试",
        "expression": "100 * ln(1 + review_count)",
        "params": [{"key": "review_count", "value": "0"}],
        "enabled": True,
        "remark": "",
    }
    created = client.post("/api/v1/formulas", json=payload)
    assert created.status_code == 200
    formula_id = created.json()["id"]

    updated = client.put(f"/api/v1/formulas/{formula_id}", json={**payload, "remark": "已更新"})
    assert updated.status_code == 200
    assert updated.json()["remark"] == "已更新"

    deleted = client.delete(f"/api/v1/formulas/{formula_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}


def test_agent_task_can_be_created_and_queried(monkeypatch):
    monkeypatch.setattr(agent_api, "enqueue_agent", lambda _task_id: "rq-agent-test")
    client = TestClient(app, headers=AUTH_HEADERS)

    created = client.post("/api/v1/agent/execute", json={"prompt": "列出当前数据表", "context": {"city": "苏州"}})
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    fetched = client.get(f"/api/v1/agent/tasks/{task_id}")
    assert fetched.status_code == 200
    data = fetched.json()
    assert data["id"] == task_id
    assert data["status"] == "pending"
    assert data["input"] == "列出当前数据表"
    assert data["rq_job_id"] == "rq-agent-test"


def test_agent_enqueue_failure_is_persisted_as_failed(monkeypatch):
    def fail_enqueue(_task_id):
        raise agent_api.AgentTaskEnqueueError("Redis 不可用")

    monkeypatch.setattr(agent_api, "enqueue_agent", fail_enqueue)
    client = TestClient(app, headers=AUTH_HEADERS)

    response = client.post("/api/v1/agent/execute", json={"prompt": "测试入队失败"})
    assert response.status_code == 503

    tasks = AgentTaskRepository().list(status="failed", limit=20, offset=0)
    assert any(item["input"] == "测试入队失败" and "Redis 不可用" in (item["error"] or "") for item in tasks["items"])


def test_agent_task_history_can_be_listed():
    client = TestClient(app, headers=AUTH_HEADERS)
    response = client.get("/api/v1/agent/tasks", params={"size": 10})
    assert response.status_code == 200
    assert "items" in response.json()
