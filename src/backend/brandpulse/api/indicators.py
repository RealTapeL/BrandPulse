"""
指标查询 API：GET /api/v1/indicators
符合前端契约：{ series: [{date, value}], meta: {} }
"""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient

router = APIRouter(prefix="/api/v1/indicators", tags=["indicators"])


class IndicatorResponse(BaseModel):
    series: list[dict]
    meta: dict


@router.get("", response_model=IndicatorResponse)
def get_indicators(
    brand_id: str = Query(..., min_length=1, description="品牌或商场×品类数据集 ID"),
    indicator: str = Query(default="heat", description="指标名：reputation/heat/sov"),
    start: Optional[str] = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
):
    """
    查询指标时序。
    brand_id 由调用方明确传入，避免以某个固定商场作为默认数据范围。
    """
    client = PostgresClient()
    sql = """
        SELECT date, value
        FROM indicators
        WHERE brand_id = :brand_id AND indicator = :indicator
    """
    params = {"brand_id": brand_id, "indicator": indicator}
    if start:
        sql += " AND date >= :start"
        params["start"] = start
    if end:
        sql += " AND date <= :end"
        params["end"] = end
    sql += " ORDER BY date ASC"

    with client.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    series = [{"date": str(r["date"]), "value": float(r["value"])} for r in rows]
    return IndicatorResponse(
        series=series,
        meta={"brand_id": brand_id, "indicator": indicator, "count": len(series)},
    )
