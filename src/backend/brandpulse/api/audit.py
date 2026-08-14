"""操作审计查询 API。"""

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Query

from brandpulse.storage.audit_repository import AuditRepository

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/events")
def list_audit_events(
    actor_id: Optional[str] = Query(default=None, max_length=64),
    method: Optional[Literal["GET", "POST", "PUT", "PATCH", "DELETE"]] = None,
    outcome: Optional[Literal["success", "failure"]] = None,
    action: Optional[str] = Query(default=None, max_length=128),
    request_id: Optional[str] = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    return AuditRepository().list(
        actor_id=actor_id,
        method=method,
        outcome=outcome,
        action=action,
        request_id=request_id,
        limit=size,
        offset=(page - 1) * size,
    )
