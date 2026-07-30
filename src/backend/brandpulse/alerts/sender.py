"""
告警通知发送：dev 模式下仅记录日志并返回模拟结果，不真正发邮件/ webhook。
TODO: 生产环境接入 SMTP / 企业微信 / 钉钉 webhook。
"""
from typing import Any, Dict, List

from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """模拟发送邮件（dev 仅记录）。"""
    logger.info(f"[alert][email] to={to} subject={subject}")
    return {"type": "email", "to": to, "status": "mock_sent"}


def send_webhook(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """模拟发送 webhook（dev 仅记录）。"""
    logger.info(f"[alert][webhook] url={url} payload={payload}")
    return {"type": "webhook", "url": url, "status": "mock_sent"}


def send(destinations: List[Dict[str, Any]], message: str) -> List[Dict[str, Any]]:
    """按目的地批量发送通知。"""
    logs = []
    for d in destinations:
        try:
            if d.get("type") == "email":
                logs.append(send_email(d["value"], "BrandPulse 告警", message))
            elif d.get("type") == "webhook":
                logs.append(send_webhook(d["value"], {"message": message}))
            else:
                logs.append({"type": d.get("type"), "error": "未知通知类型"})
        except Exception as e:
            logs.append({"type": d.get("type"), "error": str(e)})
    return logs
