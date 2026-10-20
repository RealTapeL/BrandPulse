"""机器学习预测 API：数据输入、训练、日志和预测文件导出。"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from brandpulse.api.auth import require_auth
from brandpulse.config.config import Config
from brandpulse.ml_forecasting.admission import (
    EXTERNAL_REVIEW_TARGET,
    ForecastReadinessService,
)
from brandpulse.ml_forecasting.benchmark import (
    download_public_dataset,
    public_dataset_summary,
)
from brandpulse.ml_forecasting.queue import (
    MLExportEnqueueError,
    MLTrainingEnqueueError,
    enqueue_export,
    enqueue_training,
)
from brandpulse.storage.ml_forecasting_repository import (
    MLDatasetRepository,
    MLExportRepository,
    MLOperationLogRepository,
    MLTrainingRepository,
)
from brandpulse.storage.model_registry_repository import ModelRegistryRepository

router = APIRouter(prefix="/api/v1/ml", tags=["machine-learning"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class TrainingRequest(BaseModel):
    dataset_key: str = Field(default="store_sales", min_length=1, max_length=128)
    validation_days: int = Field(default=28, ge=7, le=180)
    horizon: int = Field(default=14, ge=1, le=90)
    scope_id: Optional[str] = Field(default=None, max_length=64)
    target_metric: str = Field(default=EXTERNAL_REVIEW_TARGET, max_length=128)
    entity_type: str = Field(default="scope", pattern="^(scope|brand|store)$")


class ExportRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=128)
    file_format: str = Field(default="csv", pattern="^(csv|xlsx)$")
    run_id: Optional[str] = Field(default=None, max_length=64)


def _dataset_module():
    from ml.forecasting.datasets import DATASET_SPECS, dataset_status

    return DATASET_SPECS, dataset_status


def _find_model_dir(model_id: str) -> Path:
    try:
        from ml.forecasting.artifacts import find_model_dir

        return find_model_dir(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="模型不存在") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_upload_frame(file: UploadFile, raw: bytes) -> pd.DataFrame:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(io.BytesIO(raw))
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(raw), encoding="gb18030")
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(io.BytesIO(raw))
    raise HTTPException(status_code=415, detail="只支持 .csv、.xlsx、.xlsm 文件")


def _uploaded_dataset_response(record: dict[str, Any]) -> dict[str, Any]:
    validation = record.get("validation") or {}
    return {
        **record,
        "key": record["upload_id"],
        "name": record["original_filename"],
        "description": "用户上传的真实销售时序数据，已与内部经营表隔离。",
        "downloaded": bool(record.get("stored_path")),
        "source_url": "",
        "source_page": "",
        "license_note": "用户上传数据；请确认公司内部授权和使用范围。",
        "data_origin": record.get("data_origin", "user_upload"),
        "production_eligible": bool(record.get("production_eligible", False)),
        "validation": validation,
    }


@router.get("/datasets")
def list_datasets() -> list[dict[str, Any]]:
    specs, status_loader = _dataset_module()
    public_items = [status_loader(key) for key in specs]
    uploads = [_uploaded_dataset_response(item) for item in MLDatasetRepository().list()]
    return public_items + uploads


@router.post("/datasets/{dataset_key}/download")
def download_dataset(dataset_key: str):
    """下载并校验登记过的公开数据集；不接收任意 URL。"""
    specs, _ = _dataset_module()
    if dataset_key not in specs:
        raise HTTPException(status_code=404, detail="公开数据集不存在")
    logs = MLOperationLogRepository()
    logs.append(
        operation_type="data_download",
        status="running",
        message="开始下载公开数据集并校验来源",
        details={"dataset_key": dataset_key, "source_url": specs[dataset_key].source_url},
    )
    try:
        result = download_public_dataset(dataset_key)
    except Exception as exc:
        logs.append(
            operation_type="data_download",
            status="failed",
            level="error",
            message="公开数据集下载或校验失败",
            details={"dataset_key": dataset_key, "error": str(exc)},
        )
        raise HTTPException(status_code=502, detail=f"公开数据集下载或校验失败: {exc}") from exc
    logs.append(
        operation_type="data_download",
        status="success",
        message="公开数据集下载并校验通过",
        details={
            "dataset_key": dataset_key,
            "sha256": result.get("sha256"),
            "validation": result.get("validation") or {},
            "production_eligible": False,
        },
    )
    return result


@router.get("/datasets/{dataset_key}/summary")
def get_dataset_summary(
    dataset_key: str,
    daily_limit: int = Query(default=30, ge=1, le=90),
    ranking_limit: int = Query(default=10, ge=1, le=50),
):
    """查看已下载公开数据集的真实摘要与来源边界。"""
    try:
        return public_dataset_summary(
            dataset_key,
            daily_limit=daily_limit,
            ranking_limit=ranking_limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"公开数据摘要读取失败: {exc}") from exc


@router.post("/datasets/upload")
def upload_dataset(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xlsm"}:
        raise HTTPException(status_code=415, detail="只支持 .csv、.xlsx、.xlsm 文件")
    upload_id = str(uuid4())
    repository = MLDatasetRepository()
    log_repository = MLOperationLogRepository()
    repository.create(
        upload_id=upload_id,
        dataset_key=upload_id,
        original_filename=filename,
        file_format=suffix.removeprefix("."),
    )
    log_repository.append(
        operation_type="data_upload",
        status="running",
        upload_id=upload_id,
        message="开始接收并校验上传数据",
        details={"filename": filename, "file_format": suffix.removeprefix(".")},
    )
    try:
        raw = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError("上传文件超过 100 MB 限制")
        frame = _read_upload_frame(file, raw)
        from ml.forecasting.datasets import canonicalize_store_sales_frame

        canonical, validation = canonicalize_store_sales_frame(frame)
        target_dir = Config.RAW_DIR / "ml" / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_path = target_dir / f"{upload_id}.csv"
        canonical.to_csv(stored_path, index=False)
        manifest = {
            "upload_id": upload_id,
            "dataset_key": upload_id,
            "dataset_name": filename,
            "original_filename": filename,
            "source_sha256": _sha256(raw),
            "stored_path": str(stored_path),
            "data_origin": "user_upload",
            "production_eligible": False,
            "validation": validation,
        }
        stored_path.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record = repository.mark_valid(
            upload_id,
            stored_path=str(stored_path),
            sha256=manifest["source_sha256"],
            validation=validation,
        )
        log_repository.append(
            operation_type="data_upload",
            status="success",
            upload_id=upload_id,
            message="数据上传并校验通过",
            details=validation,
        )
        return _uploaded_dataset_response(record)
    except HTTPException:
        repository.mark_failed(upload_id, "上传文件格式不支持")
        log_repository.append(
            operation_type="data_upload",
            status="failed",
            level="error",
            upload_id=upload_id,
            message="数据上传失败：文件格式不支持",
        )
        raise
    except Exception as exc:
        repository.mark_failed(upload_id, str(exc))
        log_repository.append(
            operation_type="data_upload",
            status="failed",
            level="error",
            upload_id=upload_id,
            message="数据上传或校验失败",
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=422, detail=f"数据上传或校验失败: {exc}") from exc


@router.post("/forecasting/train")
def start_training(payload: TrainingRequest):
    specs, _ = _dataset_module()
    external_review = payload.dataset_key == "trusted_dianping_reviews"
    readiness = None
    if external_review:
        if not payload.scope_id:
            raise HTTPException(status_code=422, detail="点评增量预测必须指定 scope_id")
        try:
            readiness = ForecastReadinessService().check(
                scope_id=payload.scope_id,
                target_metric=payload.target_metric,
                entity_type=payload.entity_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if readiness["status"] != "ready":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "forecast_not_ready",
                    "message": "真实快照尚未满足预测训练准入条件，系统不会创建训练任务。",
                    "readiness": readiness,
                },
            )
    upload = None
    if payload.dataset_key not in specs and not external_review:
        upload = MLDatasetRepository().get(payload.dataset_key)
        if not upload or upload["status"] != "valid":
            raise HTTPException(status_code=404, detail="数据集不存在或尚未校验通过")
    data_origin = "trusted_snapshot" if external_review else (upload["data_origin"] if upload else specs[payload.dataset_key].data_origin)
    production_eligible = bool(upload["production_eligible"]) if upload else False
    task = "dianping_review_increment_forecast" if external_review else "store_sales_forecast"
    repository = MLTrainingRepository()
    log_repository = MLOperationLogRepository()
    run = repository.create(
        payload.dataset_key,
        {
            "validation_days": payload.validation_days,
            "horizon": payload.horizon,
            "scope_id": payload.scope_id,
            "target_metric": payload.target_metric,
            "entity_type": payload.entity_type,
            "readiness": readiness,
        },
        task=task,
        data_origin=data_origin,
        production_eligible=production_eligible,
        dataset_upload_id=upload["upload_id"] if upload else None,
    )
    log_repository.append(
        operation_type="training",
        status="pending",
        run_id=run["run_id"],
        upload_id=upload["upload_id"] if upload else None,
        message="训练任务已创建，等待进入 RQ 队列",
        details={"dataset_key": payload.dataset_key},
    )
    try:
        rq_job_id = enqueue_training(run["run_id"])
        repository.set_rq_job(run["run_id"], rq_job_id)
        log_repository.append(
            operation_type="training",
            status="pending",
            run_id=run["run_id"],
            message="训练任务已进入 brandpulse-ml 队列",
            details={"rq_job_id": rq_job_id},
        )
    except Exception as exc:
        if not isinstance(exc, MLTrainingEnqueueError):
            exc = MLTrainingEnqueueError(f"训练任务入队后状态写回失败: {exc}")
        repository.finish_failure(run["run_id"], str(exc))
        log_repository.append(
            operation_type="training",
            status="failed",
            level="error",
            run_id=run["run_id"],
            message="训练任务入队失败",
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run["rq_job_id"] = rq_job_id
    run["status"] = "pending"
    return run


@router.get("/forecasting/readiness")
def forecast_readiness(
    scope_id: str = Query(..., min_length=1, max_length=64),
    target_metric: str = Query(default=EXTERNAL_REVIEW_TARGET, min_length=1, max_length=128),
    entity_type: str = Query(default="scope", pattern="^(scope|brand|store)$"),
):
    try:
        return ForecastReadinessService().check(
            scope_id=scope_id,
            target_metric=target_metric,
            entity_type=entity_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/models")
def list_registered_models(
    scope_id: Optional[str] = Query(default=None, max_length=64),
    status: Optional[str] = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
):
    return {"items": ModelRegistryRepository().list(scope_id=scope_id, status=status, limit=limit)}


@router.get("/models/{model_version_id}")
def get_registered_model(model_version_id: str):
    model = ModelRegistryRepository().get(model_version_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    return model


@router.get("/models/{model_version_id}/monitoring")
def monitor_registered_model(model_version_id: str):
    try:
        return ModelRegistryRepository().monitoring(model_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/models/{model_version_id}/publish")
def publish_registered_model(model_version_id: str, auth: dict = Depends(require_auth)):
    # 认证和 ML 权限由 app 的受保护路由及路径权限白名单执行；actor 仅用于审计台账。
    actor_id = str((auth or {}).get("sub") or (auth or {}).get("username") or "unknown")
    try:
        return ModelRegistryRepository().publish(model_version_id, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/models/{model_version_id}/retire")
def retire_registered_model(model_version_id: str, auth: dict = Depends(require_auth)):
    actor_id = str((auth or {}).get("sub") or (auth or {}).get("username") or "unknown")
    try:
        return ModelRegistryRepository().retire(model_version_id, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/forecasting/predictions")
def list_forecast_predictions(
    scope_id: str = Query(..., min_length=1, max_length=64),
    target_metric: str = Query(default=EXTERNAL_REVIEW_TARGET, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
):
    with ModelRegistryRepository().client.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT * FROM forecast_results
                WHERE scope_id = :scope_id AND target_metric = :target_metric
                ORDER BY forecast_date ASC
                LIMIT :limit
                """
            ),
            {"scope_id": scope_id, "target_metric": target_metric, "limit": limit},
        ).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/forecasting/runs")
