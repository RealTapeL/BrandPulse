"""
阶段一：构建品牌竞品关系图谱
"""
from brandpulse.utils.logger.modules.logger import get_logger
from brandpulse.utils.storage.modules.neo4j_repository import Neo4jRepository

logger = get_logger(__name__)


def run():
    """构建瑞幸、库迪、星巴克之间的竞品关系"""
    neo4j_repo = Neo4jRepository()

    relationships = [
        ("LK001", "KD001", 0.95),
        ("KD001", "LK001", 0.95),
        ("LK001", "SB001", 0.70),
        ("SB001", "LK001", 0.70),
        ("KD001", "SB001", 0.55),
        ("SB001", "KD001", 0.55),
    ]

    count = 0
    for b1, b2, conf in relationships:
        if neo4j_repo.create_competitor_relationship(b1, b2, conf):
            count += 1

    logger.info(f"竞品关系图谱构建完成，共 {count} 条关系")
    return count
