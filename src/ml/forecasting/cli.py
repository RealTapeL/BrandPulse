"""公开预测基准数据集的下载、训练和状态查询 CLI。"""

from __future__ import annotations

import argparse
import json

from .datasets import DATASET_SPECS, dataset_status, ensure_dataset
from .training import train_store_sales


def main() -> None:
    parser = argparse.ArgumentParser(description="BrandPulse 真实公开数据预测模块")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("datasets", help="列出已登记数据集")
    download = subparsers.add_parser("download", help="下载并校验公开数据集")
    download.add_argument("--dataset", default="store_sales", choices=sorted(DATASET_SPECS))
    train = subparsers.add_parser("train", help="训练并回测公开销售数据")
    train.add_argument("--dataset", default="store_sales", choices=sorted(DATASET_SPECS))
    train.add_argument("--validation-days", type=int, default=28)
    train.add_argument("--horizon", type=int, default=14)
    status = subparsers.add_parser("status", help="查看数据集状态")
    status.add_argument("--dataset", default="store_sales", choices=sorted(DATASET_SPECS))
    args = parser.parse_args()

    if args.command == "datasets":
        result = [
            {
                "key": spec.key,
                "name": spec.name,
                "source_page": spec.source_page,
                "data_origin": spec.data_origin,
                "production_eligible": spec.production_eligible,
            }
            for spec in DATASET_SPECS.values()
        ]
    elif args.command == "download":
        result = ensure_dataset(args.dataset)
    elif args.command == "status":
        result = dataset_status(args.dataset)
    else:
        result = train_store_sales(
            dataset_key=args.dataset,
            validation_days=args.validation_days,
            horizon=args.horizon,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
