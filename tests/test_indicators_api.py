"""
indicators 聚合与 API 单元测试。
"""
from fastapi.testclient import TestClient

from brandpulse.api import indicators
from brandpulse.api.app import app
from brandpulse.indicators.jobs.aggregate import aggregate


class FakeResult:
    def mappings(self):
        return self
    def all(self):
        return [
            {"date": "2026-07-28", "value": 75.5},
            {"date": "2026-07-29", "value": 78.2},
        ]


class FakeConn:
    def execute(self, sql, params=None):
        return FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeEngine:
    def connect(self):
        return FakeConn()


class FakePostgresClient:
    engine = FakeEngine()


def test_indicators_api_returns_series(monkeypatch):
    monkeypatch.setattr(indicators, "PostgresClient", FakePostgresClient)

    c = TestClient(app)
    resp = c.get("/api/v1/indicators?brand_id=MALL:苏州中心:苏州&indicator=heat")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["series"]) == 2
    assert data["series"][0]["value"] == 75.5
    assert data["meta"]["indicator"] == "heat"


def test_indicators_api_default_params(monkeypatch):
    monkeypatch.setattr(indicators, "PostgresClient", FakePostgresClient)

    c = TestClient(app)
    resp = c.get("/api/v1/indicators?brand_id=MALL_906d5b65&indicator=heat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["brand_id"] == "MALL_906d5b65"
    assert data["meta"]["indicator"] == "heat"
