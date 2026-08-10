"""模型加载与递归多步预测。"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, row_features


def recursive_forecast(
    model: Any,
    history_frame: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    """按门店×商品递归预测未来 horizon 天，不使用未来真实标签。"""
    if horizon < 1:
        raise ValueError("horizon 必须大于 0")
    required = {"date", "store", "item", "sales"}
    if not required.issubset(history_frame.columns):
        raise ValueError(f"递归预测缺少字段: {sorted(required - set(history_frame.columns))}")

    frame = history_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame = frame.sort_values(["store", "item", "date"], kind="stable")
    histories: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=28))
    for row in frame.itertuples(index=False):
        histories[(int(row.store), int(row.item))].append(float(row.sales))
    if not histories or min(len(values) for values in histories.values()) < 28:
        raise ValueError("每个门店×商品序列至少需要 28 个历史观测值")

    last_date = frame["date"].max()
    keys = sorted(histories)
    rows: list[dict[str, Any]] = []
    for offset in range(1, horizon + 1):
        forecast_date = last_date + pd.Timedelta(days=offset)
        feature_rows = [
            row_features(forecast_date, store, item, histories[(store, item)])
            for store, item in keys
        ]
        features = pd.DataFrame(feature_rows).loc[:, list(FEATURE_COLUMNS)]
        predictions = np.maximum(np.asarray(model.predict(features), dtype="float64"), 0.0)
        for (store, item), prediction in zip(keys, predictions):
            value = float(prediction)
            histories[(store, item)].append(value)
            rows.append(
                {
                    "date": forecast_date.date().isoformat(),
                    "store": store,
                    "item": item,
                    "predicted_sales": value,
                }
            )
    return pd.DataFrame(rows)


def load_artifact(artifact_dir: str | Path) -> tuple[Any, dict[str, Any]]:
    directory = Path(artifact_dir)
    model_path = directory / "model.joblib"
    metadata_path = directory / "metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(f"预测模型工件不完整: {directory}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return joblib.load(model_path), metadata
