"""报告审核后的真实投递；SMTP 附带导出文件，Webhook 只发送可追溯的报告元数据。"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import smtplib
from typing import Any, Dict

import requests

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.storage.report_repository import ReportPublicationRepository

logger = get_logger(__name__)


def _report_message(report: Dict[str, Any]) -> str:
    scope = report.get("metadata", {}).get("scope") or {}
    return "\n".join([
        "BrandPulse 可信快照报告已审核通过。",
        f"报告 ID：{report['report_id']}",
        f"监测范围：{scope.get('city') or report.get('city') or '-'} · "
        f"{scope.get('mall_name') or report.get('mall_name') or '-'} · "
        f"{scope.get('category') or report.get('category') or '-'}",
        f"可信快照：{report.get('snapshot_id') or '-'}",
        f"数据截止：{report.get('data_cutoff_at') or '-'}",
        f"来源覆盖：{report.get('source_coverage') or {}}",
        f"质量等级：{report.get('quality_grade') or '-'}",
        "附件为经审核的导出文件。公开数据仅用于口碑、声量和竞争线索，不代表销售或招商结论。",
    ])


def send_report_email(recipient: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """向单个邮箱投递已审核报告，并附上真实已生成的文件。"""
    if not Config.SMTP_HOST or not Config.SMTP_FROM:
        raise RuntimeError("SMTP 未配置，请设置 SMTP_HOST 和 SMTP_FROM")
    path = Path(str(report.get("file_path") or ""))
    if not path.is_file():
        raise FileNotFoundError("报告文件不存在，不能邮件分发")

    message = EmailMessage()
    message["From"] = Config.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = f"BrandPulse 可信快照报告 · {report.get('report_id')}"
    message.set_content(_report_message(report))
    if report.get("file_format") == "csv":
        message.add_attachment(path.read_bytes(), maintype="text", subtype="csv", filename=path.name)
    else:
        message.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=path.name,
        )
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=Config.ALERT_WEBHOOK_TIMEOUT) as smtp:
        if Config.SMTP_USE_TLS:
            smtp.starttls()
        if Config.SMTP_USERNAME:
            smtp.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        smtp.send_message(message)
    return {"channel": "smtp", "recipient": recipient, "status": "sent", "attachment": path.name}


def send_report_webhook(recipient: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """通知外部系统报告可用；不向 webhook 泄漏文件内容或访问凭据。"""
    if not recipient.startswith(("http://", "https://")):
        raise ValueError("Webhook 地址必须是 http:// 或 https://")
    payload = {
        "event_type": "brandpulse.report.approved",
        "report_id": report["report_id"],
        "scope_id": report["scope_id"],
        "snapshot_id": report.get("snapshot_id"),
        "data_cutoff_at": report.get("data_cutoff_at"),
        "source_coverage": report.get("source_coverage") or {},
        "quality_grade": report.get("quality_grade"),
        "metric_version": report.get("metric_version"),
        "file_format": report.get("file_format"),
        "message": "报告已审核，可由已授权用户在 BrandPulse 下载。",
    }
    response = requests.post(recipient, json=payload, timeout=Config.ALERT_WEBHOOK_TIMEOUT)
    response.raise_for_status()
    return {
        "channel": "webhook", "recipient": recipient, "status": "sent",
        "status_code": response.status_code,
    }


def send_report(channel: str, recipient: str, report: Dict[str, Any]) -> Dict[str, Any]:
    if channel == "smtp":
        return send_report_email(recipient, report)
    if channel == "webhook":
        return send_report_webhook(recipient, report)
    raise ValueError(f"不支持的报告通知渠道: {channel}")


def process_due_report_deliveries(limit: int = 100) -> Dict[str, int]:
    """消费审核后显式创建的任务；失败采用持久化指数退避，绝不伪造投递成功。"""
    repository = ReportPublicationRepository()
    summary = {"sent": 0, "retry": 0, "failed": 0}
    for _ in range(max(1, min(limit, 500))):
        job = repository.claim_due_delivery_job()
        if not job:
            break
        report = repository.report_for_delivery(job["delivery_job_id"])
        if not report:
            # 避免发送过程中报告被撤销或状态改变后将任务永久卡在 sending。
            updated = repository.finish_delivery_job(
                job["delivery_job_id"], success=False, response={}, error="报告不再处于可分发状态",
            )
            if updated:
                summary[updated["status"]] = summary.get(updated["status"], 0) + 1
            continue
        try:
            response = send_report(job["channel"], job["recipient"], report)
            updated = repository.finish_delivery_job(
                job["delivery_job_id"], success=True, response=response,
            )
        except Exception as exc:
            logger.warning("[reports] 投递失败: job=%s error=%s", job["delivery_job_id"], exc)
            updated = repository.finish_delivery_job(
                job["delivery_job_id"], success=False, response={}, error=str(exc),
            )
        if updated:
            summary[updated["status"]] = summary.get(updated["status"], 0) + 1
    return summary
