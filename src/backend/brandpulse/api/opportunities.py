"""快照绑定的招商机会信号 API。"""

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from brandpulse.api.auth import require_auth
from brandpulse.opportunities.service import OpportunityService
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


class OpportunityLifecycleUpdate(BaseModel):
    lifecycle_status: Literal[
        "discovered", "master_confirmed", "profile_incomplete", "under_review", "qualified",
        "outreach", "negotiation", "introduced", "rejected", "archived",
    ]
    owner_id: Optional[str] = Field(default=None, max_length=64)
    human_comment: str = Field(default="", max_length=2000)
    human_confirmed: Optional[bool] = None


@router.get("")
def list_opportunities(
    scope_id: str = Query(..., min_length=1, max_length=64),
    snapshot_id: Optional[str] = Query(default=None, max_length=64),
    signal_class: Optional[Literal["opportunity", "risk", "data_quality", "information"]] = None,
    lifecycle_status: Optional[str] = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
) -> Dict[str, Any]:
    if not TrustedScopeRepository().get(scope_id):
        raise HTTPException(status_code=404, detail="监测范围不存在")
    try:
        return OpportunityService().list(
            scope_id=scope_id,
            snapshot_id=snapshot_id,
            signal_class=signal_class,
            lifecycle_status=lifecycle_status,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/snapshots/{snapshot_id}/generate")
def generate_opportunities(snapshot_id: str) -> Dict[str, Any]:
    try:
        return OpportunityService().generate(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{signal_id}")
def update_opportunity(
    signal_id: str,
    payload: OpportunityLifecycleUpdate,
    _auth: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        row = OpportunityService().update_lifecycle(signal_id=signal_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="机会信号不存在")
    return row
