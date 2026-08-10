"""公开预测数据集注册、下载与严格校验。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PROJECT_ROOT / "data" / "raw" / "ml" / "benchmark"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    name: str
    source_url: str
    source_page: str
    license_note: str
    description: str
    filename: str
    required_columns: tuple[str, ...]
    data_origin: str = "public_benchmark"
    production_eligible: bool = False


DATASET_SPECS: dict[str, DatasetSpec] = {
    "store_sales": DatasetSpec(
        key="store_sales",
        name="Store Item Demand Forecasting Challenge",
        source_url=(
            "https://raw.githubusercontent.com/skforecast/skforecast-datasets/"
            "main/data/store_sales.csv"
        ),
        source_page="https://github.com/skforecast/skforecast-datasets",
        license_note="GitHub 仓库注明原始来源为 Kaggle Store Item Demand Forecasting Challenge；使用前需遵守原始数据规则。",
        description="2013-01-01 至 2017-12-31 的 50 个 SKU、10 家门店销售交易，适合门店/商品日销量预测基准。",
        filename="store_sales.csv",
        required_columns=("date", "store", "item", "sales"),
    ),
}

_COLUMN_ALIASES: dict[str, set[str]] = {
    "date": {"date", "日期", "record_date", "统计日期"},
    "store": {"store", "store_id", "门店", "门店id", "门店_id"},
    "item": {"item", "item_id", "sku", "product", "商品", "商品id", "商品_id"},
    "sales": {"sales", "unit_sales", "销量", "销售量", "销量数量"},
}


def dataset_path(dataset_key: str) -> Path:
    spec = DATASET_SPECS.get(dataset_key)
    if spec is None:
        raise KeyError(f"未知公开数据集: {dataset_key}")
    return DATASET_ROOT / spec.filename


def manifest_path(dataset_key: str) -> Path:
    return dataset_path(dataset_key).with_suffix(".manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_frame(frame: pd.DataFrame, spec: DatasetSpec) -> dict[str, Any]:
    missing = sorted(set(spec.required_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"数据集缺少必要字段: {missing}")
    if frame.empty:
        raise ValueError("数据集为空")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("date 存在无法解析的值")
    numeric = pd.to_numeric(frame["sales"], errors="coerce")
    if numeric.isna().any():
        raise ValueError("sales 存在无法解析的值")
    if frame[list(spec.required_columns)].isna().any().any():
        raise ValueError("必要字段存在空值")
    if (numeric < 0).any():
        raise ValueError("sales 存在负数，拒绝作为销量目标训练")
    if frame.duplicated(subset=["date", "store", "item"]).any():
        raise ValueError("date/store/item 存在重复记录，拒绝静默聚合")

    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "stores": int(frame["store"].nunique()),
        "items": int(frame["item"].nunique()),
        "min_date": dates.min().date().isoformat(),
        "max_date": dates.max().date().isoformat(),
        "missing_values": int(frame[list(spec.required_columns)].isna().sum().sum()),
    }


def normalize_store_sales_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """把 CSV/Excel 的常见中英文列名归一为预测模块标准列名。"""
    rename: dict[Any, str] = {}
    matched: dict[str, Any] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower()
        for canonical, aliases in _COLUMN_ALIASES.items():
            if normalized in {alias.lower() for alias in aliases}:
                if canonical in matched and matched[canonical] != column:
                    raise ValueError(f"字段 {canonical} 存在多个候选列")
                matched[canonical] = column
                rename[column] = canonical
                break
    result = frame.rename(columns=rename)
    missing = sorted(set(("date", "store", "item", "sales")) - set(result.columns))
    if missing:
        raise ValueError(f"数据集缺少必要字段: {missing}；支持 date/store/item/sales 或常见中文别名")
    return result


def canonicalize_store_sales_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """归一、校验并转换为训练所需的标准数据框。"""
    spec = DATASET_SPECS["store_sales"]
    normalized = normalize_store_sales_frame(frame)
    stats = _validate_frame(normalized, spec)
    canonical = normalized.loc[:, list(spec.required_columns)].copy()
    canonical["date"] = pd.to_datetime(canonical["date"], errors="raise").dt.normalize()
    canonical["store"] = pd.to_numeric(canonical["store"], errors="raise").astype("int32")
    canonical["item"] = pd.to_numeric(canonical["item"], errors="raise").astype("int32")
    canonical["sales"] = pd.to_numeric(canonical["sales"], errors="raise").astype("float32")
    return (
        canonical.sort_values(["date", "store", "item"], kind="stable").reset_index(drop=True),
        stats,
    )


def load_dataset(dataset_key: str) -> pd.DataFrame:
    """读取本地公开数据集，并在训练前再次校验来源数据。"""
    spec = DATASET_SPECS.get(dataset_key)
    if spec is None:
        raise KeyError(f"未知数据集: {dataset_key}")
    path = dataset_path(dataset_key)
    if not path.exists():
        raise FileNotFoundError(f"数据集尚未下载: {path}")
    return load_store_sales_file(path)


def load_store_sales_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    frame = pd.read_csv(path)
    canonical, _ = canonicalize_store_sales_frame(frame)
    return canonical


def ensure_dataset(dataset_key: str, *, force: bool = False, timeout: int = 60) -> dict[str, Any]:
    """从登记的公开来源下载数据，生成可追溯 manifest，并返回校验结果。"""
    spec = DATASET_SPECS.get(dataset_key)
    if spec is None:
        raise KeyError(f"未知数据集: {dataset_key}")
    path = dataset_path(dataset_key)
    manifest = manifest_path(dataset_key)
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)

    if force or not path.exists():
        temp_path = path.with_suffix(path.suffix + ".download")
        try:
            with requests.get(spec.source_url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with temp_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    frame = pd.read_csv(path)
    stats = _validate_frame(frame, spec)
    result = {
        **asdict(spec),
        "required_columns": list(spec.required_columns),
        "path": str(path),
        "sha256": _sha256(path),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "validation": stats,
    }
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def dataset_status(dataset_key: str) -> dict[str, Any]:
    spec = DATASET_SPECS.get(dataset_key)
    if spec is None:
        raise KeyError(f"未知数据集: {dataset_key}")
    manifest = manifest_path(dataset_key)
    status: dict[str, Any] = {
        **asdict(spec),
        "required_columns": list(spec.required_columns),
        "downloaded": dataset_path(dataset_key).exists(),
        "manifest_path": str(manifest),
    }
    if manifest.exists():
        status.update(json.loads(manifest.read_text(encoding="utf-8")))
    return status
