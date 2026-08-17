"""数据库用户、刷新会话与账号状态仓储。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


def _as_user(row: Any, *, include_hash: bool = False) -> dict[str, Any]:
    item = dict(row)
    if not include_hash:
        item.pop("password_hash", None)
    for key in (
        "locked_until", "last_login_at", "password_changed_at", "created_at", "updated_at",
    ):
        if item.get(key) is not None:
            item[key] = str(item[key])
    return item


class AuthRepository:
    def __init__(self):
        self.client = PostgresClient()

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        created_by: Optional[str],
        must_change_password: bool = True,
    ) -> dict[str, Any]:
        user_id = str(uuid4())
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO auth_users (
                    user_id, username, username_normalized, password_hash, role,
                    must_change_password, created_by
                ) VALUES (
                    :user_id, :username, :username_normalized, :password_hash, :role,
                    :must_change_password, :created_by
                )
                RETURNING *
            """), {
                "user_id": user_id,
                "username": username,
                "username_normalized": username.casefold(),
                "password_hash": password_hash,
                "role": role,
                "must_change_password": must_change_password,
                "created_by": created_by,
            }).mappings().one()
        return _as_user(row)

    def get_user_by_id(self, user_id: str, *, include_hash: bool = False) -> Optional[dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth_users WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).mappings().first()
        return _as_user(row, include_hash=include_hash) if row else None

    def get_user_by_username(self, username: str, *, include_hash: bool = False) -> Optional[dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT * FROM auth_users WHERE username_normalized = :username_normalized
            """), {"username_normalized": username.casefold()}).mappings().first()
        return _as_user(row, include_hash=include_hash) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM auth_users ORDER BY created_at ASC, username_normalized ASC
            """)).mappings().all()
        return [_as_user(row) for row in rows]

    def active_admin_count(self) -> int:
        with self.client.engine.connect() as conn:
            return int(conn.execute(text("""
                SELECT COUNT(*) FROM auth_users WHERE role = 'admin' AND is_active = TRUE
            """)).scalar_one())

    def record_login_success(self, user_id: str, *, rehash: Optional[str] = None) -> dict[str, Any]:
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE auth_users
                SET failed_login_count = 0,
                    locked_until = NULL,
                    last_login_at = CURRENT_TIMESTAMP,
                    password_hash = COALESCE(:rehash, password_hash),
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                RETURNING *
            """), {"user_id": user_id, "rehash": rehash}).mappings().one()
        return _as_user(row)

    def record_login_failure(
        self, user_id: str, *, max_failures: int, lock_seconds: int
    ) -> dict[str, Any]:
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE auth_users
                SET failed_login_count = CASE
                        WHEN locked_until IS NOT NULL AND locked_until <= CURRENT_TIMESTAMP THEN 1
                        ELSE failed_login_count + 1
                    END,
                    locked_until = CASE
                        WHEN (CASE
                            WHEN locked_until IS NOT NULL AND locked_until <= CURRENT_TIMESTAMP THEN 1
                            ELSE failed_login_count + 1
                        END) >= :max_failures
                        THEN CURRENT_TIMESTAMP + (:lock_seconds * INTERVAL '1 second')
                        ELSE locked_until
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                RETURNING *
            """), {
                "user_id": user_id,
                "max_failures": max_failures,
                "lock_seconds": lock_seconds,
            }).mappings().one()
        return _as_user(row)

    def set_password(
        self, user_id: str, password_hash: str, *, must_change_password: bool
    ) -> Optional[dict[str, Any]]:
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE auth_users
                SET password_hash = :password_hash,
                    must_change_password = :must_change_password,
                    auth_revision = auth_revision + 1,
                    failed_login_count = 0,
                    locked_until = NULL,
                    password_changed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                RETURNING *
            """), {
                "user_id": user_id,
                "password_hash": password_hash,
                "must_change_password": must_change_password,
            }).mappings().first()
            if row:
                self._revoke_all_sessions(conn, user_id, "password_changed")
        return _as_user(row) if row else None

    def update_user(
        self,
        user_id: str,
        *,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        updates: list[str] = []
        params: dict[str, Any] = {"user_id": user_id}
        if role is not None:
            updates.append("role = :role")
            params["role"] = role
        if is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = is_active
        if not updates:
            return self.get_user_by_id(user_id)
        with self.client.engine.begin() as conn:
            row = conn.execute(text(f"""
                UPDATE auth_users
                SET {', '.join(updates)},
                    auth_revision = auth_revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                RETURNING *
            """), params).mappings().first()
            if row:
                self._revoke_all_sessions(conn, user_id, "account_changed")
        return _as_user(row) if row else None

    def create_refresh_session(
        self,
        *,
        user_id: str,
        refresh_token_digest: str,
        expires_at: datetime,
        client_ip: str,
        user_agent: str,
    ) -> dict[str, Any]:
        session_id = str(uuid4())
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO auth_refresh_sessions (
                    session_id, user_id, refresh_token_digest, expires_at, client_ip, user_agent
                ) VALUES (
                    :session_id, :user_id, :refresh_token_digest, :expires_at, :client_ip, :user_agent
                )
                RETURNING *
            """), {
                "session_id": session_id,
                "user_id": user_id,
                "refresh_token_digest": refresh_token_digest,
                "expires_at": expires_at,
                "client_ip": client_ip[:64],
                "user_agent": user_agent[:512],
            }).mappings().one()
        return dict(row)

    def get_active_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT session.*, user_.user_id, user_.username, user_.role, user_.is_active,
                       user_.must_change_password, user_.auth_revision
                FROM auth_refresh_sessions AS session
                JOIN auth_users AS user_ ON user_.user_id = session.user_id
                WHERE session.session_id = :session_id
                  AND session.revoked_at IS NULL
                  AND session.expires_at > CURRENT_TIMESTAMP
            """), {"session_id": session_id}).mappings().first()
        return dict(row) if row else None

    def rotate_refresh_session(
        self,
        *,
        previous_digest: str,
        next_digest: str,
        next_expires_at: datetime,
        client_ip: str,
        user_agent: str,
    ) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
        """原子轮换刷新令牌；旧令牌只能成功使用一次。"""
        with self.client.engine.begin() as conn:
            previous = conn.execute(text("""
                SELECT * FROM auth_refresh_sessions
                WHERE refresh_token_digest = :digest
                  AND revoked_at IS NULL
                  AND expires_at > CURRENT_TIMESTAMP
                FOR UPDATE
            """), {"digest": previous_digest}).mappings().first()
            if not previous:
                return None
            user = conn.execute(text("""
                SELECT * FROM auth_users WHERE user_id = :user_id FOR UPDATE
            """), {"user_id": previous["user_id"]}).mappings().first()
            if not user or not user["is_active"]:
                return None
            conn.execute(text("""
                UPDATE auth_refresh_sessions
                SET revoked_at = CURRENT_TIMESTAMP,
                    revoke_reason = 'rotated',
                    last_used_at = CURRENT_TIMESTAMP
                WHERE session_id = :session_id
            """), {"session_id": previous["session_id"]})
            session_id = str(uuid4())
            session = conn.execute(text("""
                INSERT INTO auth_refresh_sessions (
                    session_id, user_id, refresh_token_digest, expires_at, client_ip, user_agent
                ) VALUES (
                    :session_id, :user_id, :refresh_token_digest, :expires_at, :client_ip, :user_agent
                )
                RETURNING *
            """), {
                "session_id": session_id,
                "user_id": previous["user_id"],
                "refresh_token_digest": next_digest,
                "expires_at": next_expires_at,
                "client_ip": client_ip[:64],
                "user_agent": user_agent[:512],
            }).mappings().one()
        return _as_user(user), dict(session)

    def revoke_session_by_digest(self, digest: str, reason: str) -> None:
        with self.client.engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_refresh_sessions
                SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
                    revoke_reason = COALESCE(revoke_reason, :reason)
                WHERE refresh_token_digest = :digest
            """), {"digest": digest, "reason": reason[:128]})

    def revoke_all_sessions(self, user_id: str, reason: str) -> None:
        with self.client.engine.begin() as conn:
            self._revoke_all_sessions(conn, user_id, reason)

    @staticmethod
    def _revoke_all_sessions(conn: Any, user_id: str, reason: str) -> None:
        conn.execute(text("""
            UPDATE auth_refresh_sessions
            SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :user_id AND revoked_at IS NULL
        """), {"user_id": user_id, "reason": reason[:128]})

    def purge_expired_sessions(self) -> int:
        with self.client.engine.begin() as conn:
            result = conn.execute(text("""
                DELETE FROM auth_refresh_sessions
                WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
            """))
        return int(result.rowcount or 0)
