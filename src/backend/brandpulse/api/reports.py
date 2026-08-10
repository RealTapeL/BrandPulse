"""真实项目/品类报告生成、下载与定时计划 API。"""

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from brandpulse.reporting.queue import ReportEnqueueError, enqueue_report
from brandpulse.reporting.service import ReportDataNotReadyError, report_readiness, require_report_ready
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.report_repository import ReportRunRepository, ReportScheduleRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportCreate(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    file_format: Literal["csv", "xlsx"] = "xlsx"


class ReportScheduleCreate(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    frequency: Literal["daily", "weekly"]
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    file_format: Literal["csv", "xlsx"] = "xlsx"
    enabled: bool = False

    @model_validator(mode="after")
    def validate_weekday(self):
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("周报必须指定 weekday（0=周一，6=周日）")
        if self.frequency == "daily" and self.weekday is not None:
            raise ValueError("日报不能指定 weekday")
        return self


class ReportScheduleUpdate(BaseModel):
    frequency: Optional[Literal["daily", "weekly"]] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    minute: Optional[int] = Field(default=None, ge=0, le=59)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    file_format: Optional[Literal["csv", "xlsx"]] = None
    enabled: Optional[bool] = None


@router.get("/readiness/{scope_id}")
def get_report_readiness(scope_id: str):
    try:
        readiness = report_readiness(scope_id)
    except ReportDataNotReadyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {key: value for key, value in readiness.items() if key != "dashboard"}


@router.post("")
def create_report(payload: ReportCreate):
    if not MonitoringScopeRepository().get(payload.scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    try:
        require_report_ready(payload.scope_id)
    except ReportDataNotReadyError as exc:
        raise HTTPException(status_code=409, detail=f"报告未生成：{exc}") from exc
    repository = ReportRunRepository()
    run = repository.create(scope_id=payload.scope_id, file_format=payload.file_format)
    try:
        run["rq_job_id"] = enqueue_report(run["report_id"])
        repository.set_rq_job(run["report_id"], run["rq_job_id"])
        return run
    except ReportEnqueueError as exc:
        repository.finish_failure(run["report_id"], str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("")
def list_reports(scope_id: Optional[str] = Query(default=None), limit: int = Query(default=50, ge=1, le=100)):
    return {"items": ReportRunRepository().list(scope_id=scope_id, limit=limit)}


@router.get("/{report_id}")
def get_report(report_id: str):
    report = ReportRunRepository().get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.get("/{report_id}/download")
def download_report(report_id: str):
    report = ReportRunRepository().get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report["status"] != "success" or not report.get("file_path"):
        raise HTTPException(status_code=409, detail="报告尚未生成完成")
    path = Path(report["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="报告文件已不存在")
    return FileResponse(
        path,
        media_type="text/csv" if report["file_format"] == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"brandpulse_report_{report_id}.{report['file_format']}",
    )


@router.get("/schedules/list")
def list_report_schedules():
    return {"items": ReportScheduleRepository().list()}


@router.post("/schedules")
def create_report_schedule(payload: ReportScheduleCreate):
    if not MonitoringScopeRepository().get(payload.scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    return ReportScheduleRepository().create(**payload.model_dump())


@router.put("/schedules/{schedule_id}")
def update_report_schedule(schedule_id: str, payload: ReportScheduleUpdate):
    repository = ReportScheduleRepository()
    current = repository.get(schedule_id)
    if not current:
        raise HTTPException(status_code=404, detail="报告计划不存在")
    data = {**current, **payload.model_dump(exclude_unset=True)}
    if data["frequency"] == "weekly" and data.get("weekday") is None:
        raise HTTPException(status_code=422, detail="周报必须指定 weekday")
    if data["frequency"] == "daily" and data.get("weekday") is not None:
        raise HTTPException(status_code=422, detail="日报不能指定 weekday")
    return repository.update(schedule_id, payload.model_dump(exclude_unset=True))


@router.delete("/schedules/{schedule_id}")
def delete_report_schedule(schedule_id: str):
    if not ReportScheduleRepository().delete(schedule_id):
        raise HTTPException(status_code=404, detail="报告计划不存在")
    return {"deleted": True}
