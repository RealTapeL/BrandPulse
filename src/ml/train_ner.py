"""
命名实体识别（NER）训练脚本（最小可用）。
默认做 BRAND / MALL 两类的 token 分类。数据量小，仅做 pipeline 演示。

示例：
    PYTHONPATH=src/backend src/ml/train_ner.py --epochs 1 --output_dir models/ner/v1
"""
import argparse
import ast
import json
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer, Trainer, TrainingArguments

LABELS = ["O", "B-BRAND", "I-BRAND", "B-MALL", "I-MALL"]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
DEFAULT_MODEL = "uer/roberta-base-finetuned-chinanews-chinese"


def load_csv(path: Path):
    texts, entities_list = [], []
    with path.open(encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            if not line.strip():
                continue
            # 简单按最后一个逗号切分；entities 是 JSON 字符串
            text, entities_json = line.rsplit(",", 1)
            texts.append(text.strip('"'))
            entities_list.append(ast.literal_eval(entities_json.strip()))
    return texts, entities_list


def align_labels(text, entities, tokenizer, max_length=64):
    """把字符级实体标签对齐到 tokenizer 的 token 级 BIO。"""
    encoding = tokenizer(text, truncation=True, padding="max_length", max_length=max_length, return_offsets_mapping=True)
    labels = [LABEL2ID["O"]] * max_length
    offset_mapping = encoding.pop("offset_mapping")

    for ent in entities:
        word = ent["word"]
        label = ent["label"]
        start = text.find(word)
        if start == -1:
            continue
        end = start + len(word)
        for i, (tok_start, tok_end) in enumerate(offset_mapping):
            if tok_start >= start and tok_end <= end and tok_end > tok_start:
                if i == 0 or labels[i - 1] == LABEL2ID["O"] or tok_start == start:
                    labels[i] = LABEL2ID[f"B-{label}"]
                else:
                    labels[i] = LABEL2ID[f"I-{label}"]
    return encoding, labels


class NerDataset(torch.utils.data.Dataset):
    def __init__(self, encodings_list, labels_list):
        self.encodings = encodings_list
        self.labels = labels_list

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: torch.tensor(self.encodings[idx][k][0]) for k in self.encodings[idx]}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/labelled/ner.csv"))
    parser.add_argument("--output_dir", type=Path, default=Path("models/ner/v1"))
    parser.add_argument("--model_name", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--max_length", type=int, default=64)
    args = parser.parse_args()

    texts, entities_list = load_csv(args.data)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    encodings_list, labels_list = [], []
    for text, entities in zip(texts, entities_list):
        enc, labels = align_labels(text, entities, tokenizer, args.max_length)
        encodings_list.append(enc)
        labels_list.append(labels)

    dataset = NerDataset(encodings_list, labels_list)

    model = AutoModelForTokenClassification.from_pretrained(
        args.model_name,
        num_labels=len(LABELS),
        ignore_mismatched_sizes=True,
    )

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
    print(f"NER 模型已保存到 {args.output_dir}")


if __name__ == "__main__":
    main()
