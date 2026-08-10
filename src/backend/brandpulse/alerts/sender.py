"""告警通知发送：只报告真实发送结果，不伪造 mock 成功。"""
from email.message import EmailMessage
import smtplib
from typing import Any, Dict, List

import requests

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """通过配置的 SMTP 服务器发送邮件。"""
    if not Config.SMTP_HOST or not Config.SMTP_FROM:
        raise RuntimeError("SMTP 未配置，请设置 SMTP_HOST 和 SMTP_FROM")

    message = EmailMessage()
    message["From"] = Config.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=Config.ALERT_WEBHOOK_TIMEOUT) as smtp:
        if Config.SMTP_USE_TLS:
            smtp.starttls()
        if Config.SMTP_USERNAME:
            smtp.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        smtp.send_message(message)
    logger.info(f"[alert][email] sent to={to} subject={subject}")
    return {"type": "email", "to": to, "status": "sent"}


def send_webhook(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """向用户配置的 webhook 发起真实 HTTP POST。"""
    if not url.startswith(("http://", "https://")):
        raise ValueError("webhook 地址必须是 http:// 或 https://")
    response = requests.post(url, json=payload, timeout=Config.ALERT_WEBHOOK_TIMEOUT)
    response.raise_for_status()
    logger.info(f"[alert][webhook] sent url={url} status_code={response.status_code}")
    return {"type": "webhook", "url": url, "status": "sent", "status_code": response.status_code}


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
