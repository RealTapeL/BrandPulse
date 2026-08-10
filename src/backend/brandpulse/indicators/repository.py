"""
brand_indicators_daily 指标表仓储
"""
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


class IndicatorRepository:
    """指标表读写（按主键幂等 upsert）"""

    def __init__(self):
        self.client = PostgresClient()

    def upsert_indicators(self, rows: List[Dict]) -> int:
        """
        批量写入指标行，每行至少包含：
        stat_date / city / mall_name / entity_type / entity_name
        以及任意指标字段（weighted_score / heat_index / wow_momentum / volatility / sov / detail）
        """
        import json

        sql = """
        INSERT INTO brand_indicators_daily (
            stat_date, city, mall_name, entity_type, entity_name, brand_id,
            weighted_score, heat_index, wow_momentum, volatility, sov, detail
        ) VALUES (
            :stat_date, :city, :mall_name, :entity_type, :entity_name, :brand_id,
            :weighted_score, :heat_index, :wow_momentum, :volatility, :sov, :detail
        )
        ON CONFLICT (stat_date, city, mall_name, entity_type, entity_name, brand_id) DO UPDATE SET
            brand_id = COALESCE(EXCLUDED.brand_id, brand_indicators_daily.brand_id),
            weighted_score = COALESCE(EXCLUDED.weighted_score, brand_indicators_daily.weighted_score),
            heat_index = COALESCE(EXCLUDED.heat_index, brand_indicators_daily.heat_index),
            wow_momentum = COALESCE(EXCLUDED.wow_momentum, brand_indicators_daily.wow_momentum),
            volatility = COALESCE(EXCLUDED.volatility, brand_indicators_daily.volatility),
            sov = COALESCE(EXCLUDED.sov, brand_indicators_daily.sov),
            detail = COALESCE(brand_indicators_daily.detail, '{}'::jsonb)
                     || COALESCE(EXCLUDED.detail, '{}'::jsonb),
            updated_at = CURRENT_TIMESTAMP
        """
        saved = 0
        # 不同计算步骤产出的行字段不同（口碑行没有 heat_index 等），
        # 统一补齐为 None，避免 SQLAlchemy 缺绑定参数报错
        all_keys = (
            "stat_date", "city", "mall_name", "entity_type", "entity_name", "brand_id",
            "weighted_score", "heat_index", "wow_momentum", "volatility", "sov", "detail",
        )
        for row in rows:
            row = {k: row.get(k) for k in all_keys}
            if not row["brand_id"]:
                logger.warning("跳过缺少 brand_id 的指标行 %s/%s，禁止无归属写入", row["entity_name"], row["stat_date"])
                continue
            detail = row.get("detail")
            # 各指标步骤分开 upsert，同一实体的 detail 必须按 metric 合并，
            # 不能让最后一个步骤覆盖前面已落库的审计信息。
            if isinstance(detail, dict) and detail.get("metric"):
                metric = detail["metric"]
                detail = {metric: {k: v for k, v in detail.items() if k != "metric"}}
            row["detail"] = json.dumps(detail, ensure_ascii=False) if detail is not None else None
            try:
                self.client.execute(sql, row)
                saved += 1
            except Exception as e:
                logger.error(f"写入指标失败 {row.get('entity_name')}/{row.get('stat_date')}: {e}")
        return saved

    def list_indicators(
        self,
        stat_date: Optional[str] = None,
        entity_type: Optional[str] = None,
        city: Optional[str] = None,
    ) -> List[Dict]:
        """查询指标"""
        sql = "SELECT * FROM brand_indicators_daily WHERE 1=1"
        params = {}
        if stat_date:
            sql += " AND stat_date = :stat_date"
            params["stat_date"] = stat_date
        if entity_type:
            sql += " AND entity_type = :entity_type"
            params["entity_type"] = entity_type
        if city:
            sql += " AND city = :city"
            params["city"] = city
        sql += " ORDER BY stat_date DESC, entity_type, heat_index DESC NULLS LAST"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]

    def get_heat_series(
        self,
        entity_type: str,
        entity_name: str,
        city: str,
        mall_name: str,
        limit: int = 8,
    ) -> List[Dict]:
        """取某实体最近 N 期热度序列（动量/波动率计算用），按日期升序"""
        sql = """
        SELECT stat_date, heat_index
        FROM brand_indicators_daily
        WHERE entity_type = :entity_type AND entity_name = :entity_name
          AND city = :city AND mall_name = :mall_name
        ORDER BY stat_date DESC
        LIMIT :limit
        """
        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), {
                "entity_type": entity_type,
                "entity_name": entity_name,
                "city": city,
                "mall_name": mall_name,
                "limit": limit,
            })
            rows = [dict(row) for row in result.mappings().all()]
        return list(reversed(rows))

    def latest_stat_date(self) -> Optional[str]:
        """指标表中最新的 stat_date"""
        with self.client.engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(stat_date) FROM brand_indicators_daily"))
            row = result.first()
            return str(row[0]) if row and row[0] else None
