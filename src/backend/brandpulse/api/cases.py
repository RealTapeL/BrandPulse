"""业务事项 API：来源证据、负责人、处理日志和告警有效性反馈。"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from brandpulse.api.auth import require_auth
from brandpulse.cases.service import BusinessCaseService

router = APIRouter(prefix="/api/v1/cases", tags=["business-cases"])


class CaseCreate(BaseModel):
    case_type: Literal["data_quality", "collection_exception", "brand_risk", "operations_risk", "opportunity", "manual"]
    source_type: Literal["alert_history", "opportunity_signal", "data_quality_issue", "collection_run", "source_run", "report_publication", "brand", "store", "manual"] = "manual"
    source_id: str = Field(default="manual", min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=8000)
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    scope_id: Optional[str] = Field(default=None, max_length=64)
    owner_id: Optional[str] = Field(default=None, max_length=64)
    due_at: Optional[datetime] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    external_links: list[str] = Field(default_factory=list, max_length=50)


class CaseFromSource(BaseModel):
    source_type: Literal["alert_history", "opportunity_signal", "data_quality_issue", "collection_run", "source_run", "report_publication"]
    source_id: str = Field(..., min_length=1, max_length=128)
    priority: Optional[Literal["critical", "high", "normal", "low"]] = None
    owner_id: Optional[str] = Field(default=None, max_length=64)
    due_at: Optional[datetime] = None


class CaseUpdate(BaseModel):
    status: Optional[Literal["open", "acknowledged", "investigating", "action_planned", "in_progress", "resolved", "closed"]] = None
    owner_id: Optional[str] = Field(default=None, max_length=64)
    due_at: Optional[datetime] = None
    outcome: Optional[str] = Field(default=None, max_length=8000)
    feedback: Optional[Literal["pending", "valid", "false_positive", "no_action_required", "data_problem"]] = None
    rule_adjustment_requested: Optional[bool] = None
    note: str = Field(default="", max_length=4000)


def _actor(auth: Dict[str, Any]) -> str:
    return str(auth.get("username") or auth.get("sub") or "unknown")


@router.get("")
def list_cases(scope_id: Optional[str] = None, status: Optional[str] = None, owner_id: Optional[str] = None, limit: int = Query(default=100, ge=1, le=200)):
    try:
        return BusinessCaseService().list(scope_id=scope_id, status=status, owner_id=owner_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/metrics")
def case_metrics():
    return BusinessCaseService().feedback_metrics()


@router.post("")
def create_case(payload: CaseCreate, auth: Dict[str, Any] = Depends(require_auth)):
    try:
        return BusinessCaseService().create(**payload.model_dump(), created_by=_actor(auth))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/from-source")
def create_case_from_source(payload: CaseFromSource, auth: Dict[str, Any] = Depends(require_auth)):
    try:
        return BusinessCaseService().create_from_source(**payload.model_dump(), created_by=_actor(auth))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{case_id}")
def get_case(case_id: str):
    row = BusinessCaseService().get(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="事项不存在")
    return row


@router.put("/{case_id}")
def update_case(case_id: str, payload: CaseUpdate, auth: Dict[str, Any] = Depends(require_auth)):
    try:
        row = BusinessCaseService().update(case_id, actor_id=_actor(auth), **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="事项不存在")
    return row
