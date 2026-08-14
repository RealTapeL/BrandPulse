"""单团队部署的登录接口。

项目当前不提供用户管理和细粒度权限；local 模式仅建立前端会话，password 模式由
环境变量提供单个运营账号，避免把凭据写入代码库。
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from hmac import compare_digest
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from brandpulse.config.config import Config

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_TOKEN_SECRET = Config.AUTH_SECRET.encode("utf-8") if Config.AUTH_SECRET else secrets.token_bytes(32)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(username: str, role: str = "operator") -> str:
    """创建带过期时间和签名的无状态会话令牌。"""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + Config.AUTH_TOKEN_TTL_SECONDS,
    }, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}".encode("ascii")
    signature = _b64(hmac.new(_TOKEN_SECRET, unsigned, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """验证令牌签名和过期时间，失败时统一抛出 401。"""
    try:
        header, payload, signature = token.split(".")
        unsigned = f"{header}.{payload}".encode("ascii")
        expected = _b64(hmac.new(_TOKEN_SECRET, unsigned, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        data = json.loads(_unb64(payload))
        if not data.get("sub") or int(data.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired token")
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from exc


def require_auth(request: Request, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """所有业务 API 共用的 Bearer 认证依赖。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要 Bearer 登录令牌")
    auth = decode_access_token(authorization[7:].strip())
    request.state.auth = auth
    return auth


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginUser(BaseModel):
    id: str
    username: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: LoginUser


def _credentials_are_valid(username: str, password: str) -> bool:
    if Config.AUTH_MODE == "local":
        return bool(username.strip() and password)
    if Config.AUTH_MODE == "password":
        if not Config.AUTH_USERNAME or not Config.AUTH_PASSWORD:
            raise HTTPException(status_code=503, detail="AUTH_MODE=password 但未配置 AUTH_USERNAME / AUTH_PASSWORD")
        return compare_digest(username, Config.AUTH_USERNAME) and compare_digest(password, Config.AUTH_PASSWORD)
    raise HTTPException(status_code=503, detail=f"不支持的 AUTH_MODE: {Config.AUTH_MODE}")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """创建浏览器会话；生产环境应使用 password 模式或接入统一认证。"""
    if not _credentials_are_valid(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    request.state.auth = {"sub": payload.username, "role": "operator"}
    return LoginResponse(
        token=create_access_token(payload.username),
        user=LoginUser(id=payload.username, username=payload.username, role="operator"),
    )
