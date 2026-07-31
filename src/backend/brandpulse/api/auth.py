"""单团队部署的登录接口。

项目当前不提供用户管理和细粒度权限；local 模式仅建立前端会话，password 模式由
环境变量提供单个运营账号，避免把凭据写入代码库。
"""
import secrets
from hmac import compare_digest

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from brandpulse.config.config import Config

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
def login(payload: LoginRequest) -> LoginResponse:
    """创建浏览器会话；生产环境应使用 password 模式或接入统一认证。"""
    if not _credentials_are_valid(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return LoginResponse(
        token=secrets.token_urlsafe(32),
        user=LoginUser(id=payload.username, username=payload.username, role="operator"),
    )
