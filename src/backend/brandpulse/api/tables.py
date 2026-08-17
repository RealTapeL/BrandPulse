"""受限的数据表浏览 API：白名单字段、服务端筛选、排序与分页。"""
from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from brandpulse.api.dashboard import to_jsonable
from brandpulse.db_clients.postgres_client import PostgresClient

router = APIRouter(prefix="/api/v1/tables", tags=["tables"])


@dataclass(frozen=True)
class TableSpec:
    fields: Tuple[str, ...]
    searchable_fields: Tuple[str, ...]
    default_order: str
    requires_scope: bool = False


TABLE_SPECS: Dict[str, TableSpec] = {
    "raw_observations": TableSpec(
        fields=("source_name", "record_type", "observed_date", "source_record_key", "entity_mapping_status", "category_mapping_status", "quality_status", "source_url"),
        searchable_fields=("source_name", "record_type", "source_record_key", "source_url"),
        default_order="observed_date DESC, source_name ASC, source_record_key ASC",
        requires_scope=True,
    ),
    "metric_observations": TableSpec(
        fields=("snapshot_id", "metric_key", "entity_type", "entity_key", "value", "unit", "quality_status", "metric_version", "calculated_at"),
        searchable_fields=("snapshot_id", "metric_key", "entity_type", "entity_key", "quality_status"),
        default_order="calculated_at DESC, metric_key ASC",
        requires_scope=True,
    ),
    "store_operations": TableSpec(
        fields=("op_id", "brand_id", "store_id", "record_date", "sales_amount", "order_count", "customer_price", "customer_flow", "rent", "store_area", "rent_to_sales_ratio", "sales_per_sqm", "contract_end", "data_source"),
        searchable_fields=("brand_id", "store_id", "data_source"),
        default_order="record_date DESC, store_id ASC",
    ),
}


@router.get("/{table_name}")
def browse_table(
    table_name: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default="", max_length=128),
    sort_prop: str = Query(default="", max_length=64),
    sort_order: str = Query(default="", pattern="^(|ascending|descending)$"),
    scope_id: str = Query(default="", max_length=64),
):
    spec = TABLE_SPECS.get(table_name)
    if not spec:
        raise HTTPException(status_code=404, detail="不支持的数据表")

    conditions = []
    params = {"limit": size, "offset": (page - 1) * size}
    if spec.requires_scope:
        if not scope_id.strip():
            raise HTTPException(status_code=422, detail="该数据表必须选择可信监测范围")
        conditions.append("scope_id = :scope_id")
        params["scope_id"] = scope_id.strip()
    if keyword.strip():
        conditions.append("(" + " OR ".join(f"CAST({field} AS TEXT) ILIKE :keyword" for field in spec.searchable_fields) + ")")
        params["keyword"] = f"%{keyword.strip()}%"
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    if sort_prop in spec.fields and sort_order:
        order = f"{sort_prop} {'ASC' if sort_order == 'ascending' else 'DESC'} NULLS LAST"
    else:
        order = spec.default_order
    fields = ", ".join(spec.fields)
    client = PostgresClient()
    with client.engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}{where}"), params).scalar_one()
        rows = conn.execute(text(f"""
            SELECT {fields} FROM {table_name}{where}
            ORDER BY {order} LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"total": total, "rows": to_jsonable([dict(row) for row in rows])}
