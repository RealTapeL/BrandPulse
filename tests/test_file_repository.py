import json
import tempfile
from pathlib import Path

import pytest

from brandpulse.storage.modules.file_repository import FileMetricsRepository


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield FileMetricsRepository(cache_dir=tmpdir)


def test_upsert_and_list_metric(repo):
    metric = {
        "metric_id": "LK001_北京_xhs_12345_0",
        "brand_id": "LK001",
        "metric_date": "2026-07-26",
        "platform": "xiaohongshu_api",
        "review_count": 36,
        "data_source": "https://www.xiaohongshu.com/explore/abc123",
    }
    assert repo.upsert_metric(metric) is True

    metrics = repo.list_metrics()
    assert len(metrics) == 1
    assert metrics[0]["metric_id"] == metric["metric_id"]
    assert metrics[0]["brand_id"] == "LK001"


def test_upsert_overwrites_same_metric_id(repo):
    metric = {
        "metric_id": "X_0",
        "brand_id": "A",
        "metric_date": "2026-07-26",
        "platform": "p",
        "review_count": 1,
        "data_source": "url1",
    }
    repo.upsert_metric(metric)
    metric["review_count"] = 99
    repo.upsert_metric(metric)

    metrics = repo.list_metrics()
    assert len(metrics) == 1
    assert metrics[0]["review_count"] == 99


def test_filter_by_brand_and_platform(repo):
    for i in range(3):
        repo.upsert_metric(
            {
                "metric_id": f"M{i}",
                "brand_id": "LK001" if i < 2 else "SB001",
                "metric_date": "2026-07-26",
                "platform": "xiaohongshu" if i == 0 else "dianping",
                "review_count": i,
                "data_source": "url",
            }
        )

    assert len(repo.list_metrics(brand_id="LK001")) == 2
    assert len(repo.list_metrics(platform="xiaohongshu")) == 1
    assert len(repo.list_metrics(brand_id="LK001", platform="dianping")) == 1


def test_jsonl_file_created(repo):
    repo.upsert_metric(
        {
            "metric_id": "X",
            "brand_id": "A",
            "metric_date": "2026-07-26",
            "platform": "p",
            "review_count": 1,
            "data_source": "url",
        }
    )
    path = Path(repo.cache_dir) / "metrics_2026-07-26.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["metric_id"] == "X"
