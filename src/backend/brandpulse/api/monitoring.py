"""监测范围与自动采集计划 API。"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from brandpulse.collectors.jobs import CrawlJobEnqueueError, create_crawl_job
from brandpulse.storage.monitoring_repository import CrawlScheduleRepository, MonitoringScopeRepository
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


class CrawlScheduleCreate(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    # interval_minutes 保留兼容旧客户端；新页面以固定的上海时间执行。
    interval_minutes: int = Field(default=1440, ge=30, le=10080)
    run_hour: int = Field(default=9, ge=0, le=23)
    run_minute: int = Field(default=0, ge=0, le=59)
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    enabled: bool = False
    max_attempts: int = Field(default=3, ge=1, le=5)


class MonitoringScopeCreate(BaseModel):
    city: str = Field(..., min_length=1, max_length=64)
    mall_name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=64)
    legacy_dataset_key: Optional[str] = Field(default=None, max_length=128)


class CrawlScheduleUpdate(BaseModel):
    interval_minutes: Optional[int] = Field(default=None, ge=30, le=10080)
    run_hour: Optional[int] = Field(default=None, ge=0, le=23)
    run_minute: Optional[int] = Field(default=None, ge=0, le=59)
    timezone: Optional[Literal["Asia/Shanghai"]] = None
    enabled: Optional[bool] = None
    max_attempts: Optional[int] = Field(default=None, ge=1, le=5)


@router.get("/scopes")
def list_scopes(active_only: bool = True):
    return {"items": MonitoringScopeRepository().list(active_only=active_only)}


@router.post("/scopes")
def create_scope(payload: MonitoringScopeCreate):
    """登记真实 城市×商场×品类 范围；数据集键只用于历史兼容。"""
    try:
        return TrustedScopeRepository().register(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/scopes/{scope_id}/source-requirements")
def get_scope_source_requirements(scope_id: str):
    if not TrustedScopeRepository().get(scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    return {"items": TrustedScopeRepository().source_requirements(scope_id)}


@router.get("/crawl-schedules")
def list_crawl_schedules():
    return {"items": CrawlScheduleRepository().list()}


@router.post("/crawl-schedules")
def create_crawl_schedule(payload: CrawlScheduleCreate):
    if not MonitoringScopeRepository().get(payload.scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    return CrawlScheduleRepository().create(**payload.model_dump())


@router.put("/crawl-schedules/{schedule_id}")
def update_crawl_schedule(schedule_id: str, payload: CrawlScheduleUpdate):
    row = CrawlScheduleRepository().update(schedule_id, payload.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(status_code=404, detail="自动采集计划不存在")
    return row


@router.delete("/crawl-schedules/{schedule_id}")
def delete_crawl_schedule(schedule_id: str):
    if not CrawlScheduleRepository().delete(schedule_id):
        raise HTTPException(status_code=404, detail="自动采集计划不存在")
    return {"deleted": True}


@router.post("/crawl-schedules/{schedule_id}/run-now")
def run_crawl_schedule_now(schedule_id: str):
    schedule = next(
        (item for item in CrawlScheduleRepository().list() if item["schedule_id"] == schedule_id),
        None,
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="自动采集计划不存在")
    try:
        return create_crawl_job(
            brand_id=schedule["brand_id"],
            mall=schedule["mall_name"],
            category=schedule["category"],
            cities=[schedule["city"]],
            scope_id=schedule["scope_id"],
            schedule_id=schedule["schedule_id"],
            trigger_type="manual",
            max_attempts=int(schedule["max_attempts"]),
        )
    except CrawlJobEnqueueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
