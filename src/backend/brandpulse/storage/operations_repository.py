"""门店经营数据仓储。"""
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
