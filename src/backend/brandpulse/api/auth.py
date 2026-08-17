"""登录、短期 Access Token、刷新会话与后端 RBAC 依赖。"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from brandpulse.config.config import Config
from brandpulse.security.passwords import (
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from brandpulse.security.permissions import (
    VALID_ROLES,
    has_permission,
    permission_for_request,
    permissions_for_role,
)
from brandpulse.storage.auth_repository import AuthRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_LOCAL_SIGNING_SECRET = secrets.token_urlsafe(64)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")


def _signing_secret() -> str:
    if Config.AUTH_SECRET:
        return Config.AUTH_SECRET
    if Config.AUTH_MODE == "local":
        return _LOCAL_SIGNING_SECRET
    raise HTTPException(status_code=503, detail="认证服务未完成安全配置")


def _utcnow() -> datetime:
    """数据库列使用无时区 UTC 时间，避免隐式服务器时区和废弃 API。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _refresh_digest(raw_token: str) -> str:
    return hmac.new(
        _signing_secret().encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def normalize_username(username: str) -> str:
    normalized = username.strip()
    if not _USERNAME_RE.fullmatch(normalized):
        raise ValueError("用户名需为 3-64 位字母、数字、点、下划线或连字符")
    return normalized


def create_access_token(
    username: str,
    role: str = "operator",
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    auth_revision: int = 0,
) -> str:
    """创建 15 分钟内有效的 Access Token；生产请求会二次核验数据库状态。"""
    issued_at = _utcnow()
    payload = {
        "sub": user_id or username,
        "username": username,
        "role": role if role in VALID_ROLES else "viewer",
        "ver": auth_revision,
        "sid": session_id or "",
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=Config.AUTH_ACCESS_TOKEN_TTL_SECONDS),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _signing_secret(), algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    """校验签名和过期时间；失败统一转换为 401。"""
    try:
        data = jwt.decode(token, _signing_secret(), algorithms=["HS256"])
        if not data.get("sub") or not data.get("username"):
            raise ValueError("invalid subject")
        return data
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from exc


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    role = str(user["role"])
    return {
        "id": str(user["user_id"]),
        "username": str(user["username"]),
        "role": role,
        "permissions": sorted(permissions_for_role(role)),
        "must_change_password": bool(user.get("must_change_password", False)),
    }


def _auth_context(user: dict[str, Any], *, session_id: str = "") -> dict[str, Any]:
    public = _public_user(user)
    return {
        "sub": public["id"],
        "username": public["username"],
        "role": public["role"],
        "permissions": public["permissions"],
        "must_change_password": public["must_change_password"],
        "session_id": session_id,
        "auth_revision": int(user.get("auth_revision", 0)),
    }


def require_auth(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> Dict[str, Any]:
    """所有业务 API 共用的认证依赖；RBAC 模式实时核验用户与会话。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要登录后访问")
    token_data = decode_access_token(authorization[7:].strip())
    if Config.AUTH_MODE == "local":
        role = str(token_data.get("role") or "operator")
        auth = {
            "sub": str(token_data["sub"]),
            "username": str(token_data["username"]),
            "role": role,
            "permissions": sorted(permissions_for_role(role)),
            "must_change_password": False,
            "session_id": "",
            "auth_revision": int(token_data.get("ver") or 0),
        }
        return _authorize_authenticated_request(request, auth)

    if Config.AUTH_MODE != "rbac":
        raise HTTPException(status_code=503, detail="认证服务未完成安全配置")
    user_id = str(token_data["sub"])
    session_id = str(token_data.get("sid") or "")
    repository = AuthRepository()
    user = repository.get_user_by_id(user_id)
    session = repository.get_active_session(session_id) if session_id else None
    if (
        not user
        or not user["is_active"]
        or not session
        or session["user_id"] != user_id
        or int(token_data.get("ver") or 0) != int(user["auth_revision"])
    ):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    auth = _auth_context(user, session_id=session_id)
    return _authorize_authenticated_request(request, auth)


def _authorize_authenticated_request(request: Request, auth: Dict[str, Any]) -> Dict[str, Any]:
    """认证后再按方法和路径做白名单授权，未登记的接口默认拒绝。"""
    permission = permission_for_request(request.method, request.url.path)
    request.state.auth = auth
    request.state.required_permission = permission or "unmapped"
    password_change_paths = {
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/auth/change-password",
        "/api/v1/users/me/permissions",
    }
    if auth.get("must_change_password") and request.url.path.rstrip("/") not in password_change_paths:
        request.state.permission_denied = True
        raise HTTPException(status_code=403, detail="首次登录后请先修改密码")
    if not permission or not has_permission(str(auth["role"]), permission):
        request.state.permission_denied = True
        raise HTTPException(status_code=403, detail="当前账号没有执行此操作的权限")
    return auth


def require_permission(permission: str) -> Callable[..., Dict[str, Any]]:
    """生成逐接口权限依赖；权限不足统一返回 403 并供审计记录。"""
    def dependency(request: Request, auth: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
        request.state.required_permission = permission
        if permission not in auth.get("permissions", ()):
            request.state.permission_denied = True
            raise HTTPException(status_code=403, detail="当前账号没有执行此操作的权限")
        return auth

    return dependency


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginUser(BaseModel):
    id: str
    username: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    must_change_password: bool = False


class LoginResponse(BaseModel):
    token: str
    user: LoginUser


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=14, max_length=256)


def _client_metadata(request: Request) -> tuple[str, str]:
    return (
        (request.client.host if request.client else "")[:64],
        (request.headers.get("user-agent") or "")[:512],
    )


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=Config.AUTH_COOKIE_NAME,
        value=raw_token,
        max_age=Config.AUTH_REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=Config.AUTH_COOKIE_SECURE,
        samesite=Config.AUTH_COOKIE_SAMESITE,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=Config.AUTH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=Config.AUTH_COOKIE_SECURE,
        samesite=Config.AUTH_COOKIE_SAMESITE,
    )


def _issue_rbac_session(user: dict[str, Any], request: Request, response: Response) -> LoginResponse:
    raw_refresh_token = secrets.token_urlsafe(48)
    client_ip, user_agent = _client_metadata(request)
    session = AuthRepository().create_refresh_session(
        user_id=str(user["user_id"]),
        refresh_token_digest=_refresh_digest(raw_refresh_token),
        expires_at=_utcnow() + timedelta(seconds=Config.AUTH_REFRESH_TOKEN_TTL_SECONDS),
        client_ip=client_ip,
        user_agent=user_agent,
    )
    _set_refresh_cookie(response, raw_refresh_token)
    return LoginResponse(
        token=create_access_token(
            str(user["username"]),
            str(user["role"]),
            user_id=str(user["user_id"]),
            session_id=str(session["session_id"]),
            auth_revision=int(user["auth_revision"]),
        ),
        user=LoginUser(**_public_user(user)),
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """创建 Access + HttpOnly 刷新会话；不接受或记录明文凭据之外的任何认证信息。"""
    username = payload.username.strip()
    if Config.AUTH_MODE == "local":
        if not username or not payload.password:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        request.state.auth = {
            "sub": username,
            "username": username,
            "role": "operator",
            "permissions": sorted(permissions_for_role("operator")),
        }
        return LoginResponse(
            token=create_access_token(username),
            user=LoginUser(
                id=username,
                username=username,
                role="operator",
                permissions=sorted(permissions_for_role("operator")),
            ),
        )

    if Config.AUTH_MODE != "rbac":
        raise HTTPException(status_code=503, detail="认证服务未完成安全配置")
    request.state.auth = {"sub": f"login:{username[:48]}", "username": username[:64], "role": ""}
    repository = AuthRepository()
    user = repository.get_user_by_username(username, include_hash=True)
    now = _utcnow()
    if (
        not user
        or not user["is_active"]
        or (user.get("locked_until") and datetime.fromisoformat(str(user["locked_until"])) > now)
        or not verify_password(str(user.get("password_hash") or ""), payload.password)
    ):
        if user and user["is_active"] and not (
            user.get("locked_until") and datetime.fromisoformat(str(user["locked_until"])) > now
        ):
            repository.record_login_failure(
                str(user["user_id"]),
                max_failures=Config.AUTH_MAX_LOGIN_FAILURES,
                lock_seconds=Config.AUTH_LOCK_SECONDS,
            )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    refreshed_hash = hash_password(payload.password) if needs_rehash(str(user["password_hash"])) else None
    user = repository.record_login_success(str(user["user_id"]), rehash=refreshed_hash)
    request.state.auth = _auth_context(user)
    return _issue_rbac_session(user, request, response)


@router.post("/refresh", response_model=LoginResponse)
def refresh_access_token(request: Request, response: Response) -> LoginResponse:
    """轮换 HttpOnly 刷新令牌，返回新的短期 Access Token。"""
    if Config.AUTH_MODE != "rbac":
        raise HTTPException(status_code=409, detail="本地模式不需要刷新会话")
    raw_previous = request.cookies.get(Config.AUTH_COOKIE_NAME)
    if not raw_previous:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    raw_next = secrets.token_urlsafe(48)
    client_ip, user_agent = _client_metadata(request)
    rotated = AuthRepository().rotate_refresh_session(
        previous_digest=_refresh_digest(raw_previous),
        next_digest=_refresh_digest(raw_next),
        next_expires_at=_utcnow() + timedelta(seconds=Config.AUTH_REFRESH_TOKEN_TTL_SECONDS),
        client_ip=client_ip,
        user_agent=user_agent,
    )
    if not rotated:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user, session = rotated
    _set_refresh_cookie(response, raw_next)
    request.state.auth = _auth_context(user, session_id=str(session["session_id"]))
    return LoginResponse(
        token=create_access_token(
            str(user["username"]), str(user["role"]),
            user_id=str(user["user_id"]), session_id=str(session["session_id"]),
            auth_revision=int(user["auth_revision"]),
        ),
        user=LoginUser(**_public_user(user)),
    )


@router.get("/me", response_model=LoginUser)
def current_user(auth: Dict[str, Any] = Depends(require_auth)) -> LoginUser:
    return LoginUser(
        id=str(auth["sub"]), username=str(auth["username"]), role=str(auth["role"]),
        permissions=list(auth.get("permissions") or []),
        must_change_password=bool(auth.get("must_change_password")),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    _auth: Dict[str, Any] = Depends(require_auth),
) -> Response:
    raw_refresh = request.cookies.get(Config.AUTH_COOKIE_NAME)
    if Config.AUTH_MODE == "rbac" and raw_refresh:
        AuthRepository().revoke_session_by_digest(_refresh_digest(raw_refresh), "logout")
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    auth: Dict[str, Any] = Depends(require_auth),
) -> Response:
    if Config.AUTH_MODE != "rbac":
        raise HTTPException(status_code=409, detail="本地模式不支持修改密码")
    repository = AuthRepository()
    user = repository.get_user_by_id(str(auth["sub"]), include_hash=True)
    if not user or not verify_password(str(user.get("password_hash") or ""), payload.current_password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    try:
        validate_password_strength(payload.new_password, str(user["username"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repository.set_password(
        str(user["user_id"]), hash_password(payload.new_password), must_change_password=False
    )
    _clear_refresh_cookie(response)
    request.state.auth = {**auth, "password_changed": True}
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
