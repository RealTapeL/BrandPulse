"""
告警调度器（APScheduler）：每 5 分钟检查所有启用的告警规则。

提供 start_scheduler() / shutdown_scheduler()，由独立 runner 进程调用；FastAPI 不再持有调度器。
"""
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from brandpulse.alerts.service import process_due_deliveries, record_evaluation
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _fetch_metric_value(metric: str, brand_id: Optional[str]) -> Optional[float]:
    """
    从真实指标/原始经营数据表取最新值。
    """
    indicator_sql = """
        SELECT value FROM indicators
        WHERE indicator = :metric
          AND (:brand_id IS NULL OR brand_id = :brand_id)
        ORDER BY date DESC LIMIT 1
    """
    raw_sql = """
        SELECT SUM(review_count)::numeric AS value
        FROM dp_shop_metrics
        WHERE crawl_date = (SELECT MAX(crawl_date) FROM dp_shop_metrics)
          AND (:brand_id IS NULL OR brand_id = :brand_id)
    """
    freshness_sql = """
        SELECT EXTRACT(EPOCH FROM (
            CURRENT_TIMESTAMP - MAX(crawl_date)::timestamp
        )) / 3600.0 AS value
        FROM dp_shop_metrics
        WHERE (:brand_id IS NULL OR brand_id = :brand_id)
    """
    operation_sql = {
        "rent_to_sales_ratio": """
            SELECT AVG(rent_to_sales_ratio)::numeric FROM store_operations
            WHERE record_date = (SELECT MAX(record_date) FROM store_operations)
              AND (:brand_id IS NULL OR brand_id = :brand_id)
        """,
        "sales_per_sqm": """
            SELECT AVG(sales_per_sqm)::numeric FROM store_operations
            WHERE record_date = (SELECT MAX(record_date) FROM store_operations)
              AND (:brand_id IS NULL OR brand_id = :brand_id)
        """,
    }
    if metric == "review_count":
        sql = raw_sql
    elif metric == "data_freshness_hours":
        sql = freshness_sql
    elif metric in operation_sql:
        sql = operation_sql[metric]
    else:
        sql = indicator_sql
    params = {"metric": metric, "brand_id": brand_id}

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
    if value is not None:
        triggered = _check_operator(value, alert["operator"], float(alert["threshold"]))
    try:
        result = record_evaluation(alert, triggered=triggered, value=value)
    except Exception as e:
        logger.exception("[scheduler] 告警状态记录失败: %s", e)
        return triggered

    if result.get("skipped"):
        logger.info("[scheduler] %s 正由另一个检查处理，跳过本轮", alert["name"])
    elif result["event_type"] in {"trigger", "reminder"}:
        logger.warning("[scheduler] %s: %s", result["event_type"], alert["name"])
    elif result["event_type"] == "recovery":
        logger.info("[scheduler] recovery: %s", alert["name"])
    else:
        logger.info("[scheduler] %s 检查完成 (triggered=%s, value=%s)", alert["name"], triggered, value)
    return triggered


def check_all_alerts() -> int:
    """立即检查所有启用的告警规则，返回触发数。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        from sqlalchemy import text
        rows = conn.execute(
            text("""
                SELECT alert.*,
                       COALESCE(policy.cooldown_minutes, 60) AS cooldown_minutes,
                       COALESCE(policy.notify_recovery, TRUE) AS notify_recovery
                FROM alerts AS alert
                LEFT JOIN alert_delivery_policies AS policy
                  ON policy.alert_id = alert.id
                WHERE alert.enabled = TRUE
            """)
        ).mappings().all()

    triggered_count = 0
    for alert in rows:
        if _check_alert(dict(alert)):
            triggered_count += 1
    process_due_deliveries()
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
