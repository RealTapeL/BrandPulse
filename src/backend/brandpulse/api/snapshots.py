"""可信数据快照与来源健康度 API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository

router = APIRouter(prefix="/api/v1/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    scope_id: Optional[str] = Query(default=None, max_length=64),
    status: Optional[str] = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=200),
):
    return {"items": SnapshotRepository().list(scope_id=scope_id, status=status, limit=limit)}


@router.get("/source-health/{scope_id}")
def source_health(scope_id: str):
    if not TrustedScopeRepository().get(scope_id):
        raise HTTPException(status_code=404, detail="监测范围不存在")
    return {"scope_id": scope_id, "items": SnapshotRepository().source_health(scope_id)}


@router.get("/{snapshot_id}/history")
def snapshot_history(snapshot_id: str):
    snapshot = SnapshotRepository().get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="数据快照不存在")
    return {
        "snapshot_id": snapshot_id,
        "items": SnapshotRepository().status_history(snapshot_id),
    }


@router.get("/{snapshot_id}")
def get_snapshot(snapshot_id: str):
    snapshot = SnapshotRepository().get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="数据快照不存在")
    return snapshot


@router.post("/{snapshot_id}/publish")
def publish_snapshot(snapshot_id: str):
    try:
        return SnapshotRepository().publish(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
