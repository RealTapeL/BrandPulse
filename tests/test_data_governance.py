"""数据治理 API 和标准化规则的契约测试。"""
from fastapi.testclient import TestClient

from brandpulse.api.app import app
from brandpulse.data_governance.normalizer import normalize_text
from tests.conftest import AUTH_HEADERS


def test_normalize_text_only_removes_presentation_differences():
    assert normalize_text(" Peet's 皮爷咖啡 ") == "peets皮爷咖啡"
    assert normalize_text("M Stand（苏州中心店）") == "mstand苏州中心店"
    assert normalize_text(None) == ""


def test_data_governance_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/v1/data-governance/summary")
    assert response.status_code == 401


def test_data_governance_scan_and_summary():
    client = TestClient(app, headers=AUTH_HEADERS)
    scanned = client.post("/api/v1/data-governance/scan")
    assert scanned.status_code == 200
    assert scanned.json()["status"] == "completed"
    assert scanned.json()["records_checked"]["stores"] >= 0

    summary = client.get("/api/v1/data-governance/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "records" in data
    assert "latest_scan" in data


def test_data_governance_lists_pending_store_aliases():
    client = TestClient(app, headers=AUTH_HEADERS)
    response = client.get("/api/v1/data-governance/store-aliases", params={"status": "pending"})
    assert response.status_code == 200
    assert "items" in response.json()
