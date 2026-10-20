from pathlib import Path

import pandas as pd

from ml.forecasting.external_reviews import make_supervised_frame, train_review_increment


def _series(periods=20):
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    return pd.DataFrame({
        "period": dates,
        "value": [10 + index for index in range(periods)],
        "snapshot_id": [f"snapshot-{index}" for index in range(periods)],
    })


def test_external_review_features_keep_snapshot_boundary():
    frame = make_supervised_frame(_series())
    assert len(frame) == 17
    assert frame.iloc[0]["snapshot_id"] == "snapshot-3"
    assert frame.iloc[0]["lag_1"] == 12


def test_external_review_training_writes_evaluation_and_forecast_artifacts(tmp_path: Path):
    metadata = train_review_increment(
        series=_series(),
        validation_periods=3,
        horizon=7,
        output_dir=tmp_path,
        model_id="review-test-v1",
        scope_id="scope-test",
    )
    assert metadata["target_metric"] == "dp_review_count_delta"
    assert metadata["validation"]["baseline_name"]
    assert "beats_baseline" in metadata["validation"]
    assert len(pd.read_csv(tmp_path / "forecast.csv")) == 7
    assert (tmp_path / "model.joblib").exists()
    assert (tmp_path / "metadata.json").exists()
