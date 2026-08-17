"""品牌主数据与品牌维度采集记录 API。"""
import ast
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from brandpulse.collectors.jobs import CrawlJobEnqueueError, create_crawl_job
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.api.dashboard import to_jsonable
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

router = APIRouter(prefix="/api/v1/brands", tags=["brands"])

_INDICATOR_COLUMNS = {
    "reputation": ("bayesian_reputation", "贝叶斯加权口碑"),
    "review_share": ("dianping_review_share", "点评评价份额"),
}


class BrandCrawlRequest(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    # 以下旧字段保留兼容；提供时必须与 scope 完全一致，避免重新定义采集范围。
    mall: Optional[str] = Field(default=None, max_length=128)
    category: Optional[str] = Field(default=None, max_length=64)
    cities: list[str] = Field(default_factory=list)


def _presentation_status(status: Optional[str]) -> str:
    return {"pending": "crawling", "running": "crawling", "failed": "error"}.get(status, "active")


def _decode_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return {}
    return data if isinstance(data, dict) else {}


def _serialize_brand(row: Dict[str, Any]) -> Dict[str, Any]:
    last_crawl_at = row.get("finished_at") or row.get("created_at")
    return {
        "id": row["brand_id"],
        "name": row["brand_name_cn"],
        "logo_url": row.get("logo_url") or "",
        "category": row.get("category") or row.get("category_id") or "未分类",
        "city": row.get("cities") or "-",
        "last_crawl_at": str(last_crawl_at) if last_crawl_at else None,
        "status": _presentation_status(row.get("crawl_status")),
    }


def _brand_base_sql() -> str:
    return """
        FROM brands AS brand
        LEFT JOIN category_dict AS category ON category.category_id = brand.category_id
        LEFT JOIN LATERAL (
            SELECT string_agg(DISTINCT store.city, '、' ORDER BY store.city) AS cities
            FROM stores AS store
            WHERE store.brand_id = brand.brand_id AND store.city IS NOT NULL AND store.city <> ''
        ) AS store_cities ON TRUE
        LEFT JOIN LATERAL (
            SELECT status, created_at, finished_at
            FROM crawl_jobs
            WHERE brand_id = brand.brand_id
            ORDER BY created_at DESC
            LIMIT 1
        ) AS latest_job ON TRUE
        WHERE (:q IS NULL OR brand.brand_name_cn ILIKE :q OR COALESCE(brand.brand_name_en, '') ILIKE :q)
          AND (:category IS NULL OR category.category_l3 = :category OR brand.category_id = :category)
          AND (:city IS NULL OR EXISTS (
              SELECT 1 FROM stores AS filter_store
              WHERE filter_store.brand_id = brand.brand_id AND filter_store.city = :city
          ))
    """


@router.get("")
def list_brands(
    q: Optional[str] = Query(default=None, max_length=128),
    category: Optional[str] = Query(default=None, max_length=64),
    city: Optional[str] = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
):
    """分页返回品牌主数据；不把商场级采集批次伪装成品牌。"""
    params = {
        "q": f"%{q.strip()}%" if q and q.strip() else None,
        "category": category or None,
        "city": city or None,
        "limit": per_page,
        "offset": (page - 1) * per_page,
    }
    client = PostgresClient()
    with client.engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) {_brand_base_sql()}"), params).scalar_one()
        rows = conn.execute(text(f"""
            SELECT brand.brand_id, brand.brand_name_cn, brand.logo_url, brand.category_id,
                   category.category_l3 AS category, store_cities.cities,
                   latest_job.status AS crawl_status, latest_job.created_at, latest_job.finished_at
            {_brand_base_sql()}
            ORDER BY brand.brand_name_cn, brand.brand_id
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"items": [_serialize_brand(dict(row)) for row in rows], "total": total}


@router.get("/filters")
def brand_filters():
    """返回真实主数据中的筛选项，前端不再内置城市和品类。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        categories = conn.execute(text("""
            SELECT DISTINCT COALESCE(NULLIF(category.category_l3, ''), brand.category_id) AS value
            FROM brands AS brand
            LEFT JOIN category_dict AS category ON category.category_id = brand.category_id
            WHERE COALESCE(NULLIF(category.category_l3, ''), brand.category_id) IS NOT NULL
            ORDER BY value
        """)).scalars().all()
        cities = conn.execute(text("""
            SELECT DISTINCT city FROM stores
            WHERE city IS NOT NULL AND city <> ''
            ORDER BY city
        """)).scalars().all()
    return {"categories": categories, "cities": cities}


@router.get("/{brand_id}/indicator-series")
def get_brand_indicator_series(
    brand_id: str,
    scope_id: str = Query(..., min_length=1, max_length=64),
    indicator: str = Query(default="reputation", pattern="^(reputation|review_share)$"),
    limit: int = Query(default=30, ge=1, le=180),
):
    """返回范围绑定且已确认映射的品牌指标序列；不回退旧热度/SOV 日表。"""
    metric_key, label = _INDICATOR_COLUMNS[indicator]
    if not TrustedScopeRepository().get(scope_id):
        raise HTTPException(status_code=404, detail="监测范围不存在")
    client = PostgresClient()
    with client.engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM brands WHERE brand_id = :brand_id"), {"brand_id": brand_id}
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="品牌不存在")
        rows = conn.execute(
            text(
                f"""
                SELECT snapshot.observed_at::date AS date, AVG(metric.value) AS value
                FROM metric_observations AS metric
                JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = metric.snapshot_id
                WHERE metric.brand_id = :brand_id
                  AND metric.scope_id = :scope_id
                  AND metric.metric_key = :metric_key
                  AND metric.quality_status = 'valid'
                  AND metric.value IS NOT NULL
                  AND snapshot.status IN ('ready', 'published')
                GROUP BY snapshot.snapshot_id, snapshot.observed_at
                ORDER BY snapshot.observed_at DESC
                LIMIT :limit
                """
            ),
            {"brand_id": brand_id, "scope_id": scope_id, "metric_key": metric_key, "limit": limit},
        ).mappings().all()
    series = list(reversed(to_jsonable([dict(row) for row in rows])))
    return {"brand_id": brand_id, "indicator": indicator, "label": label, "series": series}


@router.get("/{brand_id}")
def get_brand(brand_id: str):
    client = PostgresClient()
    with client.engine.connect() as conn:
        row = conn.execute(text("""
            SELECT brand.brand_id, brand.brand_name_cn, brand.logo_url, brand.category_id,
                   category.category_l3 AS category, store_cities.cities,
                   latest_job.status AS crawl_status, latest_job.created_at, latest_job.finished_at
            FROM brands AS brand
            LEFT JOIN category_dict AS category ON category.category_id = brand.category_id
            LEFT JOIN LATERAL (
                SELECT string_agg(DISTINCT store.city, '、' ORDER BY store.city) AS cities
                FROM stores AS store
                WHERE store.brand_id = brand.brand_id AND store.city IS NOT NULL AND store.city <> ''
            ) AS store_cities ON TRUE
            LEFT JOIN LATERAL (
                SELECT status, created_at, finished_at FROM crawl_jobs
                WHERE brand_id = brand.brand_id ORDER BY created_at DESC LIMIT 1
            ) AS latest_job ON TRUE
            WHERE brand.brand_id = :brand_id
        """), {"brand_id": brand_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="品牌不存在")
        crawl_rows = conn.execute(text("""
            SELECT job_id, mall, category, status, result, created_at, finished_at
            FROM crawl_jobs WHERE brand_id = :brand_id
            ORDER BY created_at DESC LIMIT 20
        """), {"brand_id": brand_id}).mappings().all()

    crawls = []
    for crawl in crawl_rows:
        item = dict(crawl)
        result = _decode_result(item.pop("result"))
        crawls.append({
            "job_id": item["job_id"],
            "mall": item["mall"],
            "category": item["category"],
            "status": "success" if item["status"] == "completed" else item["status"],
            "raw_saved": result.get("raw", result.get("raw_saved", 0)),
            "started_at": str(item["created_at"]) if item["created_at"] else None,
            "finished_at": str(item["finished_at"]) if item["finished_at"] else None,
        })
    return {
        "brand": _serialize_brand(dict(row)),
        "stats": {
            "indicators": [],
            "data_boundary": "品牌详情不读取旧热度/SOV日表；请在选定可信范围内查看已确认映射的公开观测。",
        },
        "recent_crawls": crawls,
    }


@router.post("/{brand_id}/crawl")
def start_brand_crawl(brand_id: str, payload: BrandCrawlRequest):
    """按已登记 scope 发起品牌候选采集；采集结果仍需人工确认实体映射。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM brands WHERE brand_id = :brand_id"), {"brand_id": brand_id}).first()
    if not exists:
        raise HTTPException(status_code=404, detail="品牌不存在")
    scope = TrustedScopeRepository().get(payload.scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="监测范围不存在")
    if payload.mall and payload.mall.strip() != scope["mall_name"]:
        raise HTTPException(status_code=422, detail="mall 必须与 scope 对应的商场一致")
    if payload.category and payload.category.strip() != scope["category"]:
        raise HTTPException(status_code=422, detail="category 必须与 scope 对应的品类一致")
    cities = [city.strip() for city in payload.cities if city.strip()]
    if cities and cities != [scope["city"]]:
        raise HTTPException(status_code=422, detail="cities 必须与 scope 对应的城市一致")
    try:
        return create_crawl_job(
            brand_id=brand_id,
            mall=scope["mall_name"],
            category=scope["category"],
            cities=[scope["city"]],
            scope_id=scope["scope_id"],
        )
    except CrawlJobEnqueueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
