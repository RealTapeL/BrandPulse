# BrandPulse ML 模型目录

情感分类模型与 NER 模型保存位置：

- `models/sentiment/v1/` — 情感分类（positive / negative）
- `models/ner/v1/` — 命名实体识别（BRAND / MALL）

训练命令：

```bash
cd /home/lsy/BrandPulse
PYTHONPATH=src/backend .venv/bin/python src/ml/train_sentiment.py --epochs 1 --output_dir models/sentiment/v1
PYTHONPATH=src/backend .venv/bin/python src/ml/train_ner.py --epochs 1 --output_dir models/ner/v1
```

预测模型工件位于 models/forecasting/<dataset>/v1/，由训练流程本地生成，不提交二进制文件。

销售预测训练：

    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli train --dataset store_sales --validation-days 28 --horizon 14

公开数据模型会在元数据中标记为 public_benchmark 且 production_eligible=false。

推理服务：

```bash
PYTHONPATH=src/backend .venv/bin/python -m uvicorn src.ml.inference_service:app --port 9000
```
