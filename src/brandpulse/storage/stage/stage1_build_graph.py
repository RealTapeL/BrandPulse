"""
阶段一：构建品牌竞品关系图谱

数据驱动：从 PostgreSQL brand_relationships 表读取关系，
若 Neo4j 可用则同步写入图库，不可用则仅在 PG 维护。
"""
from brandpulse.logger.modules.logger import get_logger
from brandpulse.storage.modules.neo4j_repository import Neo4jRepository
from brandpulse.storage.modules.pg_repository import RelationshipRepository

logger = get_logger(__name__)


def run(relation_type: str = "竞品"):
    """
    从 PG 读取关系并同步到 Neo4j（如果可用）

    Args:
        relation_type: 要同步的关系类型，默认'竞品'

    Returns:
        int: 成功同步到 Neo4j 的关系数
    """
    rel_repo = RelationshipRepository()
    neo4j_repo = Neo4jRepository()

    relationships = rel_repo.list_relationships(relation_type=relation_type)
    if not relationships:
        logger.warning(f"未找到关系类型为 {relation_type} 的记录")
        return 0

    count = 0
    for rel in relationships:
        if neo4j_repo.create_competitor_relationship(
            rel["brand_id"],
            rel["related_brand_id"],
            float(rel.get("confidence_score", 0.8)),
        ):
            count += 1

    if neo4j_repo.client.available:
        logger.info(f"竞品关系图谱构建完成，共 {count} 条关系")
    else:
        logger.info(f"Neo4j 未启用，已从 PG 读取 {len(relationships)} 条关系，跳过图库同步")

    return count
