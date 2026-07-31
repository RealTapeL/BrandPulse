"""
告警数据模型：Alert 规则与 AlertHistory 触发记录。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AlertDestination(BaseModel):
    type: str = Field(..., description="email 或 webhook")
    value: str = Field(..., description="邮箱地址或 webhook URL")


class AlertCreate(BaseModel):
    name: str = Field(..., min_length=1, description="告警名")
    brand_id: Optional[str] = Field(default=None, description="品牌 ID，空则监控全量")
    metric: str = Field(..., description="指标名：reputation/heat/sov/review_count")
    operator: str = Field(..., description="比较运算符：> < = >= <=")
    threshold: float = Field(..., description="阈值")
    destinations: List[AlertDestination] = Field(default_factory=list, description="通知目的地")
    enabled: bool = Field(default=True, description="是否启用")

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, v: str) -> str:
        if v not in (">", "<", "=", ">=", "<="):
            raise ValueError("operator 必须是 >、<、=、>=、<= 之一")
        return v


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    brand_id: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    destinations: Optional[List[AlertDestination]] = None
    enabled: Optional[bool] = None


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
    sent_log: Dict[str, Any]
