"""基于可信快照的点评新增评价数预测。

输入必须是数据库中的快照序列；模块不补齐缺失周期，也不生成模拟训练样本。
模型只在准入服务确认数据满足门槛后由后台任务调用。
"""

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
from sklearn.linear_model import LinearRegression


TARGET_METRIC = "dp_review_count_delta"
FEATURE_COLUMNS = ("lag_1", "lag_2", "rolling_mean_3", "day_of_week")
ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    truth = actual.to_numpy(dtype="float64")
    estimate = np.maximum(np.asarray(predicted, dtype="float64"), 0.0)
    errors = estimate - truth
    denominator = float(np.abs(truth).sum())
    return {
        "mae": float(np.abs(errors).mean()),
        "rmse": float(math.sqrt(np.square(errors).mean())),
        "wape": float(np.abs(errors).sum() / denominator) if denominator else 0.0,
    }


def make_supervised_frame(series: pd.DataFrame) -> pd.DataFrame:
    required = {"period", "value", "snapshot_id"}
    missing = required - set(series.columns)
    if missing:
        raise ValueError(f"点评增量序列缺少字段: {sorted(missing)}")
    frame = series.loc[:, ["period", "value", "snapshot_id"]].copy()
    frame["period"] = pd.to_datetime(frame["period"], errors="raise").dt.normalize()
    frame["value"] = pd.to_numeric(frame["value"], errors="raise")
    if frame.empty or (frame["value"] < 0).any():
        raise ValueError("点评新增评价序列为空或包含负值")
    frame = frame.sort_values("period", kind="stable").drop_duplicates("period", keep="last")
    frame["lag_1"] = frame["value"].shift(1)
    frame["lag_2"] = frame["value"].shift(2)
    frame["rolling_mean_3"] = frame["value"].shift(1).rolling(3, min_periods=3).mean()
    frame["day_of_week"] = frame["period"].dt.dayofweek.astype("int16")
    result = frame.dropna(subset=[*FEATURE_COLUMNS, "value"]).reset_index(drop=True)
    if result.empty:
        raise ValueError("点评增量可训练样本为空")
    return result


def _progress(callback: ProgressCallback | None, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    if callback:
        try:
            callback(status, message, details)
        except Exception:
            pass


def train_review_increment(
    *,
    series: pd.DataFrame,
    validation_periods: int = 3,
    horizon: int = 7,
    output_dir: str | Path,
    model_id: str,
    scope_id: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if validation_periods < 2:
        raise ValueError("点评预测回测至少需要 2 个验证周期")
    if horizon < 1 or horizon > 30:
        raise ValueError("点评预测 horizon 必须在 1 到 30 之间")
    started = time.monotonic()
    supervised = make_supervised_frame(series)
    if len(supervised) <= validation_periods:
        raise ValueError("点评预测时间回测切分后训练集为空")

    train_frame = supervised.iloc[:-validation_periods].copy()
    validation_frame = supervised.iloc[-validation_periods:].copy()
    model = LinearRegression()
    model.fit(train_frame.loc[:, FEATURE_COLUMNS], train_frame["value"])
    model_pred = np.maximum(model.predict(validation_frame.loc[:, FEATURE_COLUMNS]), 0.0)
    naive_pred = validation_frame["lag_1"].to_numpy(dtype="float64")
    mean_pred = validation_frame["rolling_mean_3"].to_numpy(dtype="float64")
    model_metrics = _metrics(validation_frame["value"], model_pred)
    naive_metrics = _metrics(validation_frame["value"], naive_pred)
    mean_metrics = _metrics(validation_frame["value"], mean_pred)
    baseline_name, baseline_metrics = min(
        (("previous_period", naive_metrics), ("recent_3_period_mean", mean_metrics)),
        key=lambda item: item[1]["wape"],
    )
    beats_baseline = model_metrics["wape"] <= baseline_metrics["wape"]
    residual_std = float(np.std(model_pred - validation_frame["value"].to_numpy(dtype="float64"), ddof=1)) if len(validation_frame) > 1 else 0.0
    _progress(progress_callback, "running", "点评增量时间回测完成", {
        "model_metrics": model_metrics,
        "baseline_name": baseline_name,
        "baseline_metrics": baseline_metrics,
        "beats_baseline": beats_baseline,
    })

    final_model = LinearRegression()
    final_model.fit(supervised.loc[:, FEATURE_COLUMNS], supervised["value"])
    history = list(supervised["value"].astype("float64"))
    last_period = pd.Timestamp(supervised["period"].max())
    forecast_rows: list[dict[str, Any]] = []
    for offset in range(1, horizon + 1):
        period = last_period + pd.Timedelta(days=offset)
        features = pd.DataFrame([{
            "lag_1": history[-1],
            "lag_2": history[-2],
            "rolling_mean_3": float(np.mean(history[-3:])),
            "day_of_week": int(period.dayofweek),
        }], columns=FEATURE_COLUMNS)
        point = float(max(final_model.predict(features)[0], 0.0))
        margin = 1.96 * residual_std
        history.append(point)
        forecast_rows.append({
            "forecast_date": period.date().isoformat(),
            "entity_type": "scope",
            "entity_key": scope_id,
            "predicted_value": point,
            "lower_bound": max(point - margin, 0.0),
            "upper_bound": point + margin,
        })

    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.joblib"
    forecast_path = artifact_dir / "forecast.csv"
    joblib.dump(final_model, model_path)
    pd.DataFrame(forecast_rows).to_csv(forecast_path, index=False)
    metadata: dict[str, Any] = {
        "model_id": model_id,
        "task": "dianping_review_increment_forecast",
        "target_metric": TARGET_METRIC,
        "scope_id": scope_id,
        "entity_type": "scope",
        "data_origin": "trusted_snapshot",
        "production_eligible": False,
        "decision_layer": "external_trend",
        "algorithm": "LinearRegression",
        "feature_version": "review-increment-v1",
        "features": list(FEATURE_COLUMNS),
        "input_snapshot_id": str(series.iloc[-1]["snapshot_id"]),
        "training": {
            "periods": int(len(series)),
            "supervised_periods": int(len(supervised)),
            "history_start": str(supervised["period"].min().date()),
            "history_end": str(supervised["period"].max().date()),
            "horizon": horizon,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        },
        "validation": {
            "method": "last_contiguous_periods",
            "validation_periods": validation_periods,
            "validation_start": str(validation_frame["period"].min().date()),
            "validation_end": str(validation_frame["period"].max().date()),
            "actual": validation_frame["value"].tolist(),
            "predicted": model_pred.tolist(),
            "metrics": model_metrics,
            "baseline_name": baseline_name,
            "baseline_metrics": baseline_metrics,
            "alternative_baselines": {
                "previous_period": naive_metrics,
                "recent_3_period_mean": mean_metrics,
            },
            "beats_baseline": beats_baseline,
            "residual_std": residual_std,
        },
        "artifacts": {"model": str(model_path), "forecast": str(forecast_path)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (artifact_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
