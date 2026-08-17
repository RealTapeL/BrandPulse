"""密码哈希与强度校验；绝不保存或记录明文密码。"""
from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)


def validate_password_strength(password: str, username: str = "") -> None:
    """要求至少 14 位且含三类字符，避免弱口令进入用户表。"""
    if len(password) < 14:
        raise ValueError("密码至少需要 14 个字符")
    if len(password) > 256:
        raise ValueError("密码长度不能超过 256 个字符")
    categories = sum((
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^\w\s]", password)),
    ))
    if categories < 3:
        raise ValueError("密码需至少包含大写字母、小写字母、数字、符号中的三类")
    if username and username.casefold() in password.casefold():
        raise ValueError("密码不能包含用户名")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except (VerificationError, VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
