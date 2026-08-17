"""真实项目/品类报告生成、下载与定时计划 API。"""

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from brandpulse.reporting.queue import ReportEnqueueError, enqueue_report
from brandpulse.reporting.delivery import process_due_report_deliveries
from brandpulse.reporting.service import ReportDataNotReadyError, report_readiness, require_report_ready
from brandpulse.api.auth import require_auth
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.report_repository import ReportPublicationRepository, ReportRunRepository, ReportScheduleRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportCreate(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    file_format: Literal["csv", "xlsx"] = "xlsx"
    snapshot_id: Optional[str] = Field(default=None, max_length=64)
    template_id: Literal["trusted_snapshot_brief"] = "trusted_snapshot_brief"
    audience: list[str] = Field(default_factory=list, max_length=100)
    notification_channel: Literal["download", "smtp", "webhook"] = "download"


class ReportApproval(BaseModel):
    note: str = Field(default="", max_length=2000)


class ReportScheduleCreate(BaseModel):
    scope_id: str = Field(..., min_length=1, max_length=64)
    frequency: Literal["daily", "weekly"]
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    file_format: Literal["csv", "xlsx"] = "xlsx"
    enabled: bool = False
    template_id: Literal["trusted_snapshot_brief"] = "trusted_snapshot_brief"
    audience: list[str] = Field(default_factory=list, max_length=100)
    notification_channel: Literal["download", "smtp", "webhook"] = "download"
    require_approval: bool = True

    @model_validator(mode="after")
    def validate_weekday(self):
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("周报必须指定 weekday（0=周一，6=周日）")
        if self.frequency == "daily" and self.weekday is not None:
            raise ValueError("日报不能指定 weekday")
        if self.notification_channel != "download" and not self.audience:
            raise ValueError("邮件或 Webhook 分发必须指定至少一个接收方")
        return self


class ReportScheduleUpdate(BaseModel):
    frequency: Optional[Literal["daily", "weekly"]] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    minute: Optional[int] = Field(default=None, ge=0, le=59)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    file_format: Optional[Literal["csv", "xlsx"]] = None
    enabled: Optional[bool] = None
    template_id: Optional[Literal["trusted_snapshot_brief"]] = None
    audience: Optional[list[str]] = Field(default=None, max_length=100)
    notification_channel: Optional[Literal["download", "smtp", "webhook"]] = None
    require_approval: Optional[bool] = None


@router.get("/readiness/{scope_id}")
def get_report_readiness(scope_id: str, snapshot_id: Optional[str] = Query(default=None, max_length=64)):
    try:
        readiness = report_readiness(scope_id, snapshot_id)
    except ReportDataNotReadyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {key: value for key, value in readiness.items() if key != "dashboard"}


@router.post("")
def create_report(payload: ReportCreate, auth: Dict[str, Any] = Depends(require_auth)):
    if not MonitoringScopeRepository().get(payload.scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    try:
        readiness = require_report_ready(payload.scope_id, payload.snapshot_id, require_snapshot=True)
    except ReportDataNotReadyError as exc:
        raise HTTPException(status_code=409, detail=f"报告未生成：{exc}") from exc
    repository = ReportRunRepository()
    run = repository.create(
        scope_id=payload.scope_id,
        file_format=payload.file_format,
        snapshot_id=readiness["snapshot_id"],
        template_id=payload.template_id,
        audience=payload.audience,
        notification_channel=payload.notification_channel,
        requested_by=str(auth.get("username") or auth.get("sub") or "unknown"),
    )
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
def download_report(report_id: str, auth: Dict[str, Any] = Depends(require_auth)):
    report = ReportRunRepository().get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report["status"] != "success" or not report.get("file_path"):
        raise HTTPException(status_code=409, detail="报告尚未生成完成")
    path = Path(report["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="报告文件已不存在")
    ReportPublicationRepository().record_download(
        report_id, actor_id=str(auth.get("username") or auth.get("sub") or "unknown"),
    )
    return FileResponse(
        path,
        media_type="text/csv" if report["file_format"] == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"brandpulse_report_{report_id}.{report['file_format']}",
    )


@router.post("/{report_id}/approve")
def approve_report(
    report_id: str,
    payload: ReportApproval,
    auth: Dict[str, Any] = Depends(require_auth),
):
    row = ReportPublicationRepository().approve(
        report_id,
        actor_id=str(auth.get("username") or auth.get("sub") or "unknown"),
        note=payload.note,
    )
    if not row:
        raise HTTPException(status_code=409, detail="报告尚未处于待审核状态")
    return row


@router.get("/{report_id}/deliveries")
def list_report_deliveries(report_id: str, limit: int = Query(default=100, ge=1, le=200)):
    if not ReportRunRepository().get(report_id):
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"items": ReportPublicationRepository().list_delivery_jobs(report_id, limit=limit)}


@router.get("/deliveries/list")
def list_all_report_deliveries(limit: int = Query(default=100, ge=1, le=200)):
    return {"items": ReportPublicationRepository().list_all_delivery_jobs(limit=limit)}


@router.post("/{report_id}/dispatch")
def dispatch_report(report_id: str):
    """仅在用户显式操作且报告审核通过后创建真实投递任务并立即尝试一次。"""
    repository = ReportPublicationRepository()
    try:
        jobs = repository.queue_delivery_jobs(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "jobs": jobs,
        "summary": process_due_report_deliveries(limit=len(jobs)),
    }


@router.post("/{report_id}/retry-deliveries")
def retry_report_deliveries(report_id: str):
    repository = ReportPublicationRepository()
    retried = repository.retry_failed_delivery_jobs(report_id)
    if not retried:
        raise HTTPException(status_code=409, detail="没有可重试的失败分发记录，或报告未处于已审核状态")
    return {
        "retried": retried,
        "summary": process_due_report_deliveries(limit=retried),
    }


@router.get("/schedules/list")
def list_report_schedules():
    return {"items": ReportScheduleRepository().list()}


@router.post("/schedules")
def create_report_schedule(payload: ReportScheduleCreate, auth: Dict[str, Any] = Depends(require_auth)):
    if not MonitoringScopeRepository().get(payload.scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    return ReportScheduleRepository().create(
        **payload.model_dump(),
        updated_by=str(auth.get("username") or auth.get("sub") or "unknown"),
    )


@router.put("/schedules/{schedule_id}")
def update_report_schedule(
    schedule_id: str,
    payload: ReportScheduleUpdate,
    auth: Dict[str, Any] = Depends(require_auth),
):
    repository = ReportScheduleRepository()
    current = repository.get(schedule_id)
    if not current:
        raise HTTPException(status_code=404, detail="报告计划不存在")
    data = {**current, **payload.model_dump(exclude_unset=True)}
    if data["frequency"] == "weekly" and data.get("weekday") is None:
        raise HTTPException(status_code=422, detail="周报必须指定 weekday")
    if data["frequency"] == "daily" and data.get("weekday") is not None:
        raise HTTPException(status_code=422, detail="日报不能指定 weekday")
    changes = payload.model_dump(exclude_unset=True)
    configuration_fields = {"template_id", "audience", "notification_channel", "require_approval"}
    if configuration_fields.intersection(changes):
        configuration = {key: current[key] for key in configuration_fields}
        configuration.update({key: value for key, value in changes.items() if key in configuration_fields})
        if configuration["notification_channel"] != "download" and not configuration["audience"]:
            raise HTTPException(status_code=422, detail="邮件或 Webhook 分发必须指定至少一个接收方")
        repository.upsert_publication_config(
            schedule_id=schedule_id,
            template_id=configuration["template_id"],
            template_version=current.get("template_version") or "v1",
            audience=configuration["audience"] or [],
            notification_channel=configuration["notification_channel"],
            require_approval=bool(configuration["require_approval"]),
            updated_by=str(auth.get("username") or auth.get("sub") or "unknown"),
        )
    return repository.update(schedule_id, changes)


@router.delete("/schedules/{schedule_id}")
def delete_report_schedule(schedule_id: str):
    if not ReportScheduleRepository().delete(schedule_id):
        raise HTTPException(status_code=404, detail="报告计划不存在")
    return {"deleted": True}
