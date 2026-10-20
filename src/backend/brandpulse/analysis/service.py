"""Phase 2/3 统一分析查询服务。

分析服务只消费可信范围的 ready/published 快照、快照指标和已接受的原始观测。
它不回退到旧日指标表，不把未确认映射的记录归因给品牌，也不把来源缺失补成 0。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository


DEFAULT_OVERVIEW_METRICS = (
    "dp_review_count_stock",
    "dp_store_count_observed",
    "xhs_content_count_observed",
    "xhs_likes_stock",
    "bayesian_reputation",
    "source_coverage_ratio",
    "entity_mapping_coverage",
    "dp_review_count_growth_rate",
)
DEFAULT_TREND_METRIC = "dp_review_count_stock"
RELEASED_STATUSES = ("ready", "published")
MAX_COMPARABLE_INTERVAL_DAYS = 7


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ")
        except TypeError:
            return value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    return str(value)


def parse_brand_ids(value: Optional[str | Iterable[str]]) -> list[str]:
    """解析逗号分隔的品牌筛选，最多保留 5 个唯一 ID。"""
    if value is None:
        return []
    values = value.split(",") if isinstance(value, str) else value
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))[:5]


class AnalysisService:
    def __init__(self):
        self.client = PostgresClient()
        self.scopes = TrustedScopeRepository()
        self.snapshots = SnapshotRepository()

    def _query(self, sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        with self.client.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def resolve(self, scope_id: str, snapshot_id: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        scope = self.scopes.get(scope_id)
        if not scope:
            raise ValueError("监测范围不存在")
        snapshot = self.snapshots.get(snapshot_id) if snapshot_id else self.snapshots.latest_released(scope_id)
        if not snapshot:
            raise ValueError("当前范围没有 ready 或 published 可信快照")
        if snapshot.get("scope_id") != scope_id:
            raise ValueError("数据快照不属于当前监测范围")
        if snapshot.get("status") not in RELEASED_STATUSES:
            raise ValueError("只有 ready/published 快照可以用于分析")
        return scope, snapshot

    def metric_catalog(self) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT metric_key, display_name, metric_group, description, unit, source_scope,
                   window_rule, metric_version, formula, comparison_scope,
                   minimum_sample_size, quality_requirements, allow_alert, allow_prediction,
                   is_active
            FROM metric_definitions
            WHERE is_active = TRUE
            ORDER BY CASE metric_group
                WHEN 'stock' THEN 1 WHEN 'activity' THEN 2 WHEN 'quality' THEN 3
                WHEN 'competition' THEN 4 WHEN 'trend' THEN 5 ELSE 9 END, metric_key
            """
        )
        catalog = [_jsonable(row) for row in rows]
        formula_rows = self._query(
            """
            SELECT formula_id, name, description, expression, params, enabled
            FROM custom_formulas
            WHERE enabled = TRUE
            ORDER BY name, formula_id
            """
        )
        catalog.extend(_jsonable({
            "metric_key": f"formula:{row['formula_id']}",
            "display_name": row["name"],
            "metric_group": "custom",
            "description": row.get("description") or "自定义公式；必须绑定范围和快照后才有值。",
            "unit": "",
            "source_scope": "当前范围 · 当前快照",
            "window_rule": "当前快照",
            "metric_version": "custom-formula",
            "formula": row.get("expression") or "",
            "comparison_scope": "same scope × same snapshot",
            "minimum_sample_size": 0,
            "quality_requirements": {"requires_snapshot_evaluation": True},
            "allow_alert": False,
            "allow_prediction": False,
            "is_active": bool(row.get("enabled")),
            "formula_id": row["formula_id"],
            "params": row.get("params") or [],
        }) for row in formula_rows)
        return catalog

    def _definitions(self) -> dict[str, dict[str, Any]]:
        return {str(row["metric_key"]): row for row in self.metric_catalog()}

    def _metric_values(self, snapshot_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = self._query(
            """
            SELECT snapshot_id, metric_key, entity_type, entity_key, brand_id, store_id, source_name,
                   time_window_days, value, unit, quality_status, baseline_scope,
                   baseline_level, sample_size, parameters, evidence, calculated_at
            FROM metric_observations
            WHERE snapshot_id = :snapshot_id
            ORDER BY metric_key, calculated_at DESC
            """,
            {"snapshot_id": snapshot_id},
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["metric_key"]), []).append(_jsonable(row))
        return grouped

    def _custom_metric_values(self, snapshot_id: str, scope_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = self._query(
            """
            SELECT evaluation.snapshot_id, evaluation.formula_id,
                   evaluation.value, evaluation.status, evaluation.input_metrics,
                   evaluation.formula_definition, evaluation.evidence,
                   evaluation.evaluated_at
            FROM snapshot_formula_evaluations AS evaluation
            WHERE evaluation.snapshot_id = :snapshot_id
              AND evaluation.scope_id = :scope_id
            ORDER BY evaluation.evaluated_at DESC
            """,
            {"snapshot_id": snapshot_id, "scope_id": scope_id},
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = {
                "snapshot_id": row["snapshot_id"],
                "metric_key": f"formula:{row['formula_id']}",
                "entity_type": "scope",
                "entity_key": scope_id,
                "source_name": "custom_formula",
                "value": row["value"] if row["status"] == "completed" else None,
                "unit": "",
                "quality_status": "valid" if row["status"] == "completed" else row["status"],
                "sample_size": None,
                "parameters": row["input_metrics"] or {},
                "evidence": {
                    "formula_definition": row["formula_definition"] or {},
                    **(row["evidence"] or {}),
                },
            }
            grouped.setdefault(item["metric_key"], []).append(_jsonable(item))
        return grouped

    @staticmethod
    def _metric_item(
        key: str,
        definition: Optional[dict[str, Any]],
        values: list[dict[str, Any]],
        *,
        entity_type: Optional[str] = None,
        entity_key: Optional[str] = None,
    ) -> dict[str, Any]:
        candidates = values
        if entity_type is not None:
            candidates = [row for row in candidates if row.get("entity_type") == entity_type]
        if entity_key is not None:
            candidates = [row for row in candidates if str(row.get("entity_key")) == str(entity_key)]
        value = candidates[0] if candidates else None
        item = {
            "metric_key": key,
            "display_name": (definition or {}).get("display_name", key),
            "metric_group": (definition or {}).get("metric_group", ""),
            "description": (definition or {}).get("description", ""),
            "formula": (definition or {}).get("formula", ""),
            "unit": (definition or {}).get("unit", ""),
            "source_scope": (definition or {}).get("source_scope", ""),
            "window_rule": (definition or {}).get("window_rule", ""),
            "comparison_scope": (definition or {}).get("comparison_scope", ""),
            "metric_version": (definition or {}).get("metric_version", ""),
            "minimum_sample_size": (definition or {}).get("minimum_sample_size", 0),
            "quality_requirements": (definition or {}).get("quality_requirements", {}),
            "allow_alert": bool((definition or {}).get("allow_alert", False)),
            "allow_prediction": bool((definition or {}).get("allow_prediction", False)),
            "available": bool(value and value.get("value") is not None),
            "value": value.get("value") if value else None,
            "quality_status": value.get("quality_status") if value else "unavailable",
            "sample_size": value.get("sample_size") if value else None,
            "source_name": value.get("source_name") if value else None,
            "evidence": value.get("evidence") if value else {},
            "parameters": value.get("parameters") if value else {},
            "snapshot_id": value.get("snapshot_id") if value else None,
        }
        return _jsonable(item)

    def _quality(self, snapshot: dict[str, Any], values: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        coverage = snapshot.get("source_coverage") or {}
        sources = coverage.get("sources") or snapshot.get("source_results") or []
        warnings: list[str] = []
        for source in sources:
            status = source.get("status")
            if status in {"failed", "skipped", "stale"}:
                warnings.append(f"{source.get('source_name', '未知来源')}：{status}，该来源未按 0 参与指标")
            if status == "empty_validated":
                warnings.append(f"{source.get('source_name', '未知来源')}：已验证为空，不等同于有 0 条业务数据")
        if snapshot.get("quality_grade") in {"C", "D", "F"}:
            warnings.append(f"当前快照质量等级为 {snapshot.get('quality_grade')}，结论需谨慎使用")
        if snapshot.get("freshness_status") == "stale":
            warnings.append("当前快照已过期，不作为最新业务状态")
        mapping = (values.get("entity_mapping_coverage") or [{}])[0]
        if mapping.get("value") is None or mapping.get("value") == 0:
            warnings.append("当前快照没有已确认的品牌/门店实体映射，品牌排名和品牌对比不可用")
        return {
            "grade": snapshot.get("quality_grade", "unrated"),
            "freshness_status": snapshot.get("freshness_status", "unknown"),
            "source_coverage": coverage,
            "mapping_coverage": mapping.get("value"),
            "warnings": warnings,
        }

    def _brand_rows(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT raw.brand_id, brand.brand_name_cn AS brand_name,
                   COUNT(DISTINCT raw.store_id) AS store_count,
                   COUNT(*) AS observation_count,
                   SUM(NULLIF(raw.payload ->> 'review_count', '')::numeric) AS review_count,
                   AVG(NULLIF(raw.payload ->> 'score', '')::numeric) AS average_score,
                   AVG(metric.value) FILTER (WHERE metric.metric_key = 'bayesian_reputation') AS weighted_score,
                   SUM(NULLIF(raw.payload ->> 'review_count', '')::numeric)
                       / NULLIF(SUM(SUM(NULLIF(raw.payload ->> 'review_count', '')::numeric)) OVER (), 0) AS review_share
            FROM raw_observations AS raw
            JOIN brands AS brand ON brand.brand_id = raw.brand_id
            LEFT JOIN metric_observations AS metric
              ON metric.snapshot_id = :snapshot_id
             AND metric.entity_type = 'shop'
             AND metric.entity_key = raw.source_record_key
             AND metric.metric_key = 'bayesian_reputation'
             AND metric.quality_status IN ('valid', 'partial')
            WHERE raw.scope_id = :scope_id
              AND raw.collection_run_id = :collection_run_id
              AND raw.source_name = 'dianping_webbridge'
              AND raw.record_type = 'dp_shop_metric'
              AND raw.quality_status = 'accepted'
              AND raw.entity_mapping_status = 'confirmed'
              AND raw.brand_id IS NOT NULL
            GROUP BY raw.brand_id, brand.brand_name_cn
            ORDER BY weighted_score DESC NULLS LAST, review_count DESC NULLS LAST, brand.brand_name_cn
            """,
            {
                "snapshot_id": snapshot["snapshot_id"],
                "scope_id": snapshot["scope_id"],
                "collection_run_id": snapshot["collection_run_id"],
            },
        )
        xhs_status = next(
            (item.get("status") for item in (snapshot.get("source_results") or []) if item.get("source_name") == "xiaohongshu_webbridge"),
            None,
        )
        if xhs_status == "success":
            xhs_rows = self._query(
                """
                SELECT brand_id, COUNT(*) AS content_count,
                       SUM(NULLIF(payload ->> 'likes', '')::numeric) AS interaction_count
                FROM raw_observations
                WHERE scope_id = :scope_id AND collection_run_id = :collection_run_id
                  AND source_name = 'xiaohongshu_webbridge' AND record_type = 'xhs_note'
                  AND quality_status = 'accepted' AND entity_mapping_status = 'confirmed'
                  AND brand_id IS NOT NULL
                GROUP BY brand_id
                """,
                {"scope_id": snapshot["scope_id"], "collection_run_id": snapshot["collection_run_id"]},
            )
            xhs_by_brand = {str(row["brand_id"]): row for row in xhs_rows}
        else:
            xhs_by_brand = {}
        for row in rows:
            xhs = xhs_by_brand.get(str(row["brand_id"]))
            row["content_count"] = xhs.get("content_count") if xhs else None
            row["interaction_count"] = xhs.get("interaction_count") if xhs else None
            row["sources"] = ["dianping_webbridge"] + (["xiaohongshu_webbridge"] if xhs_status == "success" else [])
            row["data_quality"] = "valid" if xhs_status in {"success", None} else "partial"
        return [_jsonable(row) for row in rows]

    def _trend(self, scope_id: str, metric_key: str, limit: int) -> dict[str, Any]:
        definition = self._definitions().get(metric_key)
        if metric_key.startswith("formula:"):
            rows = self._query(
                """
                SELECT evaluation.snapshot_id, snapshot.observed_at, snapshot.quality_grade,
                       snapshot.freshness_status, snapshot.data_mode, snapshot.source_coverage,
                       CASE WHEN evaluation.status = 'completed' THEN evaluation.value ELSE NULL END AS value,
                       '' AS unit,
                       CASE WHEN evaluation.status = 'completed' THEN 'valid' ELSE evaluation.status END AS quality_status,
                       'custom_formula' AS source_name, NULL AS sample_size, evaluation.evidence
                FROM snapshot_formula_evaluations AS evaluation
                JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = evaluation.snapshot_id
                WHERE evaluation.scope_id = :scope_id
                  AND evaluation.formula_id = :formula_id
                  AND snapshot.status IN ('ready', 'published')
                ORDER BY snapshot.observed_at ASC, snapshot.created_at ASC
                LIMIT :limit
                """,
                {"scope_id": scope_id, "formula_id": metric_key.split(":", 1)[1], "limit": max(limit, 2)},
            )
        else:
            rows = self._query(
                """
                SELECT observation.snapshot_id, snapshot.observed_at, snapshot.quality_grade,
                       snapshot.freshness_status, snapshot.data_mode, snapshot.source_coverage,
                       observation.value, observation.unit,
                       observation.quality_status, observation.source_name, observation.sample_size,
                       observation.evidence
                FROM metric_observations AS observation
                JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = observation.snapshot_id
                WHERE observation.scope_id = :scope_id
                  AND observation.metric_key = :metric_key
                  AND observation.entity_type = 'scope'
                  AND snapshot.status IN ('ready', 'published')
                ORDER BY snapshot.observed_at ASC, snapshot.created_at ASC
                LIMIT :limit
                """,
                {"scope_id": scope_id, "metric_key": metric_key, "limit": max(limit, 2)},
            )
        series = [_jsonable(row) for row in rows]
        valid = [row for row in series if row.get("value") is not None and row.get("quality_status") == "valid"]
        warnings: list[str] = []
        if len(valid) < 2:
            warnings.append("当前指标少于两个可比较快照，不能输出趋势结论")
        comparison: dict[str, Any] = {"available": False, "reason": warnings[0] if warnings else ""}
        if len(valid) >= 2:
            previous, current = valid[-2], valid[-1]
            previous_value = float(previous["value"])
            current_value = float(current["value"])
            delta = current_value - previous_value
            try:
                previous_at = datetime.fromisoformat(str(previous["observed_at"]).replace("Z", "+00:00"))
                current_at = datetime.fromisoformat(str(current["observed_at"]).replace("Z", "+00:00"))
                interval_days = (current_at - previous_at).total_seconds() / 86400
            except (TypeError, ValueError):
                interval_days = 0
            current_sources = {item.get("source_name"): item.get("status") for item in (current.get("source_coverage") or {}).get("sources", [])}
            previous_sources = {item.get("source_name"): item.get("status") for item in (previous.get("source_coverage") or {}).get("sources", [])}
            comparable = (
                0 < interval_days <= MAX_COMPARABLE_INTERVAL_DAYS
                and current.get("data_mode") == previous.get("data_mode")
                and current.get("source_name") == previous.get("source_name")
                and (
                    metric_key.startswith("formula:")
                    or not current_sources
                    or not current.get("source_name")
                    or current_sources.get(current.get("source_name")) == "success"
                )
                and (
                    metric_key.startswith("formula:")
                    or not previous_sources
                    or not previous.get("source_name")
                    or previous_sources.get(previous.get("source_name")) == "success"
                )
                and (metric_key not in {"dp_review_count_stock", "dp_store_count_observed"} or current_value >= previous_value)
            )
            if not comparable:
                reason = "采集间隔、来源状态、数据模式或累计值变化不满足可比条件；不输出趋势结论"
                warnings.append(reason)
            comparison = {
                "available": comparable,
                "previous_snapshot_id": previous["snapshot_id"],
                "current_snapshot_id": current["snapshot_id"],
                "previous_value": previous_value,
                "current_value": current_value,
                "delta": delta if comparable else None,
                "growth_rate": (delta / previous_value) if comparable and previous_value else None,
                "interval_days": round(interval_days, 4),
                "interpretation": "指标事实变化；未证明因果关系" if comparable else reason,
            }
        return {
            "metric": self._metric_item(metric_key, definition, [], entity_type="scope"),
            "series": series,
            "comparison": _jsonable(comparison),
            "trend_available": bool(comparison.get("available")),
            "warnings": warnings,
        }

    def evidence(
        self,
        snapshot: dict[str, Any],
        *,
        brand_id: Optional[str] = None,
        source_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT :snapshot_id AS snapshot_id, observation_id, source_name, record_type, source_record_key, source_url,
                   observed_date, captured_at, raw_category, standard_category,
                   category_mapping_status, brand_id, store_id, entity_mapping_status,
                   mapping_confidence, quality_status, payload
            FROM raw_observations
            WHERE scope_id = :scope_id AND collection_run_id = :collection_run_id
              AND (:brand_id IS NULL OR brand_id = :brand_id)
              AND (:source_name IS NULL OR source_name = :source_name)
            ORDER BY observed_date DESC, captured_at DESC, observation_id
            LIMIT :limit
            """,
            {
                "scope_id": snapshot["scope_id"],
                "collection_run_id": snapshot["collection_run_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "brand_id": brand_id,
                "source_name": source_name,
                "limit": max(1, min(limit, 200)),
            },
        )
        return [_jsonable(row) for row in rows]

    def query(
        self,
        *,
        scope_id: str,
        view: str = "overview",
        snapshot_id: Optional[str] = None,
        metric_key: str = DEFAULT_TREND_METRIC,
        brand_ids: Optional[Iterable[str] | str] = None,
        source_name: Optional[str] = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        scope, snapshot = self.resolve(scope_id, snapshot_id)
        definitions = self._definitions()
        values = self._metric_values(snapshot["snapshot_id"])
        values.update(self._custom_metric_values(snapshot["snapshot_id"], scope_id))
        quality = self._quality(snapshot, values)
        selected_brands = parse_brand_ids(brand_ids)
        warnings = list(quality["warnings"])
        ranking = self._brand_rows(snapshot)
        if selected_brands:
            found = {str(row["brand_id"]) for row in ranking}
            missing = [brand_id for brand_id in selected_brands if brand_id not in found]
            if missing:
                warnings.append("以下品牌在当前快照没有已确认的可比观测：" + ", ".join(missing))
            ranking = [row for row in ranking if str(row["brand_id"]) in selected_brands]

        metrics = [
            self._metric_item(key, definitions.get(key), values.get(key, []), entity_type="scope", entity_key=scope_id)
            for key in DEFAULT_OVERVIEW_METRICS
        ]
        trend = self._trend(scope_id, metric_key, limit)
        trend["metric"] = self._metric_item(
            metric_key,
            definitions.get(metric_key),
            values.get(metric_key, []),
            entity_type="scope",
            entity_key=scope_id,
        )
        warnings.extend(trend["warnings"] if view in {"overview", "trend"} else [])
        raw_evidence = self.evidence(
            snapshot,
            brand_id=selected_brands[0] if len(selected_brands) == 1 else None,
            source_name=source_name,
            limit=min(limit, 100),
        ) if view in {"overview", "evidence"} else []

        result = {
            "scope": _jsonable({
                "scope_id": scope["scope_id"], "city": scope["city"],
                "mall_name": scope["mall_name"], "category": scope["category"],
            }),
            "snapshot": _jsonable({
                "snapshot_id": snapshot["snapshot_id"], "scope_id": snapshot["scope_id"],
                "collection_run_id": snapshot["collection_run_id"], "status": snapshot["status"],
                "quality_grade": snapshot.get("quality_grade"), "data_mode": snapshot.get("data_mode"),
                "freshness_status": snapshot.get("freshness_status"),
                "observed_at": snapshot.get("observed_at"), "captured_at": snapshot.get("captured_at"),
                "source_coverage": snapshot.get("source_coverage") or {},
                "source_results": snapshot.get("source_results") or [],
            }),
            "filters": {
                "view": view, "scope_id": scope_id, "snapshot_id": snapshot["snapshot_id"],
                "metric_key": metric_key, "brand_ids": selected_brands,
                "source_name": source_name, "limit": limit,
            },
            "metric": metrics[0] if view == "trend" and metrics else None,
            "metrics": metrics,
            "series": trend["series"] if view in {"overview", "trend"} else [],
            "trend_available": trend["trend_available"] if view in {"overview", "trend"} else False,
            "ranking": ranking if view in {"overview", "comparison"} else [],
            "comparison": (
                {"items": ranking, "selected_brand_ids": selected_brands}
                if view == "comparison" else trend["comparison"]
            ),
            "distribution": {
                "source_results": snapshot.get("source_results") or [],
                "quality_grade": snapshot.get("quality_grade"),
            },
            "contributors": [],
            "evidence": raw_evidence,
            "quality": quality,
            "warnings": list(dict.fromkeys(warnings)),
            "metric_catalog": self.metric_catalog() if view == "overview" else [],
            "custom_metrics": [
                self._metric_item(key, definitions.get(key), value_rows, entity_type="scope", entity_key=scope_id)
                for key, value_rows in values.items() if key.startswith("formula:")
            ],
        }
        if view == "evidence":
            result["series"] = []
            result["ranking"] = []
        if view == "trend":
            result["metric"] = trend["metric"]
        return _jsonable(result)
