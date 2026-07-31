"""Web 登录 API 使用环境驱动的单团队认证模式。"""
from fastapi.testclient import TestClient

from brandpulse.api.app import app


def test_local_login_returns_session_token():
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"username": "operator", "password": "pass"})

    assert response.status_code == 200
    data = response.json()
    assert data["token"]
    assert data["user"] == {"id": "operator", "username": "operator", "role": "operator"}
