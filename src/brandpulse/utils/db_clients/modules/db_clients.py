"""
BrandPulse 数据库客户端
统一封装 PostgreSQL、Neo4j、Qdrant 的连接
"""
from typing import Optional

from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from brandpulse.utils.config.modules.config import Config
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)


class PostgresClient:
    """PostgreSQL 客户端"""

    _instance: Optional["PostgresClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.engine = create_engine(
                Config.postgres_dsn(),
                pool_pre_ping=True,
                echo=False,
            )
            cls._instance.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=cls._instance.engine
            )
        return cls._instance

    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()

    def execute(self, sql: str, params: dict = None):
        """执行 SQL 语句"""
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result


class Neo4jClient:
    """Neo4j 图数据库客户端"""

    _instance: Optional["Neo4jClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
            )
        return cls._instance

    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()

    def run(self, query: str, parameters: dict = None):
        """执行 Cypher 查询"""
        with self.driver.session() as session:
            return session.run(query, parameters or {})

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            logger.error(f"Neo4j 连接失败: {e}")
            return False


class QdrantClientWrapper:
    """Qdrant 向量数据库客户端"""

    _instance: Optional["QdrantClientWrapper"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = QdrantClient(
                host=Config.QDRANT_HOST,
                port=Config.QDRANT_PORT,
            )
        return cls._instance

    def get_client(self) -> QdrantClient:
        """获取原始 Qdrant 客户端"""
        return self.client

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant 连接失败: {e}")
            return False


def test_all_connections():
    """测试所有数据库连接"""
    results = {}

    # PostgreSQL
    try:
        pg = PostgresClient()
        pg.execute("SELECT 1")
        results["postgres"] = "✓ 连接正常"
    except Exception as e:
        results["postgres"] = f"✗ 连接失败: {e}"

    # Neo4j
    neo4j = Neo4jClient()
    results["neo4j"] = "✓ 连接正常" if neo4j.test_connection() else "✗ 连接失败"

    # Qdrant
    qdrant = QdrantClientWrapper()
    results["qdrant"] = "✓ 连接正常" if qdrant.test_connection() else "✗ 连接失败"

    return results
