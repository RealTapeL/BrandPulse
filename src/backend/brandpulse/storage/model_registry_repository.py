"""模型注册、发布和路由台账。"""

from __future__ import annotations

import hashlib
import json
import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


class ModelRegistryRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        item = dict(row)
        for key in ("metrics", "baseline_metrics", "metadata"):
            value = item.get(key) or {}
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            item[key] = value
        for key in ("created_at", "updated_at", "approved_at", "published_at", "retired_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def register_training(
        self,
        *,
        run: Dict[str, Any],
        metadata: Dict[str, Any],
        created_by: str = "system",
    ) -> Dict[str, Any]:
        model_id = str(metadata["model_id"])
        artifact_path = str(Path(metadata["artifacts"]["model"]).parent)
        model_path = Path(metadata["artifacts"]["model"])
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest() if model_path.is_file() else ""
        validation = metadata.get("validation") or {}
        metrics = validation.get("metrics") or {}
        baseline_metrics = validation.get("baseline_metrics") or {}
        status = "evaluated" if validation.get("beats_baseline") is not False else "trained"
        target_metric = str(metadata.get("target_metric") or metadata.get("target") or run.get("task") or "unknown")
        scope_id = metadata.get("scope_id")
        entity_type = str(metadata.get("entity_type") or "scope")
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO model_registry (
                        model_version_id, model_id, run_id, scope_id, target_metric, entity_type,
                        task, model_family, status, data_origin, production_eligible, feature_version,
                        input_snapshot_id, artifact_path, artifact_sha256, metrics, baseline_metrics,
                        metadata, created_by
                    ) VALUES (
                        :model_version_id, :model_id, :run_id, :scope_id, :target_metric, :entity_type,
                        :task, :model_family, :status, :data_origin, :production_eligible, :feature_version,
                        :input_snapshot_id, :artifact_path, :artifact_sha256, CAST(:metrics AS jsonb),
                        CAST(:baseline_metrics AS jsonb), CAST(:metadata AS jsonb), :created_by
                    )
                    ON CONFLICT (model_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        scope_id = EXCLUDED.scope_id,
                        target_metric = EXCLUDED.target_metric,
                        entity_type = EXCLUDED.entity_type,
                        status = EXCLUDED.status,
                        artifact_path = EXCLUDED.artifact_path,
                        artifact_sha256 = EXCLUDED.artifact_sha256,
                        metrics = EXCLUDED.metrics,
                        baseline_metrics = EXCLUDED.baseline_metrics,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """
                ),
                {
                    "model_version_id": f"model_version_{uuid4().hex}",
                    "model_id": model_id,
                    "run_id": run.get("run_id"),
                    "scope_id": scope_id,
                    "target_metric": target_metric,
                    "entity_type": entity_type,
                    "task": str(metadata.get("task") or run.get("task") or ""),
                    "model_family": str(metadata.get("algorithm") or "unknown"),
                    "status": status,
                    "data_origin": str(metadata.get("data_origin") or run.get("data_origin") or "unknown"),
                    "production_eligible": bool(metadata.get("production_eligible", run.get("production_eligible", False))),
                    "feature_version": str(metadata.get("feature_version") or ""),
                    "input_snapshot_id": metadata.get("input_snapshot_id"),
                    "artifact_path": artifact_path,
                    "artifact_sha256": digest,
                    "metrics": _json(metrics),
                    "baseline_metrics": _json(baseline_metrics),
                    "metadata": _json(metadata),
                    "created_by": created_by,
                },
            ).mappings().one()
        return self._row(row) or {}

    def list(self, *, scope_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 200)}
        if scope_id:
            conditions.append("scope_id = :scope_id")
            params["scope_id"] = scope_id
        if status:
            conditions.append("status = :status")
            params["status"] = status
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT * FROM model_registry WHERE {' AND '.join(conditions)} "
                    "ORDER BY updated_at DESC LIMIT :limit"
                ),
                params,
            ).mappings().all()
        return [self._row(row) for row in rows if row]

    def get(self, model_version_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM model_registry WHERE model_version_id = :model_version_id"),
                {"model_version_id": model_version_id},
            ).mappings().first()
        return self._row(row)

    def publish(self, model_version_id: str, *, actor_id: str) -> Dict[str, Any]:
        with self.client.engine.begin() as conn:
            candidate = conn.execute(
                text("SELECT * FROM model_registry WHERE model_version_id = :model_version_id FOR UPDATE"),
                {"model_version_id": model_version_id},
            ).mappings().first()
            if not candidate:
                raise ValueError("模型版本不存在")
            if candidate["status"] not in {"evaluated", "pending_approval", "degraded"}:
                raise ValueError("只有已评估、待审批或降级模型可以发布")
            if candidate["status"] == "evaluated" and candidate["baseline_metrics"] in (None, {}):
                raise ValueError("模型缺少朴素基线评估，不允许发布")
            conn.execute(
                text(
                    """
                    UPDATE model_registry
                    SET status = 'retired', retired_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE target_metric = :target_metric
                      AND entity_type = :entity_type
                      AND scope_id IS NOT DISTINCT FROM :scope_id
                      AND status IN ('published', 'monitoring')
                      AND model_version_id <> :model_version_id
                    """
                ),
                {
                    "target_metric": candidate["target_metric"],
                    "entity_type": candidate["entity_type"],
                    "scope_id": candidate["scope_id"],
                    "model_version_id": model_version_id,
                },
            )
            row = conn.execute(
                text(
                    """
                    UPDATE model_registry
                    SET status = 'monitoring', approved_by = :actor_id, approved_at = CURRENT_TIMESTAMP,
                        published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE model_version_id = :model_version_id
                    RETURNING *
                    """
                ),
                {"model_version_id": model_version_id, "actor_id": actor_id},
            ).mappings().one()
            conn.execute(
                text(
                    """
                    INSERT INTO model_routes (
                        route_id, scope_id, target_metric, entity_type, model_version_id, status, created_by
                    ) VALUES (
                        :route_id, :scope_id, :target_metric, :entity_type, :model_version_id, 'active', :created_by
                    )
                    ON CONFLICT (scope_id, target_metric, entity_type) DO UPDATE SET
                        model_version_id = EXCLUDED.model_version_id,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "route_id": f"route_{uuid4().hex}",
                    "scope_id": candidate["scope_id"],
                    "target_metric": candidate["target_metric"],
                    "entity_type": candidate["entity_type"],
                    "model_version_id": model_version_id,
                    "created_by": actor_id,
                },
            )
        return self._row(row) or {}

    def retire(self, model_version_id: str, *, actor_id: str) -> Dict[str, Any]:
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE model_registry
                    SET status = 'retired', retired_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE model_version_id = :model_version_id
                      AND status NOT IN ('retired', 'archived')
                    RETURNING *
                    """
                ),
                {"model_version_id": model_version_id},
            ).mappings().first()
            if not row:
                raise ValueError("模型版本不存在或已归档")
            conn.execute(
                text(
                    """
                    UPDATE model_routes
                    SET status = 'disabled', updated_at = CURRENT_TIMESTAMP
                    WHERE model_version_id = :model_version_id
                    """
                ),
                {"model_version_id": model_version_id},
            )
        return self._row(row) or {}

    def active_route(self, *, scope_id: str, target_metric: str, entity_type: str = "scope") -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT route.*, model.status AS model_status, model.model_id, model.artifact_path,
                           model.metrics, model.baseline_metrics, model.metadata
                    FROM model_routes AS route
                    JOIN model_registry AS model ON model.model_version_id = route.model_version_id
                    WHERE route.scope_id = :scope_id
                      AND route.target_metric = :target_metric
                      AND route.entity_type = :entity_type
                      AND route.status = 'active'
                    """
                ),
                {"scope_id": scope_id, "target_metric": target_metric, "entity_type": entity_type},
            ).mappings().first()
        return self._row(row)

    def record_forecasts(self, *, model_version_id: str, metadata: Dict[str, Any]) -> int:
        scope_id = metadata.get("scope_id")
        forecast_path = Path((metadata.get("artifacts") or {}).get("forecast") or "")
        if not scope_id or not forecast_path.is_file():
            return 0
        target_metric = str(metadata.get("target_metric") or metadata.get("target") or "")
        input_snapshot_id = metadata.get("input_snapshot_id")
        written = 0
        with forecast_path.open("r", encoding="utf-8", newline="") as handle, self.client.engine.begin() as conn:
            for row in csv.DictReader(handle):
                conn.execute(
                    text(
                        """
                        INSERT INTO forecast_results (
                            forecast_id, model_version_id, scope_id, input_snapshot_id, target_metric,
                            entity_type, entity_key, forecast_date, point_forecast, lower_bound,
                            upper_bound, quality
                        ) VALUES (
                            :forecast_id, :model_version_id, :scope_id, :input_snapshot_id, :target_metric,
                            :entity_type, :entity_key, :forecast_date, :point_forecast, :lower_bound,
                            :upper_bound, CAST(:quality AS jsonb)
                        )
                        ON CONFLICT (model_version_id, entity_type, entity_key, forecast_date) DO UPDATE SET
                            point_forecast = EXCLUDED.point_forecast,
                            lower_bound = EXCLUDED.lower_bound,
                            upper_bound = EXCLUDED.upper_bound,
                            input_snapshot_id = EXCLUDED.input_snapshot_id,
                            quality = EXCLUDED.quality,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "forecast_id": f"forecast_{uuid4().hex}",
                        "model_version_id": model_version_id,
                        "scope_id": scope_id,
                        "input_snapshot_id": input_snapshot_id,
                        "target_metric": target_metric,
                        "entity_type": row.get("entity_type") or str(metadata.get("entity_type") or "scope"),
                        "entity_key": row.get("entity_key") or str(scope_id),
                        "forecast_date": row.get("forecast_date") or row.get("date"),
                        "point_forecast": row.get("predicted_value") or row.get("predicted_sales"),
                        "lower_bound": row.get("lower_bound"),
                        "upper_bound": row.get("upper_bound"),
                        "quality": _json({
                            "data_origin": metadata.get("data_origin"),
                            "input_snapshot_id": input_snapshot_id,
                            "model_id": metadata.get("model_id"),
                        }),
                    },
                )
                written += 1
        return written

    def monitoring(self, model_version_id: str) -> Dict[str, Any]:
        with self.client.engine.begin() as conn:
            model = conn.execute(
                text("SELECT * FROM model_registry WHERE model_version_id = :model_version_id"),
                {"model_version_id": model_version_id},
            ).mappings().first()
            if not model:
                raise ValueError("模型版本不存在")
            # 用同一 scope、同一指标的后续可信快照回填已到期预测，保持快照可追溯。
            conn.execute(
                text(
                    """
                    UPDATE forecast_results AS forecast
                    SET actual_value = metric.value,
                        status = 'observed',
                        updated_at = CURRENT_TIMESTAMP
                    FROM metric_observations AS metric
                    JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = metric.snapshot_id
                    WHERE forecast.model_version_id = :model_version_id
                      AND forecast.actual_value IS NULL
                      AND forecast.forecast_date <= CURRENT_DATE
                      AND metric.scope_id = forecast.scope_id
                      AND metric.entity_type = 'scope'
                      AND metric.metric_key = forecast.target_metric
                      AND snapshot.status IN ('ready', 'published')
                      AND snapshot.observed_at::date = forecast.forecast_date
                    """
                ),
                {"model_version_id": model_version_id},
            )
            rows = conn.execute(
                text(
                    """
                    SELECT forecast_date, point_forecast, lower_bound, upper_bound, actual_value,
                           input_snapshot_id, status
                    FROM forecast_results
                    WHERE model_version_id = :model_version_id
                    ORDER BY forecast_date
                    """
                ),
                {"model_version_id": model_version_id},
            ).mappings().all()
            observed = [row for row in rows if row["actual_value"] is not None and row["point_forecast"] is not None]
            metrics: Dict[str, Any] = {"observed_periods": len(observed)}
            if observed:
                errors = [float(row["point_forecast"]) - float(row["actual_value"]) for row in observed]
                denominator = sum(abs(float(row["actual_value"])) for row in observed)
                metrics.update({
                    "mae": sum(abs(error) for error in errors) / len(errors),
                    "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
                    "wape": sum(abs(error) for error in errors) / denominator if denominator else 0.0,
                })
            baseline = model["baseline_metrics"] or {}
            degraded = (
                len(observed) >= 3
                and baseline.get("wape") is not None
                and metrics.get("wape") is not None
                and float(metrics["wape"]) > float(baseline["wape"]) * 1.2
            )
            if degraded and model["status"] == "monitoring":
                conn.execute(
                    text(
                        """
                        UPDATE model_registry
                        SET status = 'degraded', updated_at = CURRENT_TIMESTAMP
                        WHERE model_version_id = :model_version_id
                        """
                    ),
                    {"model_version_id": model_version_id},
                )
            return {
                "model_version_id": model_version_id,
                "status": "degraded" if degraded else model["status"],
                "metrics": metrics,
                "baseline_metrics": baseline,
                "rows": [dict(row) for row in rows],
                "warning": "实际值尚未回填，暂不计算滚动误差" if not observed else "",
            }
