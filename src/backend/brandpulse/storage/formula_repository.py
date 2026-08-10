"""自定义公式配置和真实计算结果的 PostgreSQL 仓储。"""
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class FormulaRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["id"] = item.pop("formula_id")
        item["params"] = item.get("params") or []
        return item

    def list(self) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM custom_formulas ORDER BY created_at DESC, formula_id DESC")).mappings().all()
        return [self._row_to_dict(row) for row in rows]

    def get(self, formula_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM custom_formulas WHERE formula_id = :formula_id"),
                {"formula_id": formula_id},
            ).mappings().first()
        return self._row_to_dict(row) if row else None

    def list_enabled(self) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM custom_formulas WHERE enabled = TRUE ORDER BY formula_id")
            ).mappings().all()
        return [self._row_to_dict(row) for row in rows]

    def upsert_values(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        sql = text("""
            INSERT INTO custom_formula_values (formula_id, brand_id, stat_date, value, detail)
            VALUES (:formula_id, :brand_id, :stat_date, :value, CAST(:detail AS jsonb))
            ON CONFLICT (formula_id, brand_id, stat_date) DO UPDATE SET
                value = EXCLUDED.value,
                detail = EXCLUDED.detail,
                updated_at = CURRENT_TIMESTAMP
        """)
        with self.client.engine.begin() as conn:
            conn.execute(sql, [
                {**row, "detail": json.dumps(row.get("detail") or {}, ensure_ascii=False)}
                for row in rows
            ])
        return len(rows)

    def list_values(self, formula_id: str, brand_id: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM custom_formula_values WHERE formula_id = :formula_id"
        params: Dict[str, Any] = {"formula_id": formula_id, "limit": limit}
        if brand_id:
            sql += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        sql += " ORDER BY stat_date DESC, brand_id LIMIT :limit"
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        formula_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                INSERT INTO custom_formulas (
                    formula_id, name, description, expression, params, enabled, remark
                ) VALUES (
                    :formula_id, :name, :description, :expression, CAST(:params AS jsonb), :enabled, :remark
                ) RETURNING *
            """), {**payload, "formula_id": formula_id, "params": json.dumps(payload["params"], ensure_ascii=False)}).mappings().one()
            conn.commit()
        return self._row_to_dict(row)

    def update(self, formula_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                UPDATE custom_formulas
                SET name = :name,
                    description = :description,
                    expression = :expression,
                    params = CAST(:params AS jsonb),
                    enabled = :enabled,
                    remark = :remark,
                    updated_at = CURRENT_TIMESTAMP
                WHERE formula_id = :formula_id
                RETURNING *
            """), {**payload, "formula_id": formula_id, "params": json.dumps(payload["params"], ensure_ascii=False)}).mappings().first()
            conn.commit()
        return self._row_to_dict(row) if row else None

    def delete(self, formula_id: str) -> bool:
        with self.client.engine.connect() as conn:
            deleted = conn.execute(text("DELETE FROM custom_formulas WHERE formula_id = :formula_id"), {"formula_id": formula_id}).rowcount
            conn.commit()
        return bool(deleted)
