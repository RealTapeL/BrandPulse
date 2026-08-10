"""RQ 机器学习训练任务。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.storage.ml_forecasting_repository import (
    MLTrainingRepository,
    MLDatasetRepository,
    MLExportRepository,
    MLOperationLogRepository,
)

logger = get_logger(__name__)


def run_training_run(run_id: str) -> dict:
    repository = MLTrainingRepository()
    log_repository = MLOperationLogRepository()
    run = repository.get(run_id)
    if not run:
        raise ValueError(f"机器学习训练运行不存在: {run_id}")
    if not repository.mark_running(run_id):
        return {"run_id": run_id, "status": "already_finished"}
    log_repository.append(
        operation_type="training",
        status="running",
        run_id=run_id,
        message="训练任务开始执行",
        details={"dataset_key": run["dataset_key"]},
    )
    try:
        from ml.forecasting.training import train_store_sales

        parameters = run["parameters"] or {}
        upload = None
        data_path = None
        data_manifest = None
        if run.get("dataset_upload_id"):
            upload = MLDatasetRepository().get(run["dataset_upload_id"])
            if not upload or upload["status"] != "valid" or not upload.get("stored_path"):
                raise ValueError("上传数据集不存在、未校验通过或文件已丢失")
            data_path = upload["stored_path"]
            data_manifest = {
                "dataset_name": upload["original_filename"],
                "source_url": "",
                "source_page": "",
                "license_note": "用户上传数据；请确认公司内部授权和使用范围。",
            }
        model_id = f"{run['dataset_key']}-run-{run_id[:8]}"
        output_dir = (
            Path(Config.PROCESSED_DIR).parent.parent
            / "models"
            / "forecasting"
            / run["dataset_key"]
            / "runs"
            / run_id
        )

        def progress(status: str, message: str, details: dict | None = None) -> None:
            log_repository.append(
                operation_type="training",
                status=status,
                run_id=run_id,
                message=message,
                details=details or {},
            )

        metadata = train_store_sales(
            dataset_key=run["dataset_key"],
            validation_days=int(parameters.get("validation_days", 28)),
            horizon=int(parameters.get("horizon", 14)),
            ensure_public_data=data_path is None,
            data_path=data_path,
            data_manifest=data_manifest,
            data_origin=run["data_origin"],
            production_eligible=run["production_eligible"],
            model_id=model_id,
            output_dir=output_dir,
            progress_callback=progress,
        )
        repository.finish_success(
            run_id,
            artifact_path=str(Path(metadata["artifacts"]["model"]).parent),
            model_id=metadata["model_id"],
            metrics=metadata["validation"]["metrics"],
            train_rows=metadata["validation"]["train_rows"],
            validation_rows=metadata["validation"]["validation_rows"],
        )
        log_repository.append(
            operation_type="training",
            status="success",
            run_id=run_id,
            message="训练任务完成",
            details={
                "model_id": metadata["model_id"],
                "metrics": metadata["validation"]["metrics"],
            },
        )
        return {"run_id": run_id, "status": "success", "model_id": metadata["model_id"]}
    except Exception as exc:
        logger.exception("[ml] 训练失败: run_id=%s", run_id)
        repository.finish_failure(run_id, str(exc))
        log_repository.append(
            operation_type="training",
            status="failed",
            level="error",
            run_id=run_id,
            message="训练任务失败",
            details={"error": str(exc)},
        )
        raise


def run_forecast_export(export_id: str) -> dict:
    repository = MLExportRepository()
    log_repository = MLOperationLogRepository()
    export = repository.get(export_id)
    if not export:
        raise ValueError(f"预测导出不存在: {export_id}")
    if not repository.mark_running(export_id):
        return {"export_id": export_id, "status": "already_finished"}
    log_repository.append(
        operation_type="forecast_export",
        status="running",
        export_id=export_id,
        run_id=export.get("run_id"),
        message="预测文件导出开始执行",
        details={"model_id": export["model_id"], "file_format": export["file_format"]},
    )
    try:
        from ml.forecasting.artifacts import find_model_dir

        model_dir = find_model_dir(export["model_id"])
        source = model_dir / "forecast.csv"
        if not source.exists():
            raise FileNotFoundError(f"模型预测结果不存在: {source}")
        target_dir = Config.PROCESSED_DIR / "ml" / "exports"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{export_id}.{export['file_format']}"
        if export["file_format"] == "csv":
            shutil.copyfile(source, target)
        elif export["file_format"] == "xlsx":
            pd.read_csv(source).to_excel(target, index=False)
        else:
            raise ValueError(f"不支持的导出格式: {export['file_format']}")
        row_count = max(sum(1 for _ in target.open("r", encoding="utf-8")) - 1, 0) if export["file_format"] == "csv" else len(pd.read_excel(target))
        repository.finish_success(export_id, file_path=str(target), row_count=row_count)
        log_repository.append(
            operation_type="forecast_export",
            status="success",
            export_id=export_id,
            run_id=export.get("run_id"),
            message="预测文件导出完成",
            details={"file_path": str(target), "row_count": row_count},
        )
        return {"export_id": export_id, "status": "success", "file_path": str(target)}
    except Exception as exc:
        logger.exception("[ml] 预测导出失败: export_id=%s", export_id)
        repository.finish_failure(export_id, str(exc))
        log_repository.append(
            operation_type="forecast_export",
            status="failed",
            level="error",
            export_id=export_id,
            run_id=export.get("run_id"),
            message="预测文件导出失败",
            details={"error": str(exc)},
        )
        raise
