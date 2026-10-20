"""预测数据准入检查。

准入检查只读取可信快照和指标观测，不生成任何补齐值。未满足条件时，训练 API
必须拒绝创建训练任务，前端显示缺失周期和具体阻断原因。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


EXTERNAL_REVIEW_TARGET = "dp_review_count_delta"
MIN_COMPARABLE_PERIODS = 12
MIN_SOURCE_COVERAGE = 0.8
MAX_INTERVAL_DAYS = 7


def _json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class ForecastReadinessService:
    """计算并保存一个范围/目标/实体维度的预测准入结果。"""

    def __init__(self):
        self.client = PostgresClient()

    def _load_series(self, conn, scope_id: str, target_metric: str) -> List[Dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT snapshot.snapshot_id, snapshot.observed_at, snapshot.data_mode,
                       snapshot.quality_grade, snapshot.freshness_status,
                       metric.value, metric.quality_status, metric.evidence,
                       coverage.value AS source_coverage
                FROM data_snapshots AS snapshot
                JOIN metric_observations AS metric
                  ON metric.snapshot_id = snapshot.snapshot_id
                 AND metric.scope_id = snapshot.scope_id
                 AND metric.entity_type = 'scope'
                 AND metric.metric_key = :target_metric
                LEFT JOIN metric_observations AS coverage
                  ON coverage.snapshot_id = snapshot.snapshot_id
                 AND coverage.scope_id = snapshot.scope_id
                 AND coverage.entity_type = 'scope'
                 AND coverage.metric_key = 'source_coverage_ratio'
                WHERE snapshot.scope_id = :scope_id
                  AND snapshot.status IN ('ready', 'published')
                ORDER BY snapshot.observed_at ASC, snapshot.created_at ASC
                """
            ),
            {"scope_id": scope_id, "target_metric": target_metric},
        ).mappings().all()

        # 一个业务日只保留最后一个可信快照，避免重复采集把样本量虚增。
        by_day: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if row["value"] is None or row["quality_status"] not in {"valid", "warning"}:
                continue
            evidence = row.get("evidence") or {}
            if isinstance(evidence, str):
                try:
                    evidence = json.loads(evidence)
                except json.JSONDecodeError:
                    evidence = {}
            if evidence.get("reason"):
                continue
            observed_at = row.get("observed_at")
            if observed_at is None:
                continue
            day_key = observed_at.date().isoformat() if hasattr(observed_at, "date") else str(observed_at)[:10]
            by_day[day_key] = {
                "snapshot_id": row["snapshot_id"],
                "observed_at": _json(observed_at),
                "period": day_key,
                "value": float(row["value"]),
                "source_coverage": float(row["source_coverage"]) if row["source_coverage"] is not None else None,
                "data_mode": row["data_mode"],
                "quality_grade": row["quality_grade"],
                "freshness_status": row["freshness_status"],
            }
        return sorted(by_day.values(), key=lambda item: item["period"])

    def check(
        self,
        *,
        scope_id: str,
        target_metric: str = EXTERNAL_REVIEW_TARGET,
        entity_type: str = "scope",
        required_periods: int = MIN_COMPARABLE_PERIODS,
    ) -> Dict[str, Any]:
        if entity_type not in {"scope", "brand", "store"}:
            raise ValueError("预测实体类型不合法")
        with self.client.engine.begin() as conn:
            scope = conn.execute(
                text("SELECT scope_id, city, mall_name, category FROM trusted_monitoring_scopes WHERE scope_id = :scope_id"),
                {"scope_id": scope_id},
            ).mappings().first()
            if not scope:
                raise ValueError("监测范围不存在")
            series = self._load_series(conn, scope_id, target_metric)

            blockers: list[dict[str, str]] = []
            if entity_type != "scope":
                blockers.append({
                    "code": "entity_mapping_required",
                    "message": "品牌/门店预测需要稳定的真实实体映射；当前先只允许范围级预测。",
                })
            if len(series) < required_periods:
                blockers.append({
                    "code": "insufficient_periods",
                    "message": f"当前只有 {len(series)} 个可比较周期，还需要 {required_periods - len(series)} 个周期。",
                })
            low_coverage = [item["period"] for item in series if item["source_coverage"] is None or item["source_coverage"] < MIN_SOURCE_COVERAGE]
            if low_coverage:
                blockers.append({
                    "code": "source_coverage_low",
                    "message": f"{len(low_coverage)} 个周期来源覆盖率低于 {MIN_SOURCE_COVERAGE:.0%}，不能进入训练。",
                })
            gaps: list[str] = []
            intervals: list[float] = []
            for previous, current in zip(series, series[1:]):
                previous_day = date.fromisoformat(previous["period"])
                current_day = date.fromisoformat(current["period"])
                interval = (current_day - previous_day).days
                intervals.append(float(interval))
                if interval > MAX_INTERVAL_DAYS:
                    gaps.append(f"{previous['period']}~{current['period']}")
            if gaps:
                blockers.append({
                    "code": "period_gap",
                    "message": f"存在超过 {MAX_INTERVAL_DAYS} 天的采集间隔，缺失区间：{', '.join(gaps[:5])}。",
                })
            if len({item["data_mode"] for item in series}) > 1:
                blockers.append({
                    "code": "data_mode_changed",
                    "message": "训练窗口内数据模式发生变化，不能直接拼接为同口径时序。",
                })
            if any(current["value"] < 0 for current in series):
                blockers.append({
                    "code": "negative_increment",
                    "message": "新增评价数出现负值，需先处理累计值回退或采集异常。",
                })

            status = "ready" if not blockers else "not_ready"
            latest_snapshot_id = series[-1]["snapshot_id"] if series else None
            result: Dict[str, Any] = {
                "scope": dict(scope),
                "target_metric": target_metric,
                "entity_type": entity_type,
                "status": status,
                "eligible_periods": len(series),
                "required_periods": required_periods,
                "source_coverage": min((item["source_coverage"] for item in series if item["source_coverage"] is not None), default=None),
                "mapping_stability": None if entity_type == "scope" else 0.0,
                "latest_snapshot_id": latest_snapshot_id,
                "missing_periods": gaps,
                "blockers": blockers,
                "series": series,
                "window": {
                    "start": series[0]["period"] if series else None,
                    "end": series[-1]["period"] if series else None,
                    "max_interval_days": max(intervals) if intervals else None,
                },
                "rules": {
                    "minimum_comparable_periods": required_periods,
                    "minimum_source_coverage": MIN_SOURCE_COVERAGE,
                    "maximum_interval_days": MAX_INTERVAL_DAYS,
                    "time_split": "按时间顺序切分，不随机打乱",
                },
            }
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_readiness_checks (
                        check_id, scope_id, target_metric, entity_type, status,
                        eligible_periods, required_periods, source_coverage, mapping_stability,
                        latest_snapshot_id, missing_periods, blockers, details
                    ) VALUES (
                        :check_id, :scope_id, :target_metric, :entity_type, :status,
                        :eligible_periods, :required_periods, :source_coverage, :mapping_stability,
                        :latest_snapshot_id, CAST(:missing_periods AS jsonb), CAST(:blockers AS jsonb), CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "check_id": f"readiness_{uuid4().hex}",
                    "scope_id": scope_id,
                    "target_metric": target_metric,
                    "entity_type": entity_type,
                    "status": status,
                    "eligible_periods": len(series),
                    "required_periods": required_periods,
                    "source_coverage": result["source_coverage"],
                    "mapping_stability": result["mapping_stability"],
                    "latest_snapshot_id": latest_snapshot_id,
                    "missing_periods": json.dumps(result["missing_periods"], ensure_ascii=False),
                    "blockers": json.dumps(blockers, ensure_ascii=False),
                    "details": json.dumps({"series": series, "window": result["window"], "rules": result["rules"]}, ensure_ascii=False, default=str),
                },
            )
        return result

    def latest(self, *, scope_id: str, target_metric: str, entity_type: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM forecast_readiness_checks
                    WHERE scope_id = :scope_id AND target_metric = :target_metric AND entity_type = :entity_type
                    ORDER BY checked_at DESC
                    LIMIT 1
                    """
                ),
                {"scope_id": scope_id, "target_metric": target_metric, "entity_type": entity_type},
            ).mappings().first()
        if not row:
            return None
        result = dict(row)
        for key in ("missing_periods", "blockers", "details"):
            value = result.get(key) or ([] if key != "details" else {})
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            result[key] = value
        if result.get("checked_at") is not None:
            result["checked_at"] = str(result["checked_at"])
        return result
