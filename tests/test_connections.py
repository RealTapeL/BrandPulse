"""
数据库连接测试

验证 PostgreSQL 可正常连接（全系统唯一数据库）。
"""
from brandpulse.db_clients.postgres_client import test_connection as _test_connection


def test_postgres_connection():
    """测试 PostgreSQL 连接正常"""
    assert _test_connection() is True, "PostgreSQL 连接失败"
