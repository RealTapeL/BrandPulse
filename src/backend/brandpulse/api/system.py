"""系统存活、就绪探针与受保护的生产配置自检。"""

from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from brandpulse.config.config import Config
from brandpulse.db_clients.postgres_client import PostgresClient

router = APIRouter(prefix="/api/v1/system", tags=["system"])
protected_router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health/live")
def liveness():
    """进程能够响应请求即为存活，不依赖外部服务。"""
    return {"status": "ok", "service": "brandpulse-api"}


@router.get("/health/ready")
def readiness():
    """数据库和队列都可用时才接收业务流量。"""
    components = {}
    try:
        with PostgresClient().engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar_one()
        components["postgres"] = {"status": "ok"}
    except Exception as exc:
        components["postgres"] = {"status": "error", "error": type(exc).__name__}

    redis = None
    try:
        redis = Redis.from_url(
            Config.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        redis.ping()
        components["redis"] = {"status": "ok"}
    except Exception as exc:
        components["redis"] = {"status": "error", "error": type(exc).__name__}
    finally:
        if redis is not None:
            redis.close()

    ready = all(item["status"] == "ok" for item in components.values())
    payload = {"status": "ready" if ready else "not_ready", "components": components}
    return JSONResponse(payload, status_code=200 if ready else 503)


@protected_router.get("/configuration")
def configuration_status():
    """只返回配置完备性，不返回账号、密码、主机名或密钥内容。"""
    checks = []

    def add(key: str, label: str, status: str, message: str) -> None:
        checks.append({"key": key, "label": label, "status": status, "message": message})

    add(
        "auth_mode", "登录模式",
        "pass" if Config.AUTH_MODE == "password" else "fail",
        "已启用固定账号密码模式" if Config.AUTH_MODE == "password" else "当前为 local，本地模式接受任意非空账号密码",
    )
    secret_ok = len(Config.AUTH_SECRET) >= 32
    add(
        "auth_secret", "令牌签名密钥",
        "pass" if secret_ok else "fail",
        "已配置长度不少于 32 的持久密钥" if secret_ok else "AUTH_SECRET 缺失或长度不足，服务重启会使登录令牌失效",
    )
    password_ok = bool(Config.AUTH_USERNAME and Config.AUTH_PASSWORD)
    add(
        "auth_account", "固定登录账号",
        "pass" if password_ok else "fail",
        "固定账号已配置" if password_ok else "AUTH_USERNAME / AUTH_PASSWORD 尚未完整配置",
    )
    add(
        "audit", "操作审计",
        "pass" if Config.AUDIT_ENABLED else "fail",
        "操作审计已启用" if Config.AUDIT_ENABLED else "AUDIT_ENABLED=false，变更操作不会留痕",
    )
    smtp_ok = bool(Config.SMTP_HOST and Config.SMTP_FROM)
    add(
        "smtp", "邮件通知",
        "pass" if smtp_ok else "warning",
        "SMTP 基础配置已就绪" if smtp_ok else "SMTP 尚未配置，只能使用 Webhook 或仅记录告警",
    )

    backups = sorted(Config.BACKUP_DIR.glob("brandpulse_*.dump")) if Config.BACKUP_DIR.is_dir() else []
    latest = max(backups, key=lambda path: path.stat().st_mtime) if backups else None
    if latest:
        age_hours = (datetime.now().timestamp() - latest.stat().st_mtime) / 3600
        checksum_ok = latest.with_suffix(latest.suffix + ".sha256").is_file()
        backup_ok = age_hours <= 48 and checksum_ok
        backup_message = f"最近备份 {latest.name}，约 {age_hours:.1f} 小时前"
        if not checksum_ok:
            backup_message += "，缺少 SHA-256 校验文件"
    else:
        backup_ok = False
        backup_message = "尚未发现 PostgreSQL 备份"
    add("backup", "数据库备份", "pass" if backup_ok else "fail", backup_message)

    local_cors = any("localhost" in item or "127.0.0.1" in item for item in Config.CORS_ORIGINS)
    add(
        "cors", "浏览器来源限制",
        "warning" if local_cors else "pass",
        "仍包含本地开发来源，生产部署需改为正式域名" if local_cors else "未发现本地开发来源",
    )
    production_ready = not any(item["status"] == "fail" for item in checks)
    return {"production_ready": production_ready, "checks": checks}
