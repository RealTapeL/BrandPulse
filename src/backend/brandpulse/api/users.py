"""管理员用户与角色管理 API。"""
from __future__ import annotations

import secrets
import string
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from brandpulse.api.auth import normalize_username, require_auth, require_permission
from brandpulse.security.passwords import hash_password, validate_password_strength
from brandpulse.security.permissions import ROLE_ADMIN, USER_MANAGE, VALID_ROLES, permissions_for_role
from brandpulse.storage.auth_repository import AuthRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _user_response(user: dict[str, Any]) -> dict[str, Any]:
    role = str(user["role"])
    return {
        "id": str(user["user_id"]),
        "username": str(user["username"]),
        "role": role,
        "permissions": sorted(permissions_for_role(role)),
        "is_active": bool(user["is_active"]),
        "must_change_password": bool(user["must_change_password"]),
        "locked_until": user.get("locked_until"),
        "last_login_at": user.get("last_login_at"),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def _generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+="
    # 保证满足三类字符要求，避免随机性导致偶发弱密码。
    return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(20))


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    role: str = Field(default="viewer")
    temporary_password: Optional[str] = Field(default=None, min_length=14, max_length=256)


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    temporary_password: Optional[str] = Field(default=None, min_length=14, max_length=256)


@router.get("")
def list_users(_auth: Dict[str, Any] = Depends(require_permission(USER_MANAGE))):
    return {"items": [_user_response(user) for user in AuthRepository().list_users()]}


@router.post("")
def create_user(payload: UserCreate, auth: Dict[str, Any] = Depends(require_permission(USER_MANAGE))):
    try:
        username = normalize_username(payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="角色必须是 admin、operator 或 viewer")
    repository = AuthRepository()
    if repository.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    temporary_password = payload.temporary_password or _generate_temporary_password()
    try:
        validate_password_strength(temporary_password, username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = repository.create_user(
        username=username,
        password_hash=hash_password(temporary_password),
        role=payload.role,
        created_by=str(auth["sub"]),
        must_change_password=True,
    )
    # 仅本次响应返回一次性密码；审计中间件不保存请求体或响应体。
    return {"user": _user_response(user), "temporary_password": temporary_password}


@router.put("/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    auth: Dict[str, Any] = Depends(require_permission(USER_MANAGE)),
):
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=400, detail="无更新字段")
    if payload.role is not None and payload.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="角色必须是 admin、operator 或 viewer")
    repository = AuthRepository()
    target = repository.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    changing_last_admin = (
        target["role"] == ROLE_ADMIN
        and target["is_active"]
        and ((payload.role is not None and payload.role != ROLE_ADMIN) or payload.is_active is False)
    )
    if changing_last_admin and repository.active_admin_count() <= 1:
        raise HTTPException(status_code=409, detail="不能停用或降级最后一个有效管理员")
    if str(auth["sub"]) == user_id and (
        payload.is_active is False or (payload.role is not None and payload.role != ROLE_ADMIN)
    ):
        raise HTTPException(status_code=409, detail="不能停用或降级当前登录的管理员账号")
    updated = repository.update_user(user_id, role=payload.role, is_active=payload.is_active)
    return _user_response(updated)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    payload: PasswordReset,
    _auth: Dict[str, Any] = Depends(require_permission(USER_MANAGE)),
):
    repository = AuthRepository()
    target = repository.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    temporary_password = payload.temporary_password or _generate_temporary_password()
    try:
        validate_password_strength(temporary_password, str(target["username"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = repository.set_password(user_id, hash_password(temporary_password), must_change_password=True)
    return {"user": _user_response(user), "temporary_password": temporary_password}


@router.get("/me/permissions")
def my_permissions(auth: Dict[str, Any] = Depends(require_auth)):
    """供前端恢复会话后读取当前实时权限。"""
    return {
        "role": auth["role"],
        "permissions": auth.get("permissions") or [],
    }
