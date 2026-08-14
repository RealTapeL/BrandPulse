"""数据治理 API 和标准化规则的契约测试。"""
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.data_governance.normalizer import normalize_text
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.mall_heat_repository import XhsNoteRepository
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


def test_monitoring_dataset_is_not_reported_as_unknown_brand():
    client = TestClient(app, headers=AUTH_HEADERS)
    scanned = client.post("/api/v1/data-governance/scan")
    assert scanned.status_code == 200

    response = client.get("/api/v1/data-governance/issues", params={"status": "open"})
    assert response.status_code == 200
    assert not any(
        item["issue_type"] == "unresolved_dataset_brand"
        and item["entity_key"].startswith("MALL_")
        for item in response.json()["items"]
    )


def test_data_governance_lists_pending_store_aliases():
    client = TestClient(app, headers=AUTH_HEADERS)
    response = client.get("/api/v1/data-governance/store-aliases", params={"status": "pending"})
    assert response.status_code == 200
    assert "items" in response.json()


def test_raw_record_lineage_is_written_with_raw_record():
    client = TestClient(app, headers=AUTH_HEADERS)
    note_id = f"lineage-test-{uuid4().hex}"
    run_id = f"source_{uuid4().hex}"
    note = {
        "note_id": note_id,
        "brand_id": "MALL_lineage_test",
        "city": "苏州",
        "mall_name": "测试商场",
        "title": "记录级血缘测试",
        "author_name": "test",
        "likes": 1,
        "publish_time": "",
        "note_url": "https://example.com/lineage-test",
        "keyword": "测试",
        "crawl_date": str(date.today()),
    }
    lineage = {
        "run_id": run_id,
        "source_name": "xiaohongshu_webbridge",
        "record_type": "xhs_note",
        "record_key": note_id,
        "crawl_date": str(date.today()),
        "metadata": {"note_id": note_id},
    }
    try:
        assert XhsNoteRepository().upsert_note(note, lineage=lineage)
        response = client.get(
            "/api/v1/data-governance/lineage/records",
            params={"run_id": run_id},
        )
        assert response.status_code == 200
        rows = response.json()["items"]
        assert len(rows) == 1
        assert rows[0]["record_key"] == note_id
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM raw_record_lineage WHERE run_id = :run_id"
            ), {"run_id": run_id})
            conn.execute(text(
                "DELETE FROM xhs_notes WHERE note_id = :note_id"
            ), {"note_id": note_id})
