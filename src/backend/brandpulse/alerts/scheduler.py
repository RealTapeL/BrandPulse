"""
告警调度器（APScheduler）：每 5 分钟检查所有启用的告警规则。

提供 start_scheduler() / shutdown_scheduler()，由独立 runner 进程调用；FastAPI 不再持有调度器。
"""
from typing import Any, Dict, Optional

from sqlalchemy import text

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from brandpulse.alerts.service import process_due_deliveries, record_evaluation
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _fetch_metric_evidence(metric: str, scope_id: str) -> Optional[Dict[str, Any]]:
    """读取同一可信范围的最新快照事实，并返回可以追溯的指标证据。

    不回退到旧 ``brand_id`` 聚合、热度或 SOV 表。找不到 ready/published 快照或
    合格的快照指标时返回 ``None``，由状态机记录“暂无可用指标值”而不是猜测补值。
    """
    if metric not in {
        "data_freshness_hours",
        "dp_review_count_stock",
        "source_coverage_ratio",
        "entity_mapping_coverage",
    }:
        return None

    freshness_sql = """
        SELECT snapshot.snapshot_id, snapshot.observed_at, snapshot.quality_grade,
               snapshot.freshness_status, snapshot.source_coverage,
               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - snapshot.observed_at)) / 3600.0 AS value
        FROM data_snapshots AS snapshot
        WHERE snapshot.scope_id = :scope_id
          AND snapshot.status IN ('ready', 'published')
          AND snapshot.observed_at IS NOT NULL
        ORDER BY snapshot.observed_at DESC, snapshot.created_at DESC
        LIMIT 1
    """
    metric_sql = """
        SELECT observation.value, observation.metric_key, observation.metric_version,
               observation.quality_status, observation.unit, observation.evidence,
               observation.calculated_at, snapshot.snapshot_id, snapshot.observed_at,
               snapshot.quality_grade, snapshot.freshness_status, snapshot.source_coverage
        FROM metric_observations AS observation
        JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = observation.snapshot_id
        WHERE observation.scope_id = :scope_id
          AND observation.metric_key = :metric_key
          AND observation.entity_type = 'scope'
          AND observation.entity_key = :scope_id
          AND observation.quality_status = 'valid'
          AND observation.value IS NOT NULL
          AND snapshot.status IN ('ready', 'published')
        ORDER BY snapshot.observed_at DESC, observation.calculated_at DESC
        LIMIT 1
    """
    try:
        client = PostgresClient()
        with client.engine.connect() as conn:
            if metric == "data_freshness_hours":
                row = conn.execute(text(freshness_sql), {"scope_id": scope_id}).mappings().first()
                if not row or row["value"] is None:
                    return None
                return {
                    "value": float(row["value"]),
                    "scope_id": scope_id,
                    "snapshot_id": row["snapshot_id"],
                    "metric_key": metric,
                    "metric_quality": "valid",
                    "evidence": {
                        "source": "data_snapshots",
                        "observed_at": str(row["observed_at"]),
                        "quality_grade": row["quality_grade"],
                        "freshness_status": row["freshness_status"],
                        "source_coverage": row["source_coverage"],
                    },
                }
            row = conn.execute(
                text(metric_sql), {"scope_id": scope_id, "metric_key": metric}
            ).mappings().first()
            if not row:
                return None
            return {
                "value": float(row["value"]),
                "scope_id": scope_id,
                "snapshot_id": row["snapshot_id"],
                "metric_key": row["metric_key"],
                "metric_quality": row["quality_status"],
                "evidence": {
                    "source": "metric_observations",
                    "unit": row["unit"],
                    "metric_version": row["metric_version"],
                    "calculated_at": str(row["calculated_at"]),
                    "observed_at": str(row["observed_at"]),
                    "quality_grade": row["quality_grade"],
                    "freshness_status": row["freshness_status"],
                    "source_coverage": row["source_coverage"],
                    "metric_evidence": row["evidence"] or {},
                },
            }
    except Exception as exc:
        logger.error("[scheduler] 查询可信快照指标 %s 失败: %s", metric, exc)
        return None


def _fetch_metric_value(
    metric: str,
    brand_id: Optional[str] = None,
    scope_id: Optional[str] = None,
) -> Optional[float]:
    """兼容旧内部调用签名；brand_id 不再参与可信告警的指标查询。"""
    del brand_id
    evidence = _fetch_metric_evidence(metric, scope_id) if scope_id else None
    return evidence["value"] if evidence else None


def _check_operator(value: float, op: str, threshold: float) -> bool:
    return {
        ">": value > threshold,
        "<": value < threshold,
        "=": value == threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
    }.get(op, False)


def _check_alert(alert: dict) -> bool:
    # API 响应保留 metric 字段；调度 SQL 额外带 metric_key。两者在可信规则中相同。
    metric_key = alert.get("metric_key", alert["metric"])
    evidence = _fetch_metric_evidence(metric_key, alert["scope_id"])
    value = evidence["value"] if evidence else None
    if evidence:
        # record_evaluation 会把该证据与生成的 alert_history 绑定，避免后续快照覆盖原判断依据。
        alert["metric_evidence"] = evidence
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
        rows = conn.execute(
            text("""
                SELECT alert.*,
                       COALESCE(policy.cooldown_minutes, 60) AS cooldown_minutes,
                       COALESCE(policy.notify_recovery, TRUE) AS notify_recovery,
                       trusted_rule.scope_id,
                       trusted_rule.metric_key
                FROM alerts AS alert
                JOIN trusted_alert_rules AS trusted_rule ON trusted_rule.alert_id = alert.id
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
