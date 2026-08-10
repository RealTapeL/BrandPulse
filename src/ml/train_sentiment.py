"""
情感分类训练脚本（最小可用）。
默认使用轻量中文模型；可通过 --model_name 指定测试用 tiny 模型以加速验证。

示例：
    cd /home/lsy/BrandPulse
    PYTHONPATH=src/backend src/ml/train_sentiment.py --epochs 1 --output_dir models/sentiment/v1
"""
import argparse
import csv
import json
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

LABELS = ["negative", "positive"]
DEFAULT_MODEL = "uer/roberta-base-finetuned-chinanews-chinese"  # 中文分类模型，约 100MB


def load_csv(path: Path):
    texts, labels = [], []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            text = (row.get("text") or "").strip()
            label = (row.get("label") or "").strip()
            if not text:
                continue
            if label not in LABELS:
                raise ValueError(f"不支持的情感标签: {label}")
            texts.append(text)
            labels.append(LABELS.index(label))
    return texts, labels


class TextDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/labelled/sentiment.csv"))
    parser.add_argument("--output_dir", type=Path, default=Path("models/sentiment/v1"))
    parser.add_argument("--model_name", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--max_length", type=int, default=64)
    args = parser.parse_args()

    texts, labels = load_csv(args.data)
    if not texts:
        raise ValueError("训练数据为空")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(LABELS),
        ignore_mismatched_sizes=True,
    )

    encodings = tokenizer(texts, truncation=True, padding=True, max_length=args.max_length)
    dataset = TextDataset(encodings, labels)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        logging_steps=1,
        save_strategy="epoch",
        remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=dataset)
    trainer.train()

    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    (args.output_dir / "labels.json").write_text(json.dumps(LABELS), encoding="utf-8")
    print(f"模型已保存到 {args.output_dir}")


if __name__ == "__main__":
    main()
