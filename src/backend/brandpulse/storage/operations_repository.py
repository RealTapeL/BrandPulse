"""门店经营数据仓储。

这里的聚合只读取已经通过品牌、门店主数据校验的真实经营记录；没有记录时
返回空结果，不用默认值填充业务指标。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class OperationsRepository:
    def __init__(self):
        self.client = PostgresClient()

    def upsert_many(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        sql = text("""
            INSERT INTO store_operations (
                op_id, store_id, brand_id, record_date, sales_amount, order_count,
                customer_price, customer_flow, rent, property_fee, energy_cost,
                store_area, rent_to_sales_ratio, sales_per_sqm, contract_start,
                contract_end, is_in_contract, data_source
            ) VALUES (
                :op_id, :store_id, :brand_id, :record_date, :sales_amount, :order_count,
                :customer_price, :customer_flow, :rent, :property_fee, :energy_cost,
                :store_area, :rent_to_sales_ratio, :sales_per_sqm, :contract_start,
                :contract_end, :is_in_contract, :data_source
            )
            ON CONFLICT (op_id) DO UPDATE SET
                store_id = EXCLUDED.store_id,
                brand_id = EXCLUDED.brand_id,
                record_date = EXCLUDED.record_date,
                sales_amount = EXCLUDED.sales_amount,
                order_count = EXCLUDED.order_count,
                customer_price = EXCLUDED.customer_price,
                customer_flow = EXCLUDED.customer_flow,
                rent = EXCLUDED.rent,
                property_fee = EXCLUDED.property_fee,
                energy_cost = EXCLUDED.energy_cost,
                store_area = EXCLUDED.store_area,
                rent_to_sales_ratio = EXCLUDED.rent_to_sales_ratio,
                sales_per_sqm = EXCLUDED.sales_per_sqm,
                contract_start = EXCLUDED.contract_start,
                contract_end = EXCLUDED.contract_end,
                is_in_contract = EXCLUDED.is_in_contract,
                data_source = EXCLUDED.data_source
        """)
        with self.client.engine.begin() as conn:
            conn.execute(sql, rows)
        return len(rows)

    def list(self, brand_id: Optional[str] = None, store_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM store_operations WHERE 1=1"
        params: Dict[str, Any] = {"limit": limit}
        if brand_id:
            sql += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        if store_id:
            sql += " AND store_id = :store_id"
            params["store_id"] = store_id
        sql += " ORDER BY record_date DESC, store_id LIMIT :limit"
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    def sales_trend(
        self,
        *,
        scope_id: Optional[str] = None,
        brand_id: Optional[str] = None,
        store_id: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """按日聚合真实 POS/经营记录，支持项目、品牌和门店筛选。

        ``scope_id`` 通过 ``stores`` 主数据映射到监测项目；不使用门店名称模糊
        匹配，避免把同名门店或不同项目的销售额混在一起。
        """
        where = ["1 = 1"]
        params: Dict[str, Any] = {}
        if scope_id:
            where.append(
                """EXISTS (
                    SELECT 1
                    FROM scope_store_mappings AS scope_store
                    WHERE scope_store.scope_id = :scope_id
                      AND scope_store.store_id = operation.store_id
                      AND scope_store.mapping_status = 'confirmed'
                )"""
            )
            params["scope_id"] = scope_id
        if brand_id:
            where.append("operation.brand_id = :brand_id")
            params["brand_id"] = brand_id
        if store_id:
            where.append("operation.store_id = :store_id")
            params["store_id"] = store_id
        if start_date:
            where.append("operation.record_date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where.append("operation.record_date <= :end_date")
            params["end_date"] = end_date

        sql = text(f"""
            SELECT
                operation.record_date,
                COUNT(DISTINCT operation.store_id) AS store_count,
                COALESCE(SUM(operation.sales_amount), 0) AS sales_amount,
                COALESCE(SUM(operation.order_count), 0) AS order_count,
                COALESCE(SUM(operation.customer_flow), 0) AS customer_flow,
                CASE
                    WHEN SUM(operation.order_count) > 0
                    THEN SUM(operation.sales_amount) / SUM(operation.order_count)
                END AS customer_price,
                CASE
                    WHEN SUM(operation.store_area) > 0
                    THEN SUM(operation.sales_amount) / SUM(operation.store_area)
                END AS sales_per_sqm
            FROM store_operations AS operation
            JOIN stores AS store
              ON store.store_id = operation.store_id
             AND store.brand_id = operation.brand_id
            WHERE {' AND '.join(where)}
            GROUP BY operation.record_date
            ORDER BY operation.record_date ASC
        """)
        with self.client.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(row) for row in rows]

    def mapping_readiness(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        """返回项目与主数据、经营数据的真实映射准备状态。"""
        params = {"scope_id": scope["scope_id"]}
        with self.client.engine.connect() as conn:
            store_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM scope_store_mappings
                WHERE scope_id = :scope_id AND mapping_status = 'confirmed'
            """), params).scalar_one()
            operation_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM store_operations AS operation
                JOIN scope_store_mappings AS scope_store
                  ON scope_store.store_id = operation.store_id
                 AND scope_store.scope_id = :scope_id
                 AND scope_store.mapping_status = 'confirmed'
            """), params).scalar_one()
            latest_date = conn.execute(text("""
                SELECT MAX(operation.record_date)
                FROM store_operations AS operation
                JOIN scope_store_mappings AS scope_store
                  ON scope_store.store_id = operation.store_id
                 AND scope_store.scope_id = :scope_id
                 AND scope_store.mapping_status = 'confirmed'
            """), params).scalar_one()
        return {
            "scope_id": scope["scope_id"],
            "brand_id": None,
            "city": scope["city"],
            "mall_name": scope["mall_name"],
            "mapped_store_count": int(store_count or 0),
            "operation_record_count": int(operation_count or 0),
            "latest_record_date": str(latest_date) if latest_date else None,
            "ready_for_sales_metric": bool(store_count and operation_count),
            "mapping_rule": "仅统计 scope_store_mappings 中人工确认的真实门店；不会使用旧数据集键推断经营归属。",
        }
