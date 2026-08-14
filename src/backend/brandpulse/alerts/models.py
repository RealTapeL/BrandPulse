"""
告警数据模型：Alert 规则与 AlertHistory 触发记录。
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class AlertDestination(BaseModel):
    type: Literal["email", "webhook"] = Field(..., description="email 或 webhook")
    value: str = Field(..., description="邮箱地址或 webhook URL")

    @model_validator(mode="after")
    def _valid_destination(self):
        self.value = self.value.strip()
        if self.type == "email":
            local, separator, domain = self.value.partition("@")
            if not separator or not local or "." not in domain:
                raise ValueError("邮件通知地址格式无效")
        else:
            parsed = urlparse(self.value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Webhook 地址必须是完整的 http:// 或 https:// URL")
        return self


class AlertCreate(BaseModel):
    name: str = Field(..., min_length=1, description="告警名")
    brand_id: Optional[str] = Field(default=None, description="品牌 ID，空则监控全量")
    metric: str = Field(..., description="指标名：reputation/heat/sov/review_count/data_freshness_hours")
    operator: str = Field(..., description="比较运算符：> < = >= <=")
    threshold: float = Field(..., description="阈值")
    destinations: List[AlertDestination] = Field(default_factory=list, description="通知目的地")
    enabled: bool = Field(default=True, description="是否启用")
    cooldown_minutes: int = Field(default=60, ge=5, le=10080, description="持续异常提醒冷却时间")
    notify_recovery: bool = Field(default=True, description="恢复正常时是否通知")

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, v: str) -> str:
        if v not in (">", "<", "=", ">=", "<="):
            raise ValueError("operator 必须是 >、<、=、>=、<= 之一")
        return v

    @field_validator("metric")
    @classmethod
    def _valid_metric(cls, v: str) -> str:
        allowed = {"reputation", "heat", "sov", "review_count", "data_freshness_hours", "rent_to_sales_ratio", "sales_per_sqm"}
        if v not in allowed:
            raise ValueError(f"metric 必须是: {', '.join(sorted(allowed))}")
        return v


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    brand_id: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    destinations: Optional[List[AlertDestination]] = None
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(default=None, ge=5, le=10080)
    notify_recovery: Optional[bool] = None

    @field_validator("operator")
    @classmethod
    def _valid_update_operator(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in (">", "<", "=", ">=", "<="):
            raise ValueError("operator 必须是 >、<、=、>=、<= 之一")
        return v

    @field_validator("metric")
    @classmethod
    def _valid_update_metric(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"reputation", "heat", "sov", "review_count", "data_freshness_hours", "rent_to_sales_ratio", "sales_per_sqm"}:
            raise ValueError("不支持的告警指标")
        return v


class AlertResponse(AlertCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class AlertHistoryItem(BaseModel):
    id: int
    alert_id: int
    checked_at: datetime
    triggered: bool
    metric_value: Optional[float]
    message: Optional[str]
    event_type: str = "check"
    notification_status: str = "not_requested"
    sent_log: Any
