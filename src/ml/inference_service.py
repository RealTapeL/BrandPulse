"""
ML 推理服务（FastAPI）：加载情感 & NER 模型，提供 /ml/sentiment 与 /ml/ner。
模型不存在时明确返回 503，避免把 mock 结果混入业务数据。

启动：
    PYTHONPATH=src/backend .venv/bin/python -m uvicorn src.ml.inference_service:app --port 9000
"""
import json
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer, pipeline

app = FastAPI(title="BrandPulse ML Inference")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SENTIMENT_DIR = PROJECT_ROOT / "models" / "sentiment" / "v1"
NER_DIR = PROJECT_ROOT / "models" / "ner" / "v1"

_sentiment_pipe = None
_ner_pipe = None


def _json_safe(value):
    """将 Transformers/Numpy 推理结果转换为 FastAPI 可序列化的基础类型。"""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return item_method()
        except (TypeError, ValueError):
            pass
    return value


def _load_sentiment():
    global _sentiment_pipe
    if _sentiment_pipe is not None:
        return _sentiment_pipe
    if not SENTIMENT_DIR.exists():
        return None
    model = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_DIR)
    tokenizer = AutoTokenizer.from_pretrained(SENTIMENT_DIR)
    _sentiment_pipe = pipeline("text-classification", model=model, tokenizer=tokenizer)
    return _sentiment_pipe


def _load_ner():
    global _ner_pipe
    if _ner_pipe is not None:
        return _ner_pipe
    if not NER_DIR.exists():
        return None
    model = AutoModelForTokenClassification.from_pretrained(NER_DIR)
    tokenizer = AutoTokenizer.from_pretrained(NER_DIR)
    labels_path = NER_DIR / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else None
    _ner_pipe = pipeline("token-classification", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
    return _ner_pipe, labels


class SentimentRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, description="待分析文本列表")


class SentimentResponse(BaseModel):
    predictions: List[dict]
    model_loaded: bool


class NerRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待抽取文本")


class NerResponse(BaseModel):
    entities: List[dict]
    model_loaded: bool


@app.post("/ml/sentiment", response_model=SentimentResponse)
def sentiment(req: SentimentRequest):
    pipe = _load_sentiment()
    if pipe is None:
        raise HTTPException(status_code=503, detail="情感模型未部署，请先训练并部署 models/sentiment/v1")
    predictions = _json_safe(pipe(req.texts))
    return SentimentResponse(predictions=predictions, model_loaded=True)


@app.post("/ml/ner", response_model=NerResponse)
def ner(req: NerRequest):
    result = _load_ner()
    if result is None:
        raise HTTPException(status_code=503, detail="NER 模型未部署，请先训练并部署 models/ner/v1")
    pipe, _ = result
    entities = _json_safe(pipe(req.text))
    return NerResponse(entities=entities, model_loaded=True)


@app.get("/ml/health")
def health():
    return {
        "sentiment_model": SENTIMENT_DIR.exists(),
        "ner_model": NER_DIR.exists(),
    }
