# BrandPulse ML 模块

情感分类、命名实体识别（NER）与可审计的时间序列预测。

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

模型不存在时返回 503，不返回 mock 结果。

## 销售预测

预测模块只登记和使用可追溯的真实公开基准数据，不生成 mock 经营数据。
使用 ml.forecasting.cli 下载、校验、训练和回测 store_sales 数据集。

    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli datasets
    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli download --dataset store_sales
    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli train --dataset store_sales --validation-days 28 --horizon 14

训练会校验字段、日期、负数、重复记录和缺失值，按最后连续 28 天做时间回测，
再用完整历史重新拟合模型，并保存 model.joblib、metadata.json 和 forecast.csv。
公开基准模型会写入 data_origin=public_benchmark、production_eligible=false，
不能直接用于中国商场经营决策。待获得有授权的内部 POS / 客流数据并完成主数据映射、
质量扫描和独立回测后，才允许登记为生产模型。

## Web 平台闭环

机器学习页面支持完整的输入、训练、导出和审计流程：

- `POST /api/v1/ml/datasets/upload`：上传 CSV/XLSX/XLSM，校验必需字段、日期、销量、缺失值和重复记录，并登记 SHA-256 与数据范围。
- `POST /api/v1/ml/forecasting/train`：使用公开数据集或已校验的上传数据创建后台训练任务。
- `GET /api/v1/ml/logs`：查询数据输入、训练各阶段和预测导出的持久化日志。
- `POST /api/v1/ml/forecasting/exports`：将模型的 `forecast.csv` 异步导出为 CSV 或 XLSX。
- `GET /api/v1/ml/forecasting/exports/{export_id}/download`：下载已完成的预测文件。

上传数据会保存到 `data/raw/ml/uploads/`，预测导出保存到 `data/processed/ml/exports/`，两者都不写入
`store_operations`。训练和导出由 `brandpulse-ml` RQ 队列执行；生产资格默认关闭。

## 数据

标注数据见 `data/labelled/`：
- `sentiment.csv` — text,label
- `ner.csv` — text,entities（JSON 字符串）
