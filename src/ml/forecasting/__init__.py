"""可审计的时间序列预测模块。

本包只负责真实数据集的下载、校验、训练、回测和预测，不生成业务 mock 数据。
公开基准数据与内部经营数据严格分开，并在模型元数据中记录数据来源和生产资格。
"""

from .datasets import DATASET_SPECS, DatasetSpec, ensure_dataset, load_dataset
from .training import train_store_sales

__all__ = [
    "DATASET_SPECS",
    "DatasetSpec",
    "ensure_dataset",
    "load_dataset",
    "train_store_sales",
]
