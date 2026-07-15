"""
Neo4j 图数据库仓储层
"""
from typing import Dict, List

from brandpulse.utils.db_clients.modules.db_clients import Neo4jClient
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)


class Neo4jRepository:
    """Neo4j 图数据库仓储"""

    def __init__(self):
        self.client = Neo4jClient()

    def create_brand_node(self, brand: Dict) -> bool:
        """创建品牌节点"""
        query = """
        MERGE (b:Brand {brand_id: $brand_id})
        SET b.brand_name_cn = $brand_name_cn,
            b.brand_name_en = $brand_name_en,
            b.tier = $tier,
            b.business_model = $business_model,
            b.avg_price_min = $avg_price_min,
            b.avg_price_max = $avg_price_max,
            b.category = $category
        """

        def to_float(value):
            """将 Decimal 等类型转为 float"""
            if value is None:
                return None
            return float(value)

        try:
            self.client.run(query, {
                "brand_id": brand.get("brand_id"),
                "brand_name_cn": brand.get("brand_name_cn"),
                "brand_name_en": brand.get("brand_name_en"),
                "tier": brand.get("tier"),
                "business_model": brand.get("business_model"),
                "avg_price_min": to_float(brand.get("avg_price_min")),
                "avg_price_max": to_float(brand.get("avg_price_max")),
                "category": brand.get("category_id"),
            })
            return True
        except Exception as e:
            logger.error(f"创建品牌节点 {brand.get('brand_id')} 失败: {e}")
            return False

    def create_store_node(self, store: Dict) -> bool:
        """创建门店节点和关系"""
        query = """
        MERGE (s:Store {store_id: $store_id})
        SET s.store_name = $store_name,
            s.address = $address,
            s.longitude = $longitude,
            s.latitude = $latitude,
            s.store_status = $store_status

        WITH s
        MATCH (b:Brand {brand_id: $brand_id})
        MERGE (b)-[:HAS_STORE]->(s)

        WITH s
        MERGE (c:City {name: $city})
        MERGE (s)-[:LOCATED_IN]->(c)

        WITH s
        FOREACH (mall IN CASE WHEN $mall_name IS NOT NULL AND $mall_name <> '' THEN [$mall_name] ELSE [] END |
            MERGE (m:Mall {name: mall})
            MERGE (s)-[:IN_MALL]->(m)
        )
        """
        try:
            self.client.run(query, {
                "store_id": store.get("store_id"),
                "store_name": store.get("store_name"),
                "address": store.get("address"),
                "longitude": store.get("longitude"),
                "latitude": store.get("latitude"),
                "store_status": store.get("store_status"),
                "brand_id": store.get("brand_id"),
                "city": store.get("city"),
                "mall_name": store.get("mall_name"),
            })
            return True
        except Exception as e:
            logger.error(f"创建门店节点 {store.get('store_id')} 失败: {e}")
            return False

    def create_competitor_relationship(
        self, brand_id1: str, brand_id2: str, confidence: float = 0.8
    ) -> bool:
        """创建竞品关系"""
        query = """
        MATCH (b1:Brand {brand_id: $brand_id1})
        MATCH (b2:Brand {brand_id: $brand_id2})
        MERGE (b1)-[r:COMPETES_WITH]->(b2)
        SET r.confidence = $confidence
        """
        try:
            self.client.run(query, {
                "brand_id1": brand_id1,
                "brand_id2": brand_id2,
                "confidence": confidence,
            })
            return True
        except Exception as e:
            logger.error(f"创建竞品关系 {brand_id1}-{brand_id2} 失败: {e}")
            return False

    def clear_all(self) -> bool:
        """清空所有节点和关系（慎用）"""
        query = "MATCH (n) DETACH DELETE n"
        try:
            self.client.run(query)
            logger.warning("已清空 Neo4j 所有数据")
            return True
        except Exception as e:
            logger.error(f"清空 Neo4j 失败: {e}")
            return False
