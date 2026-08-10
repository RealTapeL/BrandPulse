"""报告数据准备与新鲜度门禁。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

from brandpulse.api.dashboard import build_dashboard
from brandpulse.config.config import Config
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository


class ReportDataNotReadyError(RuntimeError):
    """数据不完整或不新鲜时拒绝生成正式报告。"""


def _age_hours(value: str | None) -> int | None:
    if not value:
        return None
    return max((date.today() - date.fromisoformat(value)).days * 24, 0)


def report_readiness(scope_id: str) -> Dict[str, Any]:
    scope = MonitoringScopeRepository().get(scope_id)
    if not scope:
        raise ReportDataNotReadyError("监测项目不存在")
    dashboard = build_dashboard(scope_id=scope_id)
    indicator_age = _age_hours(dashboard.get("stat_date"))
    source_age = _age_hours(dashboard.get("crawl_date"))
    xiaohongshu_age = _age_hours(scope.get("latest_xiaohongshu_date"))
    reasons = []
    if not dashboard.get("stat_date") or not dashboard.get("indicators"):
        reasons.append("当前范围没有可用于报告的真实指标快照")
    if not dashboard.get("crawl_date") or not dashboard.get("dp_shops"):
        reasons.append("当前范围没有可用于报告的大众点评原始数据")
    if indicator_age is not None and indicator_age > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"指标数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    if source_age is not None and source_age > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"来源数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    if dashboard.get("xhs_notes") and xiaohongshu_age is not None and xiaohongshu_age > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"小红书来源数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "scope": scope,
        "stat_date": dashboard.get("stat_date"),
        "crawl_date": dashboard.get("crawl_date"),
        "indicator_age_hours": indicator_age,
        "source_age_hours": source_age,
        "xiaohongshu_age_hours": xiaohongshu_age,
        "dashboard": dashboard,
    }


def require_report_ready(scope_id: str) -> Dict[str, Any]:
    readiness = report_readiness(scope_id)
    if not readiness["ready"]:
        raise ReportDataNotReadyError("；".join(readiness["reasons"]))
    return readiness
