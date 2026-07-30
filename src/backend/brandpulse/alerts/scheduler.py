"""
告警调度器（APScheduler）：每 5 分钟检查所有启用的告警规则。

提供 start_scheduler() / shutdown_scheduler() 生命周期函数，供 API 启动时调用。
"""
import json
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from brandpulse.alerts.models import AlertCreate
from brandpulse.alerts.sender import send
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _fetch_metric_value(metric: str, brand_id: Optional[str]) -> Optional[float]:
    """
    从 indicators 表取最新指标值。
    brand_id 为空时按指标名取全局最新一条。
    TODO: 接入品牌基础表后可按真实 brand_id 聚合。
    """
    sql = """
        SELECT value
        FROM indicators
        WHERE indicator = :metric
        ORDER BY date DESC
        LIMIT 1
    """
    params = {"metric": metric}
    if brand_id:
        sql = sql.replace("WHERE indicator = :metric", "WHERE indicator = :metric AND brand_id = :brand_id")
        params["brand_id"] = brand_id

    try:
        client = PostgresClient()
        with client.engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text(sql), params).first()
            return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        logger.error(f"[scheduler] 查询指标 {metric} 失败: {e}")
        return None


def _check_operator(value: float, op: str, threshold: float) -> bool:
    return {
        ">": value > threshold,
        "<": value < threshold,
        "=": value == threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
    }.get(op, False)


def _check_alert(alert: dict) -> bool:
    value = _fetch_metric_value(alert["metric"], alert.get("brand_id"))
    triggered = False
    message = None
    if value is not None:
        triggered = _check_operator(value, alert["operator"], float(alert["threshold"]))
        message = f"告警 [{alert['name']}]: {alert['metric']}={value}, 阈值{alert['operator']}{alert['threshold']}"

    sent_log = []
    if triggered and alert.get("destinations"):
        sent_log = send(alert["destinations"], message)

    insert_sql = """
        INSERT INTO alert_history (alert_id, triggered, metric_value, message, sent_log)
        VALUES (:alert_id, :triggered, :metric_value, :message, :sent_log)
    """
    try:
        client = PostgresClient()
        client.execute(insert_sql, {
            "alert_id": alert["id"],
            "triggered": triggered,
            "metric_value": value,
            "message": message,
            "sent_log": json.dumps(sent_log),
        })
    except Exception as e:
        logger.error(f"[scheduler] 写入 alert_history 失败: {e}")

    if triggered:
        logger.warning(message)
    else:
        logger.info(f"[scheduler] {alert['name']} 未触发 (value={value})")
    return triggered


def check_all_alerts() -> int:
    """立即检查所有启用的告警规则，返回触发数。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        from sqlalchemy import text
        rows = conn.execute(
            text("SELECT * FROM alerts WHERE enabled = TRUE")
        ).mappings().all()

    triggered_count = 0
    for alert in rows:
        if _check_alert(dict(alert)):
            triggered_count += 1
    return triggered_count


def start_scheduler(interval_minutes: int = 5) -> BackgroundScheduler:
    """启动后台告警调度器。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        check_all_alerts,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="brandpulse-alerts",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"[scheduler] 告警调度器已启动，间隔 {interval_minutes} 分钟")
    return _scheduler


def shutdown_scheduler() -> None:
    """关闭调度器。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("[scheduler] 告警调度器已关闭")
