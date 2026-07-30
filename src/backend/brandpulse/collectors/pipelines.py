"""
数据采集 pipeline：解析 -> 标准化 -> 校验 -> 落盘。
正常数据写入 data/normalized/<trace_id>.json，异常写入 data/invalid/<trace_id>.json。
"""
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from brandpulse.collectors.schemas import (
    NormalizationResult,
    NormalizedItem,
    ParsedItem,
    RawItem,
)
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[4] / "data"
RAW_DIR = DATA_DIR / "raw"
NORMALIZED_DIR = DATA_DIR / "normalized"
INVALID_DIR = DATA_DIR / "invalid"


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    INVALID_DIR.mkdir(parents=True, exist_ok=True)


def parse_html(html: str, url: str) -> ParsedItem:
    """
    通用 HTML 解析示例：提取 title、价格文本、日期文本。
    TODO: 针对大众点评/小红书/高德等不同页面应使用专用 extractor，此处仅做演示骨架。
    """
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else None

    # 粗略价格匹配：¥32.5 / 人均 45 / 32.5元
    price_match = re.search(r"[￥¥人均\s]*([\d]+(?:\.[\d]+)?)\s*[元]?", soup.get_text())
    price_text = price_match.group(0).strip() if price_match else None

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", soup.get_text())
    date_text = date_match.group(1) if date_match else None

    # source 启发式判断
    source = None
    if "dianping.com" in url:
        source = "dianping"
    elif "xiaohongshu.com" in url:
        source = "xiaohongshu"

    return ParsedItem(
        title=title,
        price_text=price_text,
        currency="CNY",
        date_text=date_text,
        source=source,
    )


def _parse_price(price_text: str | None) -> Decimal | None:
    if not price_text:
        return None
    digits = re.search(r"[\d]+(?:\.[\d]+)?", price_text)
    if not digits:
        return None
    try:
        return Decimal(digits.group(0))
    except InvalidOperation:
        return None


def _parse_date(date_text: str | None) -> datetime | None:
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def normalize_item(raw: RawItem, parsed: ParsedItem | None = None) -> NormalizationResult:
    """
    将 RawItem + ParsedItem 标准化为 NormalizedItem。
    校验失败时返回 NormalizationResult(success=False, error=...)。
    """
    if parsed is None:
        parsed = parse_html(raw.raw_html, str(raw.url))

    try:
        item = NormalizedItem(
            brand=parsed.brand or "unknown",
            title=parsed.title or "未命名",
            price=_parse_price(parsed.price_text),
            currency=parsed.currency or "CNY",
            date=_parse_date(parsed.date_text),
            sku=parsed.sku,
            source=parsed.source or "unknown",
            trace_id=raw.trace_id,
            url=raw.url,
        )
        return NormalizationResult(success=True, item=item, raw_trace_id=raw.trace_id)
    except Exception as e:
        return NormalizationResult(success=False, error=str(e), raw_trace_id=raw.trace_id)


def _write_invalid(raw: RawItem, error: str) -> Path:
    INVALID_DIR.mkdir(parents=True, exist_ok=True)
    path = INVALID_DIR / f"{raw.trace_id}.json"
    path.write_text(
        json.dumps(
            {"trace_id": raw.trace_id, "url": str(raw.url), "error": error, "fetched_at": raw.fetched_at.isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _write_normalized(item: NormalizedItem) -> Path:
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    path = NORMALIZED_DIR / f"{item.trace_id}.json"
    path.write_text(item.model_dump_json(indent=2), encoding="utf-8")
    return path


def process_raw_item(raw_dict: dict[str, Any]) -> NormalizationResult:
    """
    端到端处理：dict -> RawItem -> parse -> normalize -> 写盘。

    Returns:
        NormalizationResult
    """
    ensure_dirs()

    try:
        raw = RawItem.model_validate(raw_dict)
    except Exception as e:
        logger.error(f"[pipeline] RawItem 校验失败: {e}")
        return NormalizationResult(success=False, error=f"RawItem 校验失败: {e}")

    # 原始页先落盘（便于回溯）
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{raw.trace_id}.json"
    raw_path.write_text(raw.model_dump_json(indent=2), encoding="utf-8")

    parsed = parse_html(raw.raw_html, str(raw.url))
    result = normalize_item(raw, parsed)

    if result.success and result.item:
        _write_normalized(result.item)
        logger.info(f"[pipeline] normalized {raw.trace_id} -> {result.item.title}")
    else:
        _write_invalid(raw, result.error or "unknown")
        logger.warning(f"[pipeline] invalid {raw.trace_id}: {result.error}")

    return result
