"""数据治理 API：质量扫描、问题处理、品牌别名、门店匹配和采集血缘。"""
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from brandpulse.data_governance.service import DataGovernanceService

router = APIRouter(prefix="/api/v1/data-governance", tags=["data-governance"])


class IssueUpdate(BaseModel):
    status: Literal["open", "acknowledged", "resolved", "ignored"]
    resolution_note: str = Field(default="", max_length=1000)


class BrandAliasCreate(BaseModel):
    brand_id: str = Field(..., min_length=1, max_length=32)
    alias_text: str = Field(..., min_length=1, max_length=255)
    source_name: str = Field(default="manual", min_length=1, max_length=128)
    status: Literal["confirmed", "pending", "rejected"] = "confirmed"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    note: str = Field(default="", max_length=1000)


class StoreAliasUpdate(BaseModel):
    store_id: Optional[str] = Field(default=None, max_length=64)
    status: Literal["confirmed", "pending", "rejected"]
    note: str = Field(default="", max_length=1000)


@router.get("/summary")
def governance_summary() -> Dict[str, Any]:
    return DataGovernanceService().repo.summary()


@router.post("/scan")
def run_quality_scan() -> Dict[str, Any]:
    try:
        return DataGovernanceService().scan(trigger_type="api")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"数据质量扫描失败: {exc}") from exc


@router.get("/issues")
def list_quality_issues(
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    return DataGovernanceService().repo.list_issues(
        status=status, severity=severity, limit=size, offset=(page - 1) * size
    )


@router.put("/issues/{issue_id}")
def update_quality_issue(issue_id: str, payload: IssueUpdate) -> Dict[str, Any]:
    row = DataGovernanceService().repo.update_issue(issue_id, payload.status, payload.resolution_note)
    if not row:
        raise HTTPException(status_code=404, detail="质量问题不存在")
    return row


@router.get("/brand-aliases")
def list_brand_aliases(
    brand_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    return {"items": DataGovernanceService().repo.list_brand_aliases(brand_id=brand_id, status=status)}


@router.post("/brand-aliases")
def create_brand_alias(payload: BrandAliasCreate) -> Dict[str, Any]:
    service = DataGovernanceService()
    try:
        with service.client.engine.connect() as conn:
            if not conn.execute(text("SELECT 1 FROM brands WHERE brand_id = :brand_id"), {"brand_id": payload.brand_id}).first():
                raise HTTPException(status_code=404, detail="品牌不存在")
        return service.repo.create_brand_alias(payload.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"品牌别名保存失败: {exc}") from exc


@router.get("/store-aliases")
def list_store_aliases(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    return DataGovernanceService().repo.list_store_aliases(
        status=status, limit=size, offset=(page - 1) * size
    )


@router.get("/store-options")
def store_options(
    q: Optional[str] = Query(default=None, max_length=128),
    city: Optional[str] = Query(default=None, max_length=64),
    size: int = Query(default=200, ge=1, le=500),
) -> Dict[str, Any]:
    return {"items": DataGovernanceService().repo.list_store_options(q=q, city=city, limit=size)}


@router.put("/store-aliases/{alias_id}")
def update_store_alias(alias_id: str, payload: StoreAliasUpdate) -> Dict[str, Any]:
    service = DataGovernanceService()
    try:
        row = service.repo.update_store_alias(
            alias_id, store_id=payload.store_id, status=payload.status, note=payload.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="门店别名不存在")
    return row


@router.get("/lineage")
def list_lineage(
    source_name: Optional[str] = Query(default=None, max_length=128),
    size: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    return {"items": DataGovernanceService().repo.lineage(source_name=source_name, limit=size)}


@router.get("/lineage/records")
def list_raw_lineage(
    source_name: Optional[str] = Query(default=None, max_length=128),
    crawl_job_id: Optional[str] = Query(default=None, max_length=36),
    run_id: Optional[str] = Query(default=None, max_length=64),
    size: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    return {"items": DataGovernanceService().repo.raw_lineage(
        source_name=source_name,
        crawl_job_id=crawl_job_id,
        run_id=run_id,
        limit=size,
    )}
