import io
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from brandpulse.api.app import app
from brandpulse.api.auth import create_access_token
from brandpulse.storage.ml_forecasting_repository import MLDatasetRepository
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository


client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('ml-test')}"}


def test_ml_dataset_registry_requires_authentication():
    response = client.get("/api/v1/ml/datasets")
    assert response.status_code == 401


def test_ml_dataset_registry_returns_registered_public_dataset():
    response = client.get("/api/v1/ml/datasets", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert any(
        item["key"] == "store_sales"
        and item["data_origin"] == "public_benchmark"
        and item["production_eligible"] is False
        for item in data
    )


def test_public_dataset_download_is_bound_to_registered_source(monkeypatch):
    calls = []

    def fake_download(dataset_key):
        calls.append(dataset_key)
        return {
            "key": dataset_key,
            "data_origin": "public_benchmark",
            "production_eligible": False,
            "sha256": "a" * 64,
            "validation": {"rows": 913000, "stores": 10, "items": 50},
        }

    class FakeLogs:
        def append(self, **kwargs):
            return kwargs

    monkeypatch.setattr("brandpulse.api.ml_forecasting.download_public_dataset", fake_download)
    monkeypatch.setattr("brandpulse.api.ml_forecasting.MLOperationLogRepository", FakeLogs)

    response = client.post("/api/v1/ml/datasets/store_sales/download", headers=AUTH_HEADERS)

    assert response.status_code == 200, response.text
    assert calls == ["store_sales"]
    assert response.json()["production_eligible"] is False


def test_public_dataset_download_rejects_unregistered_dataset():
    response = client.post("/api/v1/ml/datasets/not-registered/download", headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_public_dataset_summary_has_explicit_non_internal_boundary(monkeypatch):
    monkeypatch.setattr(
        "brandpulse.api.ml_forecasting.public_dataset_summary",
        lambda dataset_key, daily_limit, ranking_limit: {
            "dataset_key": dataset_key,
            "production_eligible": False,
            "summary": {"rows": 913000},
            "boundary": "公开零售基准数据；不得写入 store_operations",
        },
    )

    response = client.get(
        "/api/v1/ml/datasets/store_sales/summary",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"]["rows"] == 913000
    assert "不得写入 store_operations" in response.json()["boundary"]


def test_ml_dataset_upload_validates_and_keeps_upload_out_of_operations_table():
    rows = ["date,store,item,sales"]
    for day in range(35):
        rows.append(f"{date(2024, 1, 1) + timedelta(days=day)},1,101,{10 + day}")
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=AUTH_HEADERS,
        files={"file": ("sales.csv", io.BytesIO("\n".join(rows).encode()), "text/csv")},
    )
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["data_origin"] == "user_upload"
    assert record["status"] == "valid"
    assert record["validation"]["rows"] == 35
    assert record["production_eligible"] is False

    stored_path = Path(record["stored_path"])
    manifest_path = stored_path.with_suffix(".manifest.json")
    try:
        assert stored_path.exists()
        assert manifest_path.exists()
    finally:
        MLDatasetRepository().delete(record["upload_id"])
        stored_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)


def test_external_forecast_readiness_does_not_create_training_when_data_is_insufficient():
    scope = next((item for item in TrustedScopeRepository().list() if item.get("latest_snapshot_id")), None)
    if not scope:
        return
    response = client.get(
        "/api/v1/ml/forecasting/readiness",
        headers=AUTH_HEADERS,
        params={"scope_id": scope["scope_id"]},
    )
    assert response.status_code == 200, response.text
    readiness = response.json()
    assert readiness["status"] in {"ready", "not_ready"}
    if readiness["status"] == "not_ready":
        blocked = client.post(
            "/api/v1/ml/forecasting/train",
            headers=AUTH_HEADERS,
            json={
                "dataset_key": "trusted_dianping_reviews",
                "scope_id": scope["scope_id"],
                "horizon": 7,
            },
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == "forecast_not_ready"
