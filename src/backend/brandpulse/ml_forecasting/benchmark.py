"""公开销售基准数据的下载、摘要与来源边界。

公开数据只用于验证销售时序、特征构造和模型回测链路，不写入
``store_operations``，也不参与苏州中心等真实监测范围的经营指标。
"""

from __future__ import annotations

from typing import Any


def _datasets_module():
    from ml.forecasting.datasets import DATASET_SPECS, dataset_status, ensure_dataset, load_dataset

    return DATASET_SPECS, dataset_status, ensure_dataset, load_dataset


def download_public_dataset(dataset_key: str) -> dict[str, Any]:
    """下载登记过的公开数据集，并返回可审计的来源与校验结果。"""
    specs, _, ensure_dataset, _ = _datasets_module()
    if dataset_key not in specs:
        raise KeyError(f"未知公开数据集: {dataset_key}")
    return ensure_dataset(dataset_key)


def public_dataset_summary(
    dataset_key: str,
    *,
    daily_limit: int = 30,
    ranking_limit: int = 10,
) -> dict[str, Any]:
    """返回公开数据集的真实摘要，不补齐、不生成模拟值。"""
    specs, status_loader, _, load_dataset = _datasets_module()
    if dataset_key not in specs:
        raise KeyError(f"未知公开数据集: {dataset_key}")
    status = status_loader(dataset_key)
    if not status.get("downloaded"):
        raise FileNotFoundError("公开数据集尚未下载，请先执行下载与校验")

    frame = load_dataset(dataset_key)
    daily = (
        frame.groupby("date", as_index=False)["sales"]
        .sum()
        .sort_values("date")
        .tail(max(1, min(int(daily_limit), 90)))
    )
    store_ranking = (
        frame.groupby("store", as_index=False)["sales"]
        .sum()
        .sort_values(["sales", "store"], ascending=[False, True])
        .head(max(1, min(int(ranking_limit), 50)))
    )
    item_ranking = (
        frame.groupby("item", as_index=False)["sales"]
        .sum()
        .sort_values(["sales", "item"], ascending=[False, True])
        .head(max(1, min(int(ranking_limit), 50)))
    )

    return {
        "dataset_key": dataset_key,
        "dataset_name": specs[dataset_key].name,
        "data_origin": specs[dataset_key].data_origin,
        "production_eligible": False,
        "source_url": specs[dataset_key].source_url,
        "source_page": specs[dataset_key].source_page,
        "license_note": specs[dataset_key].license_note,
        "validation": status.get("validation") or {},
        "summary": {
            "rows": int(len(frame)),
            "stores": int(frame["store"].nunique()),
            "items": int(frame["item"].nunique()),
            "total_sales_units": float(frame["sales"].sum()),
            "daily_periods": int(frame["date"].nunique()),
            "daily_series": [
                {"date": row.date.date().isoformat(), "sales": float(row.sales)}
                for row in daily.itertuples(index=False)
            ],
            "top_stores": [
                {"store": int(row.store), "sales": float(row.sales)}
                for row in store_ranking.itertuples(index=False)
            ],
            "top_items": [
                {"item": int(row.item), "sales": float(row.sales)}
                for row in item_ranking.itertuples(index=False)
            ],
        },
        "boundary": (
            "公开零售基准数据；不得写入 store_operations，"
            "不得作为内部 POS、苏州中心经营指标或内部生产预测依据。"
        ),
    }
