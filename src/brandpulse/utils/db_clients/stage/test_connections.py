"""
阶段：测试数据库连接
"""
from brandpulse.utils.db_clients.modules.db_clients import test_all_connections
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)


def run():
    """执行数据库连接测试"""
    logger.info("测试数据库连接...")
    results = test_all_connections()
    for name, status in results.items():
        print(f"{name}: {status}")
    return results
