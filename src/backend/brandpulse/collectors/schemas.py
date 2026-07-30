"""
数据采集的 Pydantic schema：原始页、解析中间态、标准化条目。
用于校验、文档化与 LLM Agent 工具输入输出。
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator


class RawItem(BaseModel):
    """从爬虫抓取的原始页面条目。"""

    raw_html: str = Field(..., description="原始 HTML 文本")
    url: HttpUrl = Field(..., description="页面 URL")
    trace_id: str = Field(..., description="本次采集 trace_id")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="抓取时间 UTC")


class ParsedItem(BaseModel):
    """解析后的中间结构，字段可能缺失（由 normalizer 补齐）。"""

    title: Optional[str] = Field(default=None, description="商品/笔记/门店标题")
    price_text: Optional[str] = Field(default=None, description="价格原始文本，如 ￥32.5")
    currency: Optional[str] = Field(default=None, description="货币代码：CNY/USD/...")
    date_text: Optional[str] = Field(default=None, description="日期原始文本")
    sku: Optional[str] = Field(default=None, description="SKU/商品编号/门店 ID")
    source: Optional[str] = Field(default=None, description="来源平台：dianping/xiaohongshu/...")
    brand: Optional[str] = Field(default=None, description="品牌名")


class NormalizedItem(BaseModel):
    """标准化后的数据条目，可入库存储。"""

    brand: str = Field(..., description="品牌名")
    title: str = Field(..., description="标题")
    price: Optional[Decimal] = Field(default=None, description="价格数值")
    currency: str = Field(default="CNY", description="货币代码")
    date: Optional[datetime] = Field(default=None, description="发布/评价日期 UTC")
    sku: Optional[str] = Field(default=None, description="SKU/门店 ID")
    source: str = Field(..., description="来源平台")
    trace_id: str = Field(..., description="采集 trace_id")
    url: HttpUrl = Field(..., description="原始 URL")

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return (v or "CNY").upper()


class NormalizationResult(BaseModel):
    """normalizer 处理结果：成功或失败。"""

    success: bool
    item: Optional[NormalizedItem] = None
    error: Optional[str] = None
    raw_trace_id: Optional[str] = None


__all__ = [
    "RawItem",
    "ParsedItem",
    "NormalizedItem",
    "NormalizationResult",
    "ValidationError",
]
