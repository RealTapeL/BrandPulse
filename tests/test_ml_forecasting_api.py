import io
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from brandpulse.api.app import app
from brandpulse.api.auth import create_access_token
from brandpulse.storage.ml_forecasting_repository import MLDatasetRepository


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
