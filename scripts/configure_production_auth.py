#!/usr/bin/env python3
"""安全启用 BrandPulse 数据库账号、会话与三角色 RBAC。"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "backend"))

from sqlalchemy import text

from brandpulse.api.auth import normalize_username
from brandpulse.config.config import Config
from brandpulse.security.passwords import hash_password, validate_password_strength
from brandpulse.storage.auth_repository import AuthRepository


def _replace_env_value(env_path: Path, key: str, value: str) -> None:
    """仅更新一个 KEY，保留 .env 的其他行、注释和所有业务密钥。"""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{key}="
    replacement = f"{prefix}{value}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+="
    # 前缀确保达到强度规则，其余部分提供足够随机熵。
    return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(24))


def _write_initial_password(username: str, password: str) -> Path:
    secret_dir = PROJECT_ROOT / ".secrets"
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(secret_dir, 0o700)
    password_path = secret_dir / "brandpulse_initial_admin_password.txt"
    password_path.write_text(
        f"username={username}\npassword={password}\n"
        "首次登录后必须立即修改密码；交付后请安全删除本文件。\n",
        encoding="utf-8",
    )
    os.chmod(password_path, 0o600)
    return password_path


def main() -> int:
    parser = argparse.ArgumentParser(description="启用 BrandPulse 生产级 RBAC 登录")
    parser.add_argument("--username", default="brandpulse_admin", help="初始管理员用户名（3-64 位）")
    parser.add_argument(
        "--local-http",
        action="store_true",
        help="仅用于本机 HTTP 调试：写入 AUTH_COOKIE_SECURE=false；正式 HTTPS 部署不要使用。",
    )
    args = parser.parse_args()

    try:
        username = normalize_username(args.username)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        # 以随机强密码验证用户名，复用服务端密码规范。
        validate_password_strength(_generate_password(), username)
    except ValueError as exc:
        parser.error(str(exc))

    if Config.APP_ENV == "production" and args.local_http:
        parser.error("APP_ENV=production 时不能使用 --local-http")
    try:
        with AuthRepository().client.engine.connect() as conn:
            if conn.execute(text("SELECT to_regclass('public.auth_users')")).scalar_one() is None:
                raise RuntimeError("认证表不存在，请先运行 bash scripts/apply_migrations.sh")
    except Exception as exc:
        print(f"认证初始化失败：{exc}", file=sys.stderr)
        return 1

    env_path = PROJECT_ROOT / ".env"
    existing_secret = os.getenv("AUTH_SECRET", "")
    auth_secret = existing_secret if len(existing_secret) >= 64 else secrets.token_urlsafe(72)
    _replace_env_value(env_path, "AUTH_MODE", "rbac")
    _replace_env_value(env_path, "AUTH_SECRET", auth_secret)
    _replace_env_value(env_path, "AUTH_COOKIE_SECURE", "false" if args.local_http else "true")
    _replace_env_value(env_path, "AUTH_COOKIE_SAMESITE", "strict")

    repository = AuthRepository()
    if repository.active_admin_count() > 0:
        print("RBAC 已启用；检测到有效管理员账号，未重置任何密码。")
        return 0

    password = _generate_password()
    user = repository.create_user(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        created_by=None,
        must_change_password=True,
    )
    password_path = _write_initial_password(str(user["username"]), password)
    print("RBAC 已启用，并已创建初始管理员。")
    print(f"初始密码仅写入本机受限文件：{password_path}")
    print("请通过 HTTPS 重启服务；管理员首次登录后必须修改密码。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
