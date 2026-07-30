# BrandPulse ML 模块

最小可用的情感分类 + 命名实体识别（NER）训练与推理。

## 训练

```bash
cd /home/lsy/BrandPulse
PYTHONPATH=src/backend .venv/bin/python src/ml/train_sentiment.py --epochs 1 --output_dir models/sentiment/v1 --model_name hf-internal-testing/tiny-random-roberta
PYTHONPATH=src/backend .venv/bin/python src/ml/train_ner.py --epochs 1 --output_dir models/ner/v1 --model_name hf-internal-testing/tiny-random-roberta
```

> 生产默认用 `hfl/chinese-roberta-wwm-ext`；测试/验证可用 `hf-internal-testing/tiny-random-roberta` 加速。

## 推理

```bash
PYTHONPATH=src/backend .venv/bin/python -m uvicorn src.ml.inference_service:app --port 9000
```

接口：
- `POST /ml/sentiment` body `{ "texts": ["..."] }` → `{ predictions: [...], model_loaded: bool }`
- `POST /ml/ner` body `{ "text": "..." }` → `{ entities: [...], model_loaded: bool }`
- `GET /ml/health`

模型不存在时返回 mock 结果，确保服务可先行启动。

## 数据

标注数据见 `data/labelled/`：
- `sentiment.csv` — text,label
- `ner.csv` — text,entities（JSON 字符串）
