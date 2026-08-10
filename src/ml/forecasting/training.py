"""门店销售预测训练、时间回测与模型工件保存。"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .datasets import DATASET_SPECS, ensure_dataset, load_dataset, load_store_sales_file
from .features import FEATURE_COLUMNS, feature_matrix, make_supervised_frame
from .predict import recursive_forecast


MODEL_ROOT = Path(__file__).resolve().parents[3] / "models" / "forecasting"
ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


def _progress(
    callback: ProgressCallback | None,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    if callback is None:
        return
    try:
        callback(status, message, details)
    except Exception:
        # 日志写入失败不能中断模型训练本身。
        return


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.08,
        max_iter=180,
        max_leaf_nodes=31,
        min_samples_leaf=30,
        l2_regularization=1.0,
        random_state=42,
    )


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    y_true = actual.to_numpy(dtype="float64")
    y_pred = np.maximum(np.asarray(predicted, dtype="float64"), 0.0)
    errors = y_pred - y_true
    denominator = float(np.abs(y_true).sum())
    return {
        "mae": float(np.abs(errors).mean()),
        "rmse": float(math.sqrt(np.square(errors).mean())),
        "wape": float(np.abs(errors).sum() / denominator) if denominator else 0.0,
        "rmsle": float(
            math.sqrt(np.square(np.log1p(y_pred) - np.log1p(y_true)).mean())
        ),
    }


def train_store_sales(
    *,
    dataset_key: str = "store_sales",
    validation_days: int = 28,
    horizon: int = 14,
    output_dir: str | Path | None = None,
    ensure_public_data: bool = True,
    data_path: str | Path | None = None,
    data_manifest: dict[str, Any] | None = None,
    data_origin: str | None = None,
    production_eligible: bool | None = None,
    model_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """训练一个真实公开基准数据集上的日销量模型。

    训练前按时间切分最后 validation_days 天进行回测，之后才用完整历史重新拟合模型。
    生成的模型明确标记为 public_benchmark，禁止直接作为内部经营决策模型。
    """
    if dataset_key not in DATASET_SPECS and not data_path:
        raise KeyError(f"未知数据集: {dataset_key}")
    if validation_days < 7:
        raise ValueError("validation_days 至少为 7")
    if horizon < 1 or horizon > 90:
        raise ValueError("horizon 必须在 1 到 90 之间")
    started = time.monotonic()
    if data_path:
        _progress(progress_callback, "running", "开始读取上传数据", {"path": str(data_path)})
        frame = load_store_sales_file(data_path)
    else:
        data_manifest = ensure_dataset(dataset_key) if ensure_public_data else data_manifest
        frame = load_dataset(dataset_key)
    _progress(progress_callback, "running", "数据校验完成，开始构造时序特征", {"rows": len(frame)})
    supervised = make_supervised_frame(frame)
    _progress(
        progress_callback,
        "running",
        "时序特征构造完成",
        {"supervised_rows": len(supervised), "features": len(FEATURE_COLUMNS)},
    )
    max_date = frame["date"].max()
    validation_start = max_date - pd.Timedelta(days=validation_days - 1)
    train_frame = supervised[supervised["date"] < validation_start]
    validation_frame = supervised[supervised["date"] >= validation_start]
    if train_frame.empty or validation_frame.empty:
        raise ValueError("时间回测切分后训练集或验证集为空")

    x_train, y_train = feature_matrix(train_frame)
    x_validation, y_validation = feature_matrix(validation_frame)
    validation_model = _new_model()
    _progress(
        progress_callback,
        "running",
        "开始时间回测训练",
        {"train_rows": len(train_frame), "validation_rows": len(validation_frame)},
    )
    validation_model.fit(x_train, y_train)
    validation_pred = validation_model.predict(x_validation)
    metrics = _metrics(y_validation, validation_pred)
    _progress(progress_callback, "running", "时间回测完成", metrics)

    model = _new_model()
    x_all, y_all = feature_matrix(supervised)
    _progress(progress_callback, "running", "开始使用完整历史训练最终模型", {"rows": len(supervised)})
    model.fit(x_all, y_all)
    _progress(progress_callback, "running", "最终模型训练完成")

    resolved_model_id = model_id or f"{dataset_key}-v1"
    artifact_dir = Path(output_dir) if output_dir else MODEL_ROOT / dataset_key / "v1"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.joblib"
    joblib.dump(model, model_path)

    forecast = recursive_forecast(model, frame, horizon=horizon)
    _progress(progress_callback, "running", "未来预测生成完成", {"rows": len(forecast)})
    forecast_path = artifact_dir / "forecast.csv"
    forecast.to_csv(forecast_path, index=False)

    spec = DATASET_SPECS.get(dataset_key, DATASET_SPECS["store_sales"])
    metadata: dict[str, Any] = {
        "model_id": resolved_model_id,
        "task": "store_sales_forecast",
        "dataset_key": dataset_key,
        "dataset_name": (data_manifest or {}).get("dataset_name", spec.name),
        "source_url": (data_manifest or {}).get("source_url", spec.source_url),
        "source_page": (data_manifest or {}).get("source_page", spec.source_page),
        "license_note": (data_manifest or {}).get("license_note", spec.license_note),
        "data_origin": data_origin or spec.data_origin,
        "production_eligible": (
            production_eligible
            if production_eligible is not None
            else spec.production_eligible
        ),
        "target": "sales",
        "frequency": "D",
        "algorithm": "HistGradientBoostingRegressor",
        "features": list(FEATURE_COLUMNS),
        "lags": [1, 7, 14, 28],
        "rolling_windows": [7, 14, 28],
        "validation": {
            "method": "last_contiguous_days",
            "validation_days": validation_days,
            "validation_start": validation_start.date().isoformat(),
            "validation_end": max_date.date().isoformat(),
            "train_rows": int(len(train_frame)),
            "validation_rows": int(len(validation_frame)),
            "metrics": metrics,
        },
        "training": {
            "rows_loaded": int(len(frame)),
            "supervised_rows": int(len(supervised)),
            "stores": int(frame["store"].nunique()),
            "items": int(frame["item"].nunique()),
            "history_start": frame["date"].min().date().isoformat(),
            "history_end": max_date.date().isoformat(),
            "forecast_horizon": horizon,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        },
        "artifacts": {
            "model": str(model_path),
            "forecast": str(forecast_path),
        },
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    if data_manifest is not None:
        metadata["dataset_manifest"] = data_manifest
    (artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (artifact_dir / "feature_columns.json").write_text(
        json.dumps(list(FEATURE_COLUMNS), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata
