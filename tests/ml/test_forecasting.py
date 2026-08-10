from collections import deque

import numpy as np
import pandas as pd

from ml.forecasting.features import FEATURE_COLUMNS, make_supervised_frame, row_features
from ml.forecasting.predict import recursive_forecast


def _series_frame(days: int = 42) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    rows = []
    for store in (1, 2):
        for item in (1, 2):
            for index, date in enumerate(dates):
                rows.append({"date": date, "store": store, "item": item, "sales": index + store + item})
    return pd.DataFrame(rows)


def test_supervised_features_use_only_prior_history():
    frame = make_supervised_frame(_series_frame())
    assert list(FEATURE_COLUMNS) == [
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
    ]
    first = frame.sort_values(["store", "item", "date"]).iloc[0]
    assert first["date"] == pd.Timestamp("2024-01-29")
    assert first["lag_1"] == 29.0
    assert first["lag_7"] == 23.0
    assert first["rolling_mean_7"] == 26.0


def test_row_features_require_28_history_points():
    with np.testing.assert_raises(ValueError):
        row_features(pd.Timestamp("2024-02-01"), 1, 1, deque([1.0] * 27))


class _MeanModel:
    def predict(self, features):
        return np.full(len(features), features["rolling_mean_7"].mean())


def test_recursive_forecast_has_requested_horizon_and_nonnegative_values():
    forecast = recursive_forecast(_MeanModel(), _series_frame(), horizon=3)
    assert len(forecast) == 3 * 4
    assert forecast["date"].nunique() == 3
    assert (forecast["predicted_sales"] >= 0).all()
