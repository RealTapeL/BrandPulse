"""在可信 scope 快照上执行自定义公式，并保留完整输入证据。

旧 ``brand_indicators_daily`` / ``custom_formula_values`` 没有城市×商场×品类
范围和快照版本，不能支撑正式招商判断。本模块只使用 metric_observations 中
已标记为 valid 的 scope 级指标。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.indicators.formula_engine import FormulaEvaluationError, evaluate_formula
from brandpulse.logger.logger import get_logger
from brandpulse.storage.formula_repository import FormulaRepository
from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

logger = get_logger(__name__)


def _snapshot_context(scope_id: str, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
    """返回一个 ready/published 快照的可用 scope 指标和每个指标的证据。"""
    client = PostgresClient()
    with client.engine.connect() as conn:
        conditions = [
            "snapshot.scope_id = :scope_id",
            "snapshot.status IN ('ready', 'published')",
        ]
        params: Dict[str, Any] = {"scope_id": scope_id}
        if snapshot_id:
            conditions.append("snapshot.snapshot_id = :snapshot_id")
            params["snapshot_id"] = snapshot_id
        snapshot = conn.execute(text(f"""
            SELECT snapshot_id, scope_id, observed_at, quality_grade, freshness_status,
                   data_mode, source_coverage
            FROM data_snapshots AS snapshot
            WHERE {' AND '.join(conditions)}
            ORDER BY observed_at DESC, created_at DESC
            LIMIT 1
        """), params).mappings().first()
        if not snapshot:
            if snapshot_id:
                raise ValueError("指定快照不存在、未属于该范围，或尚未 ready/published")
            raise ValueError("该范围暂无 ready/published 快照，不能计算公式")
        metric_rows = conn.execute(text("""
            SELECT metric_key, value, unit, metric_version, quality_status, evidence,
                   calculated_at
            FROM metric_observations
            WHERE snapshot_id = :snapshot_id
              AND scope_id = :scope_id
              AND entity_type = 'scope'
              AND entity_key = :scope_id
              AND quality_status = 'valid'
              AND value IS NOT NULL
            ORDER BY metric_key, calculated_at DESC
        """), {"snapshot_id": snapshot["snapshot_id"], "scope_id": scope_id}).mappings().all()

    context: Dict[str, float] = {}
    evidence: Dict[str, Any] = {}
    for row in metric_rows:
        # 同一指标可能有不同 source_name；scope 输出优先取最新一条，定义中保留来源证据。
        if row["metric_key"] in context:
            continue
        context[row["metric_key"]] = float(row["value"])
        evidence[row["metric_key"]] = {
            "unit": row["unit"], "metric_version": row["metric_version"],
            "quality_status": row["quality_status"], "calculated_at": str(row["calculated_at"]),
            "metric_evidence": row["evidence"] or {},
        }
    return {"snapshot": dict(snapshot), "context": context, "metric_evidence": evidence}


def compute_custom_formulas(
    *,
    scope_id: str,
    snapshot_id: Optional[str] = None,
    formula_id: Optional[str] = None,
) -> Dict[str, Any]:
    """在一个实际快照上计算启用公式；缺失输入会如实记录为 skipped。"""
    if not TrustedScopeRepository().get(scope_id):
        raise ValueError("监测范围不存在")
    snapshot_context = _snapshot_context(scope_id, snapshot_id)
    snapshot = snapshot_context["snapshot"]
    repo = FormulaRepository()
    formulas = repo.list_enabled()
    if formula_id:
        formulas = [formula for formula in formulas if formula["id"] == formula_id]
    if not formulas:
        return {
            "saved": 0, "skipped": 0, "snapshot_id": snapshot["snapshot_id"],
            "scope_id": scope_id, "evaluations": [],
        }

    evaluations = []
    saved = 0
    skipped = 0
    for formula in formulas:
        params: Dict[str, float] = {}
        failure_reason = ""
        for item in formula.get("params") or []:
            try:
                params[item["key"]] = float(item["value"])
            except (KeyError, TypeError, ValueError):
                failure_reason = f"参数 {item!r} 不是有限数值"
                break
        input_metrics = {**params, **snapshot_context["context"]}
        status = "completed"
        value: Optional[float] = None
        if not failure_reason:
            try:
                value = evaluate_formula(formula["expression"], input_metrics)
            except FormulaEvaluationError as exc:
                status = "skipped"
                failure_reason = str(exc)
        else:
            status = "skipped"

        row = repo.upsert_snapshot_evaluation({
            "formula_id": formula["id"], "scope_id": scope_id,
            "snapshot_id": snapshot["snapshot_id"], "status": status, "value": value,
            "input_metrics": input_metrics,
            "formula_definition": {
                "name": formula["name"], "description": formula.get("description") or "",
                "expression": formula["expression"], "params": formula.get("params") or [],
            },
            "evidence": {
                "snapshot": {
                    "observed_at": str(snapshot["observed_at"]),
                    "quality_grade": snapshot["quality_grade"],
                    "freshness_status": snapshot["freshness_status"],
                    "data_mode": snapshot["data_mode"],
                    "source_coverage": snapshot["source_coverage"],
                },
                "metric_evidence": snapshot_context["metric_evidence"],
            },
            "failure_reason": failure_reason,
        })
        evaluations.append(row)
        if status == "completed":
            saved += 1
        else:
            skipped += 1

    logger.info(
        "[公式] scope=%s snapshot=%s 完成=%s 跳过=%s",
        scope_id, snapshot["snapshot_id"], saved, skipped,
    )
    return {
        "saved": saved, "skipped": skipped, "snapshot_id": snapshot["snapshot_id"],
        "scope_id": scope_id, "evaluations": evaluations,
    }
