"""
BrandPulse PostgreSQL 客户端

全系统唯一的数据库连接入口（单例），上层仓储（storage/）统一从这里取 engine。
"""
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


class PostgresClient:
    """PostgreSQL 客户端（单例，池化连接，自动预检）"""

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
        """执行 SQL 语句（自动提交）"""
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result


def test_connection() -> bool:
    """测试 PostgreSQL 连接是否可用"""
    try:
        PostgresClient().execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"PostgreSQL 连接失败: {e}")
        return False
