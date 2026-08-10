"""
ML 推理服务单元测试：模型不存在时返回 mock 结果，服务不崩溃。
"""
from fastapi.testclient import TestClient

from src.ml.inference_service import app

client = TestClient(app)


def test_sentiment_requires_deployed_model(monkeypatch):
    monkeypatch.setattr("src.ml.inference_service._load_sentiment", lambda: None)
    resp = client.post("/ml/sentiment", json={"texts": ["好喝"]})
    assert resp.status_code == 503


def test_ner_requires_deployed_model(monkeypatch):
    monkeypatch.setattr("src.ml.inference_service._load_ner", lambda: None)
    resp = client.post("/ml/ner", json={"text": "星巴克在苏州中心"})
    assert resp.status_code == 503


def test_health_reports_model_presence():
    resp = client.get("/ml/health")
    assert resp.status_code == 200
    assert "sentiment_model" in resp.json()
    assert "ner_model" in resp.json()
