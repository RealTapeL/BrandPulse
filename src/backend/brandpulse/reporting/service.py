"""报告数据准备与快照发布门禁。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from brandpulse.api.dashboard import build_dashboard
from brandpulse.config.config import Config
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.trusted_data_repository import SnapshotRepository


class ReportDataNotReadyError(RuntimeError):
    """数据不完整、不新鲜或未明确绑定快照时拒绝生成正式报告。"""


def _age_hours(value: Any) -> Optional[float]:
    if not value:
        return None
    raw = str(value)
    try:
        timestamp = datetime.fromisoformat(raw)
    except ValueError:
        timestamp = datetime.combine(date.fromisoformat(raw), datetime.min.time())
    return max((datetime.now() - timestamp).total_seconds() / 3600, 0.0)


def _legacy_readiness(scope: Dict[str, Any]) -> Dict[str, Any]:
    """仅保留给无可信快照的旧测试/历史接口；新报告创建路径不会使用它。"""
    dashboard = build_dashboard(scope_id=scope["scope_id"])
    indicator_age = _age_hours(dashboard.get("stat_date"))
    source_age = _age_hours(dashboard.get("crawl_date"))
    reasons = []
    if not dashboard.get("stat_date") or not dashboard.get("indicators"):
        reasons.append("当前范围没有可用于报告的真实指标快照")
    if not dashboard.get("crawl_date") or not dashboard.get("dp_shops"):
        reasons.append("当前范围没有可用于报告的大众点评原始数据")
    if indicator_age is not None and indicator_age > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"指标数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    if source_age is not None and source_age > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"来源数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "scope": scope,
        "snapshot": None,
        "snapshot_id": None,
        "stat_date": dashboard.get("stat_date"),
        "crawl_date": dashboard.get("crawl_date"),
        "indicator_age_hours": indicator_age,
        "source_age_hours": source_age,
        "dashboard": dashboard,
        "compatibility_legacy": True,
    }


def report_readiness(scope_id: str, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
    scope = MonitoringScopeRepository().get(scope_id)
    if not scope:
        raise ReportDataNotReadyError("监测项目不存在")
    snapshots = SnapshotRepository()
    snapshot = snapshots.get(snapshot_id) if snapshot_id else snapshots.latest_released(scope_id)
    # 保留旧报告查询的兼容路径，但新建/定时报告强制 require_report_ready(..., require_snapshot=True)。
    if not snapshot:
        return _legacy_readiness(scope)
    if snapshot["scope_id"] != scope_id:
        raise ReportDataNotReadyError("报告快照不属于当前监测范围")
    dashboard = build_dashboard(scope_id=scope_id, snapshot_id=snapshot["snapshot_id"])
    age_hours = _age_hours(snapshot.get("observed_at"))
    source_results = snapshot.get("source_results", [])
    coverage = snapshot.get("source_coverage") or {}
    reasons = []
    if snapshot["status"] not in {"ready", "published"}:
        reasons.append("快照不是 ready/published 状态")
    if snapshot.get("freshness_status") != "fresh":
        reasons.append("快照数据已过期或新鲜度未知")
    if age_hours is not None and age_hours > Config.REPORT_MAX_DATA_AGE_HOURS:
        reasons.append(f"快照数据已超过 {Config.REPORT_MAX_DATA_AGE_HOURS} 小时")
    if snapshot.get("data_mode") != "multi_source":
        reasons.append("当前不是完整多来源快照；正式报告自动跳过，避免把单源数据包装为完整结论")
    if snapshot.get("quality_grade") not in {"A", "B"}:
        reasons.append(f"快照质量等级为 {snapshot.get('quality_grade')}，未达到正式报告门槛")
    if any(result.get("status") != "success" for result in source_results):
        reasons.append("存在未成功来源；正式报告不能将缺失来源按零处理")
    if not dashboard.get("metric_summary"):
        reasons.append("快照尚未产出可追溯指标")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "scope": scope,
        "snapshot": snapshot,
        "snapshot_id": snapshot["snapshot_id"],
        "stat_date": dashboard.get("stat_date"),
        "crawl_date": dashboard.get("crawl_date"),
        "indicator_age_hours": age_hours,
        "source_age_hours": age_hours,
        "source_coverage": coverage,
        "quality_grade": snapshot.get("quality_grade"),
        "metric_version": "snapshot-v2",
        "dashboard": dashboard,
        "compatibility_legacy": False,
    }


def require_report_ready(
    scope_id: str,
    snapshot_id: Optional[str] = None,
    *,
    require_snapshot: bool = False,
) -> Dict[str, Any]:
    readiness = report_readiness(scope_id, snapshot_id)
    if require_snapshot and not readiness.get("snapshot_id"):
        raise ReportDataNotReadyError("当前范围没有可发布的可信快照，不能生成正式报告")
    if not readiness["ready"]:
        raise ReportDataNotReadyError("；".join(readiness["reasons"]))
    return readiness
