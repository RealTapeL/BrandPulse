"""生产 RBAC 登录、会话撤销、强制改密和权限边界契约。"""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.config.config import Config
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.security.passwords import hash_password
from brandpulse.storage.auth_repository import AuthRepository


def _enable_rbac(monkeypatch):
    monkeypatch.setattr(Config, "AUTH_MODE", "rbac")
    monkeypatch.setattr(Config, "AUTH_SECRET", "rbac-test-secret-" * 5)
    monkeypatch.setattr(Config, "AUTH_COOKIE_SECURE", False)
    monkeypatch.setattr(Config, "AUTH_COOKIE_SAMESITE", "strict")


def _create_user(repository, username, role, password, *, must_change_password=False):
    return repository.create_user(
        username=username,
        password_hash=hash_password(password),
        role=role,
        created_by=None,
        must_change_password=must_change_password,
    )


def _delete_users(user_ids):
    with PostgresClient().engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_users WHERE user_id = ANY(:user_ids)"), {"user_ids": user_ids})


def test_rbac_viewer_cannot_operate_and_refresh_logout_revoke_session(monkeypatch):
    _enable_rbac(monkeypatch)
    monkeypatch.setattr(Config, "AUDIT_ENABLED", True)
    repository = AuthRepository()
    suffix = uuid4().hex
    viewer = _create_user(repository, f"viewer_{suffix}", "viewer", "ViewerPass!2026-strong")
    admin = _create_user(repository, f"admin_{suffix}", "admin", "AdminPass!2026-strong")
    client = TestClient(app)
    admin_client = TestClient(app)
    audit_request_ids = []
    try:
        login = client.post("/api/v1/auth/login", json={
            "username": viewer["username"], "password": "ViewerPass!2026-strong",
        })
        assert login.status_code == 200
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "viewer"
        assert client.post("/api/v1/agent/execute", headers=headers, json={"prompt": "刷新指标"}).status_code == 403
        assert client.get("/api/v1/system/configuration", headers=headers).status_code == 403
        denied = client.get("/api/v1/users", headers=headers)
        assert denied.status_code == 403
        audit_request_ids.append(denied.headers["x-request-id"])

        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        refreshed_headers = {"Authorization": f"Bearer {refreshed.json()['token']}"}
        assert client.post("/api/v1/auth/logout", headers=refreshed_headers).status_code == 204
        assert client.get("/api/v1/auth/me", headers=refreshed_headers).status_code == 401

        admin_login = admin_client.post("/api/v1/auth/login", json={
            "username": admin["username"], "password": "AdminPass!2026-strong",
        })
        assert admin_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['token']}"}
        assert admin_client.get("/api/v1/users", headers=admin_headers).status_code == 200
        audited = admin_client.get("/api/v1/audit/events", headers=admin_headers, params={
            "request_id": audit_request_ids[0],
        })
        assert audited.status_code == 200
        event = audited.json()["items"][0]
        assert event["status_code"] == 403
        assert event["details"]["permission_denied"] is True
        assert event["details"]["required_permission"] == "user.manage"
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM audit_events
                WHERE request_id = ANY(:request_ids)
                   OR actor_id = ANY(:actor_ids)
            """), {
                "request_ids": audit_request_ids,
                "actor_ids": [viewer["user_id"], admin["user_id"]],
            })
        _delete_users([viewer["user_id"], admin["user_id"]])


def test_rbac_temporary_password_must_be_changed_before_business_access(monkeypatch):
    _enable_rbac(monkeypatch)
    repository = AuthRepository()
    username = f"temporary_{uuid4().hex}"
    user = _create_user(
        repository, username, "operator", "TemporaryPass!2026", must_change_password=True
    )
    client = TestClient(app)
    try:
        login = client.post("/api/v1/auth/login", json={"username": username, "password": "TemporaryPass!2026"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        blocked = client.get("/api/v1/brands", headers=headers)
        assert blocked.status_code == 403
        assert "先修改密码" in blocked.json()["detail"]
        changed = client.post("/api/v1/auth/change-password", headers=headers, json={
            "current_password": "TemporaryPass!2026",
            "new_password": "ChangedPass!2026-strong",
        })
        assert changed.status_code == 204
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    finally:
        _delete_users([user["user_id"]])
