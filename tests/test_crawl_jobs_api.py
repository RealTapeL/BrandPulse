"""
Crawl jobs API 单元测试：mock enqueue_crawl，验证 POST 创建任务与 GET 查询。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brandpulse.api.app import app
from brandpulse.db_clients.postgres_client import PostgresClient
from tests.conftest import AUTH_HEADERS


@pytest.fixture
def client(monkeypatch):
    created = []

    def fake_enqueue(meta):
        created.append(meta)
        return "rq-job-123"

    # 不要真正运行 worker，避免触发 WebBridge。
    monkeypatch.setattr("brandpulse.collectors.jobs.enqueue_crawl", fake_enqueue)

    # 数据库依赖 PostgresClient；实际 POST 会写库，这里直接测 HTTP 接口形态
    yield TestClient(app, headers=AUTH_HEADERS), created
    job_ids = [meta.get("job_id") for meta in created if meta.get("job_id")]
    if job_ids:
        with PostgresClient().engine.begin() as conn:
            conn.execute(text("DELETE FROM crawl_jobs WHERE job_id = ANY(:job_ids)"), {"job_ids": job_ids})


def test_create_crawl_job(client):
    c, created = client
    resp = c.post("/api/v1/crawl_jobs", json={
        "brand_id": "LK001",
        "mall": "苏州中心",
        "category": "咖啡",
        "cities": ["苏州"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["rq_job_id"] == "rq-job-123"
    assert len(created) == 1
    assert created[0]["mall"] == "苏州中心"

    fetched = c.get(f"/api/v1/crawl_jobs/{data['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["rq_job_id"] == "rq-job-123"

    listed = c.get("/api/v1/crawl_jobs", params={"brand_id": "LK001", "size": 10})
    assert listed.status_code == 200
    assert any(item["job_id"] == data["job_id"] for item in listed.json()["items"])
