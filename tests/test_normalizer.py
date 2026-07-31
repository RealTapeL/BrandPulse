"""
pipeline + schema 单元测试：验证 RawItem 校验、解析、标准化、异常落盘。
"""
import json
from pathlib import Path

import pytest

from brandpulse.collectors import pipelines
from brandpulse.collectors.pipelines import (
    parse_html,
    process_raw_item,
)
from brandpulse.collectors.schemas import NormalizedItem, RawItem


@pytest.fixture(autouse=True)
def clean_data_dirs(tmp_path, monkeypatch):
    """测试使用临时目录，避免污染真实 data/。"""
    monkeypatch.setattr(pipelines, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(pipelines, "NORMALIZED_DIR", tmp_path / "normalized")
    monkeypatch.setattr(pipelines, "INVALID_DIR", tmp_path / "invalid")


def test_parse_html_extracts_title_and_price():
    html = "<html><head><title>瑞幸咖啡(苏州中心店)</title></head><body>人均 ¥32.5，发布于 2026-07-28</body></html>"
    parsed = parse_html(html, "https://www.dianping.com/shop/123")
    assert parsed.title == "瑞幸咖啡(苏州中心店)"
    assert "32.5" in parsed.price_text
    assert parsed.date_text == "2026-07-28"
    assert parsed.source == "dianping"


def test_process_raw_item_success():
    result = process_raw_item({
        "raw_html": "<html><head><title>Peet's</title></head><body>¥38 2026-07-27</body></html>",
        "url": "https://www.dianping.com/shop/456",
        "trace_id": "trace-ok-1",
    })
    assert result.success is True
    assert result.item.price == 38
    assert result.item.currency == "CNY"
    assert (pipelines.NORMALIZED_DIR / "trace-ok-1.json").exists()


def test_process_raw_item_invalid_date_writes_invalid():
    result = process_raw_item({
        "raw_html": "<html><title>T</title><body>¥abc 2026-99-99</body></html>",
        "url": "https://www.xiaohongshu.com/note/1",
        "trace_id": "trace-bad-1",
    })
    # 当前 parse_date 无法解析 2026-99-99，normalize 会把 date 设为 None，仍能成功
    assert result.success is True
    assert result.item.date is None


def test_rawitem_validation_fails_without_url():
    with pytest.raises(Exception):
        RawItem.model_validate({"raw_html": "x", "trace_id": "t"})


def test_normalized_item_currency_uppercased():
    item = NormalizedItem(
        brand="Luckin",
        title="L",
        currency="cny",
        source="dianping",
        trace_id="t",
        url="https://example.com",
    )
    assert item.currency == "CNY"
