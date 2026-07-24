"""
数据库连接测试

验证 PostgreSQL 与 Qdrant 可正常连接；Neo4j 在当前环境可选/未启用。
"""
from brandpulse.db_clients.modules.db_clients import test_all_connections as _test_all_connections


def test_postgres_and_qdrant_connections():
    """测试 PostgreSQL 和 Qdrant 连接正常"""
    results = _test_all_connections()
    assert results.get("postgres") == "✓ 连接正常", f"PostgreSQL 连接失败: {results.get('postgres')}"
    assert results.get("qdrant") == "✓ 连接正常", f"Qdrant 连接失败: {results.get('qdrant')}"
    # Neo4j 在本机环境可选，断言其为成功或失败均可，但不应抛异常
    assert "neo4j" in results
