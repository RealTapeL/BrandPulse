"""销售时序监督学习特征。所有滞后/滚动特征只使用预测时点之前的数据。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


GROUP_COLUMNS = ("store", "item")
TARGET_COLUMN = "sales"
LAGS = (1, 7, 14, 28)
ROLLING_WINDOWS = (7, 14, 28)
FEATURE_COLUMNS = (
    "store",
    "item",
    "day_of_week",
    "day_of_month",
    "day_of_year",
    "week_of_year",
    "month",
    "year",
    "is_weekend",
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
)


def _calendar_features(dates: pd.Series) -> pd.DataFrame:
    values = pd.to_datetime(dates)
    iso_week = values.dt.isocalendar().week.astype("int16")
    return pd.DataFrame(
        {
            "day_of_week": values.dt.dayofweek.astype("int8"),
            "day_of_month": values.dt.day.astype("int8"),
            "day_of_year": values.dt.dayofyear.astype("int16"),
            "week_of_year": iso_week.to_numpy(),
            "month": values.dt.month.astype("int8"),
            "year": values.dt.year.astype("int16"),
            "is_weekend": (values.dt.dayofweek >= 5).astype("int8"),
        },
        index=dates.index,
    )


def make_supervised_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """构造一阶监督样本，并丢弃没有完整 28 天历史的样本。"""
    required = set(GROUP_COLUMNS) | {"date", TARGET_COLUMN}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"特征构造缺少字段: {sorted(missing)}")

    work = frame.loc[:, ["date", *GROUP_COLUMNS, TARGET_COLUMN]].copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise").dt.normalize()
    work = work.sort_values([*GROUP_COLUMNS, "date"], kind="stable").reset_index(drop=True)
    grouped = work.groupby(list(GROUP_COLUMNS), sort=False, observed=True)[TARGET_COLUMN]
    for lag in LAGS:
        work[f"lag_{lag}"] = grouped.shift(lag)
    for window in ROLLING_WINDOWS:
        work[f"rolling_mean_{window}"] = grouped.transform(
            lambda values: values.shift(1).rolling(window=window, min_periods=window).mean()
        )
    calendar = _calendar_features(work["date"])
    for column in calendar.columns:
        work[column] = calendar[column].to_numpy()
    result = work.dropna(subset=list(FEATURE_COLUMNS) + [TARGET_COLUMN]).copy()
    if result.empty:
        raise ValueError("可训练样本为空，至少需要 28 天连续历史")
    return result.reset_index(drop=True)


def feature_matrix(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    missing = set(FEATURE_COLUMNS + ("sales",)) - set(frame.columns)
    if missing:
        raise ValueError(f"监督样本缺少字段: {sorted(missing)}")
    return frame.loc[:, list(FEATURE_COLUMNS)], frame["sales"].astype("float64")


def row_features(
    date: datetime | pd.Timestamp,
    store: int,
    item: int,
    history: Iterable[float],
) -> dict[str, Any]:
    """为递归多步预测构造一行特征；history 按时间升序且不含当前时点。"""
    values = np.asarray(list(history), dtype="float64")
    if len(values) < max(max(LAGS), max(ROLLING_WINDOWS)):
        raise ValueError("递归预测需要至少 28 个历史观测值")
    timestamp = pd.Timestamp(date)
    return {
        "store": int(store),
        "item": int(item),
        "day_of_week": int(timestamp.dayofweek),
        "day_of_month": int(timestamp.day),
        "day_of_year": int(timestamp.dayofyear),
        "week_of_year": int(timestamp.isocalendar().week),
        "month": int(timestamp.month),
        "year": int(timestamp.year),
        "is_weekend": int(timestamp.dayofweek >= 5),
        "lag_1": float(values[-1]),
        "lag_7": float(values[-7]),
        "lag_14": float(values[-14]),
        "lag_28": float(values[-28]),
        "rolling_mean_7": float(values[-7:].mean()),
        "rolling_mean_14": float(values[-14:].mean()),
        "rolling_mean_28": float(values[-28:].mean()),
    }
