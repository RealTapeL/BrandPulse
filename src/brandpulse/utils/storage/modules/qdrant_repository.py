"""
Qdrant 向量数据库仓储层
"""
from typing import Dict, List, Optional

from qdrant_client.http import models

from brandpulse.utils.db_clients.modules.db_clients import QdrantClientWrapper
from brandpulse.utils.logger.modules.logger import get_logger

logger = get_logger(__name__)

DEFAULT_COLLECTION = "brand_knowledge"
DEFAULT_VECTOR_SIZE = 1536


class QdrantRepository:
    """Qdrant 向量数据库仓储"""

    def __init__(self, collection_name: Optional[str] = None):
        self.client = QdrantClientWrapper().get_client()
        self.collection_name = collection_name or DEFAULT_COLLECTION

    def create_collection(
        self,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        distance: str = "Cosine",
    ) -> bool:
        """创建集合"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if exists:
                logger.info(f"集合 {self.collection_name} 已存在")
                return True

            distance_map = {
                "Cosine": models.Distance.COSINE,
                "Euclidean": models.Distance.EUCLID,
                "Dot": models.Distance.DOT,
            }

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=distance_map.get(distance, models.Distance.COSINE),
                ),
            )
            logger.info(f"集合 {self.collection_name} 创建成功")
            return True
        except Exception as e:
            logger.error(f"创建集合 {self.collection_name} 失败: {e}")
            return False

    def add_text_chunks(
        self,
        chunks: List[Dict],
        embeddings: List[List[float]],
    ) -> bool:
        """批量添加文本片段和向量"""
        if len(chunks) != len(embeddings):
            logger.error("chunks 和 embeddings 数量不一致")
            return False

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            points.append(
                models.PointStruct(
                    id=chunk.get("chunk_id"),
                    vector=embedding,
                    payload={
                        "entity_type": chunk.get("entity_type"),
                        "entity_id": chunk.get("entity_id"),
                        "chunk_type": chunk.get("chunk_type"),
                        "title": chunk.get("title"),
                        "content": chunk.get("content"),
                        "source_url": chunk.get("source_url"),
                        "source_date": chunk.get("source_date"),
                        "keywords": chunk.get("keywords"),
                    },
                )
            )

        try:
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"成功添加 {len(points)} 个文本片段")
            return True
        except Exception as e:
            logger.error(f"添加文本片段失败: {e}")
            return False

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """向量相似度搜索"""
        try:
            search_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        )
                    )
                search_filter = models.Filter(must=conditions)

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                with_payload=True,
            )

            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    def delete_collection(self) -> bool:
        """删除集合"""
        try:
            self.client.delete_collection(self.collection_name)
            logger.warning(f"已删除集合 {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            return False
