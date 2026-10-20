"""统一分析中心 API。"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from brandpulse.analysis.service import AnalysisService

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.get("/metrics")
def list_analysis_metrics():
    """返回统一指标字典；不附带任何模拟指标值。"""
    return {"items": AnalysisService().metric_catalog()}


@router.get("")
def query_analysis(
    scope_id: str = Query(..., min_length=1, max_length=64),
    view: Literal["overview", "comparison", "trend", "evidence"] = "overview",
    snapshot_id: Optional[str] = Query(default=None, max_length=64),
    metric_key: str = Query(default="dp_review_count_stock", max_length=128),
    brand_ids: Optional[str] = Query(default=None, max_length=512),
    source_name: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(default=30, ge=2, le=100),
):
    try:
        return AnalysisService().query(
            scope_id=scope_id,
            view=view,
            snapshot_id=snapshot_id,
            metric_key=metric_key,
            brand_ids=brand_ids,
            source_name=source_name,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
