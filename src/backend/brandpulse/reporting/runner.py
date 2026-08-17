"""RQ 报告生成任务：只导出通过新鲜度门禁的真实数据快照。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.opportunities.service import OpportunityService
from brandpulse.reporting.delivery import process_due_report_deliveries
from brandpulse.reporting.service import ReportDataNotReadyError, require_report_ready
from brandpulse.storage.report_repository import ReportRunRepository

logger = get_logger(__name__)


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if "detail" in frame.columns:
        frame["detail"] = frame["detail"].map(
            lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        )
    return frame


def _summary_frame(readiness: dict) -> pd.DataFrame:
    scope = readiness["scope"]
    dashboard = readiness["dashboard"]
    snapshot = readiness.get("snapshot") or {}
    return pd.DataFrame([
        {"字段": "项目", "值": scope["mall_name"]},
        {"字段": "城市", "值": scope["city"]},
        {"字段": "品类", "值": scope["category"]},
        {"字段": "可信快照 ID", "值": readiness.get("snapshot_id") or ""},
        {"字段": "数据截止时间", "值": snapshot.get("observed_at") or readiness["stat_date"]},
        {"字段": "快照质量等级", "值": readiness.get("quality_grade") or snapshot.get("quality_grade") or ""},
        {"字段": "来源覆盖", "值": json.dumps(readiness.get("source_coverage") or {}, ensure_ascii=False)},
        {"字段": "指标版本", "值": readiness.get("metric_version") or "snapshot-v2"},
        {"字段": "指标日期", "值": readiness["stat_date"]},
        {"字段": "点评采集日期", "值": readiness["crawl_date"]},
        {"字段": "指标记录数", "值": len(dashboard["indicators"])},
        {"字段": "点评门店数", "值": len(dashboard["dp_shops"])},
        {"字段": "小红书笔记数", "值": len(dashboard["xhs_notes"])},
    ])


def run_report(report_id: str) -> dict:
    repository = ReportRunRepository()
    report = repository.get(report_id)
    if not report:
        raise ValueError(f"报告运行不存在: {report_id}")
    if not repository.mark_running(report_id):
        return {"report_id": report_id, "status": "already_finished"}
    try:
        readiness = require_report_ready(
            report["scope_id"], report.get("snapshot_id"), require_snapshot=True,
        )
        dashboard = readiness["dashboard"]
        output_dir = Config.PROCESSED_DIR / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{report_id}.{report['file_format']}"
        summary = _summary_frame(readiness)
        indicators = _frame(dashboard["indicators"])
        dianping = _frame(dashboard["dp_shops"])
        xiaohongshu = _frame(dashboard["xhs_notes"])
        opportunities = _frame(OpportunityService().list(
            scope_id=report["scope_id"], snapshot_id=readiness["snapshot_id"], limit=200,
        )["items"])
        if report["file_format"] == "xlsx":
            with pd.ExcelWriter(target, engine="openpyxl") as writer:
                summary.to_excel(writer, sheet_name="报告摘要", index=False)
                indicators.to_excel(writer, sheet_name="指标快照", index=False)
                dianping.to_excel(writer, sheet_name="点评明细", index=False)
                xiaohongshu.to_excel(writer, sheet_name="小红书明细", index=False)
                opportunities.to_excel(writer, sheet_name="机会与行动", index=False)
        elif report["file_format"] == "csv":
            indicators.assign(
                scope_id=readiness["scope"]["scope_id"],
                city=readiness["scope"]["city"],
                mall_name=readiness["scope"]["mall_name"],
                category=readiness["scope"]["category"],
                stat_date=readiness["stat_date"],
                crawl_date=readiness["crawl_date"],
            ).to_csv(target, index=False)
        else:
            raise ValueError(f"不支持的报告格式: {report['file_format']}")
        row_count = len(indicators) + len(dianping) + len(xiaohongshu) + len(opportunities)
        metadata = {
            "scope": readiness["scope"],
            "snapshot_id": readiness["snapshot_id"],
            "data_cutoff_at": readiness["snapshot"].get("observed_at"),
            "source_coverage": readiness.get("source_coverage") or {},
            "quality_grade": readiness.get("quality_grade"),
            "metric_version": readiness.get("metric_version"),
            "stat_date": readiness["stat_date"],
            "crawl_date": readiness["crawl_date"],
            "indicator_age_hours": readiness["indicator_age_hours"],
            "source_age_hours": readiness["source_age_hours"],
            "sheets": ["报告摘要", "指标快照", "点评明细", "小红书明细", "机会与行动"] if report["file_format"] == "xlsx" else ["指标快照"],
        }
        repository.finish_success(
            report_id,
            snapshot_date=readiness["stat_date"],
            file_path=str(target),
            row_count=row_count,
            metadata=metadata,
        )
        # 定时计划可显式关闭人工审核；默认仍必须人工审核，且仅在审批后才会有投递任务。
        if report.get("require_approval") is False:
            approved = repository.get(report_id)
            if approved:
                from brandpulse.storage.report_repository import ReportPublicationRepository

                ReportPublicationRepository().approve_automatically(report_id)
                if approved.get("notification_channel") in {"smtp", "webhook"} and approved.get("audience"):
                    ReportPublicationRepository().queue_delivery_jobs(report_id)
                    process_due_report_deliveries(limit=len(approved["audience"]))
        return {"report_id": report_id, "status": "success", "file_path": str(target)}
    except ReportDataNotReadyError as exc:
        repository.finish_failure(report_id, str(exc), status="skipped")
        return {"report_id": report_id, "status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.exception("[report] generation failed: report_id=%s", report_id)
        repository.finish_failure(report_id, str(exc))
        raise