def list_training_runs(
    status: Optional[str] = Query(default=None, pattern="^(pending|running|success|failed)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    return MLTrainingRepository().list(status=status, limit=size, offset=(page - 1) * size)


@router.get("/forecasting/runs/{run_id}")
def get_training_run(run_id: str):
    run = MLTrainingRepository().get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="机器学习训练运行不存在")
    return run


@router.post("/forecasting/exports")
def start_export(payload: ExportRequest):
    _find_model_dir(payload.model_id)
    repository = MLExportRepository()
    log_repository = MLOperationLogRepository()
    export = repository.create(
        model_id=payload.model_id,
        file_format=payload.file_format,
        run_id=payload.run_id,
    )
    log_repository.append(
        operation_type="forecast_export",
        status="pending",
        export_id=export["export_id"],
        run_id=payload.run_id,
        message="预测导出任务已创建",
        details={"model_id": payload.model_id, "file_format": payload.file_format},
    )
    try:
        rq_job_id = enqueue_export(export["export_id"])
        repository.set_rq_job(export["export_id"], rq_job_id)
    except Exception as exc:
        if not isinstance(exc, MLExportEnqueueError):
            exc = MLExportEnqueueError(f"预测导出入队后状态写回失败: {exc}")
        repository.finish_failure(export["export_id"], str(exc))
        log_repository.append(
            operation_type="forecast_export",
            status="failed",
            level="error",
            export_id=export["export_id"],
            run_id=payload.run_id,
            message="预测导出入队失败",
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    export["rq_job_id"] = rq_job_id
    export["status"] = "pending"
    return export


@router.get("/forecasting/exports")
def list_exports(limit: int = Query(default=50, ge=1, le=100)):
    return {"items": MLExportRepository().list(limit)}


@router.get("/forecasting/exports/{export_id}")
def get_export(export_id: str):
    export = MLExportRepository().get(export_id)
    if not export:
        raise HTTPException(status_code=404, detail="预测导出任务不存在")
    return export


@router.get("/forecasting/exports/{export_id}/download")
def download_export(export_id: str):
    export = MLExportRepository().get(export_id)
    if not export:
        raise HTTPException(status_code=404, detail="预测导出任务不存在")
    if export["status"] != "success" or not export.get("file_path"):
        raise HTTPException(status_code=409, detail="预测文件尚未导出完成")
    path = Path(export["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="预测文件已不存在")
    return FileResponse(
        path,
        media_type=(
            "text/csv"
            if export["file_format"] == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=f"brandpulse_forecast_{export_id}.{export['file_format']}",
    )


@router.get("/logs")
def list_ml_logs(
    operation_type: Optional[str] = Query(default=None, pattern="^(data_download|data_upload|training|forecast_export)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    return MLOperationLogRepository().list(
        operation_type=operation_type,
        limit=size,
        offset=(page - 1) * size,
    )


@router.get("/forecasting/models/{model_id}")
def get_model_metadata(model_id: str):
    metadata_path = _find_model_dir(model_id) / "metadata.json"
    return json.loads(metadata_path.read_text(encoding="utf-8"))


@router.get("/forecasting/models/{model_id}/forecast")
def get_model_forecast(
    model_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
):
    forecast_path = _find_model_dir(model_id) / "forecast.csv"
    if not forecast_path.exists():
        raise HTTPException(status_code=404, detail="模型预测结果不存在")
    frame = pd.read_csv(forecast_path).head(limit)
    return {"model_id": model_id, "rows": frame.to_dict(orient="records")}
