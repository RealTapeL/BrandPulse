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


TABLE_SPECS: Dict[str, TableSpec] = {
    "dp_shop_metrics": TableSpec(
        fields=("shop_name", "city", "crawl_date", "score", "review_count", "avg_price", "business_area", "place"),
        searchable_fields=("shop_name", "city", "business_area", "place"),
        default_order="crawl_date DESC, shop_name ASC",
    ),
    "xhs_notes": TableSpec(
        fields=("title", "author_name", "likes", "publish_time", "city", "mall_name", "crawl_date"),
        searchable_fields=("title", "author_name", "city", "mall_name"),
        default_order="crawl_date DESC, likes DESC NULLS LAST",
    ),
    "brand_indicators_daily": TableSpec(
        fields=("stat_date", "entity_name", "city", "mall_name", "weighted_score", "heat_index", "sov", "wow_momentum", "volatility"),
        searchable_fields=("entity_name", "city", "mall_name"),
        default_order="stat_date DESC, heat_index DESC NULLS LAST",
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
):
    spec = TABLE_SPECS.get(table_name)
    if not spec:
        raise HTTPException(status_code=404, detail="不支持的数据表")

    where = ""
    params = {"limit": size, "offset": (page - 1) * size}
    if keyword.strip():
        where = " WHERE " + " OR ".join(f"CAST({field} AS TEXT) ILIKE :keyword" for field in spec.searchable_fields)
        params["keyword"] = f"%{keyword.strip()}%"

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
