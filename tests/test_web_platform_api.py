"""新增 Web 平台接口的持久化与轮询契约测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient

from brandpulse.api import agent as agent_api
from brandpulse.api.app import app


def test_formula_crud():
    client = TestClient(app)
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
    monkeypatch.setattr(agent_api, "run_agent_task", lambda _task_id: None)
    client = TestClient(app)

    created = client.post("/api/v1/agent/execute", json={"prompt": "列出当前数据表", "context": {"city": "苏州"}})
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    fetched = client.get(f"/api/v1/agent/tasks/{task_id}")
    assert fetched.status_code == 200
    data = fetched.json()
    assert data["id"] == task_id
    assert data["status"] == "pending"
    assert data["input"] == "列出当前数据表"
