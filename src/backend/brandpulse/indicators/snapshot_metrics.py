"""快照绑定的确定性指标计算。

公开数据只生成公开口碑、公开内容和竞争线索指标。它不会推断销售、坪效、利润或租户
健康度；没有足够可比快照时趋势值保持 ``NULL`` 并写明原因。
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.trusted_data_repository import SnapshotRepository

METRIC_VERSION = "snapshot-v2"
MIN_REPUTATION_POOL = 3
MAX_COMPARABLE_INTERVAL_DAYS = 7


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _numeric(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    numeric = _numeric(value)
    return int(numeric) if numeric is not None else None


def bayesian_weight(score: float, review_count: int, average: float, threshold: float) -> float:
    """标准贝叶斯加权评分；输入由可解释比较池提供。"""
    return (review_count / (review_count + threshold)) * score + (
        threshold / (review_count + threshold)
    ) * average


def is_comparable_cumulative_stock(
    *,
    current_total: int,
    previous_total: int,
    interval_days: float,
    current_source_success: bool,
) -> bool:
    """累计公开指标的趋势门禁。

    评价数下降通常意味着来源展示口径变动或抓取异常，而不是可直接解释为品牌表现
    下降。这里返回 ``False``，由调用方写入 not_comparable 证据，而不是产出负增长。
    """
    return (
        current_source_success
        and 0 < interval_days <= MAX_COMPARABLE_INTERVAL_DAYS
        and previous_total > 0
        and current_total >= previous_total
    )


class SnapshotMetricService:
    """以单个 ready/published snapshot 为唯一输入边界计算指标。"""

    def __init__(self):
        self.client = PostgresClient()
        self.snapshots = SnapshotRepository()

    def _raw(self, snapshot: Dict[str, Any], source_name: str, record_type: str) -> list[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT observation_id, source_record_key, source_url, payload,
                           entity_mapping_status, brand_id, store_id
                    FROM raw_observations
                    WHERE scope_id = :scope_id
                      AND collection_run_id = :collection_run_id
                      AND source_name = :source_name
                      AND record_type = :record_type
                      AND quality_status = 'accepted'
                    ORDER BY source_record_key
                    """
                ),
                {
                    "scope_id": snapshot["scope_id"],
                    "collection_run_id": snapshot["collection_run_id"],
                    "source_name": source_name,
                    "record_type": record_type,
                },
            ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _metric(
        *,
        snapshot: Dict[str, Any],
        metric_key: str,
        entity_type: str,
        entity_key: str,
        value: Optional[float],
        unit: str,
        source_name: str = "",
        time_window_days: Optional[int] = None,
        quality_status: str = "valid",
        baseline_scope: Optional[Dict[str, Any]] = None,
        baseline_level: str = "",
        sample_size: Optional[int] = None,
        parameters: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        brand_id: Optional[str] = None,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "metric_key": metric_key,
            "snapshot_id": snapshot["snapshot_id"],
            "scope_id": snapshot["scope_id"],
            "metric_version": METRIC_VERSION,
            "entity_type": entity_type,
            "entity_key": entity_key,
            "brand_id": brand_id,
            "store_id": store_id,
            "source_name": source_name,
            "time_window_days": time_window_days,
            "value": round(value, 6) if value is not None else None,
            "unit": unit,
            "quality_status": quality_status,
            "baseline_scope": baseline_scope or {},
            "baseline_level": baseline_level,
            "sample_size": sample_size,
            "parameters": parameters or {},
            "evidence": evidence or {},
        }

    def _start_run(self, snapshot_id: str) -> str:
        run_id = f"metricrun_{snapshot_id.split('_')[-1][:32]}"
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO metric_calculation_runs (metric_run_id, snapshot_id, metric_version, status)
                    VALUES (:metric_run_id, :snapshot_id, :metric_version, 'running')
                    ON CONFLICT (snapshot_id, metric_version) DO UPDATE SET
                        status = 'running', failure_reason = '', output_count = 0,
                        started_at = CURRENT_TIMESTAMP, finished_at = NULL, updated_at = CURRENT_TIMESTAMP
                    RETURNING metric_run_id
                    """
                ),
                {
                    "metric_run_id": run_id,
                    "snapshot_id": snapshot_id,
                    "metric_version": METRIC_VERSION,
                },
            ).mappings().one()
        return str(row["metric_run_id"])

    def _finish_run(
        self,
        metric_run_id: str,
        *,
        status: str,
        input_summary: Dict[str, Any],
        output_count: int,
        failure_reason: str = "",
    ) -> None:
        with self.client.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE metric_calculation_runs
                    SET status = :status, input_summary = CAST(:input_summary AS jsonb),
                        output_count = :output_count, failure_reason = :failure_reason,
                        finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE metric_run_id = :metric_run_id
                    """
                ),
                {
                    "metric_run_id": metric_run_id,
                    "status": status,
                    "input_summary": _json(input_summary),
                    "output_count": output_count,
                    "failure_reason": failure_reason,
                },
            )

    def _reputation_pool(
        self,
        snapshot: Dict[str, Any],
        current_rows: list[Dict[str, Any]],
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any], str]:
        """优先同商场同品类；样本不足时降级到同城同品类的近时点已发布快照。"""
        scored = [
            row for row in current_rows
            if _numeric((row.get("payload") or {}).get("score")) is not None
            and (_int((row.get("payload") or {}).get("review_count")) or 0) > 0
        ]
        baseline = {
            "scope_id": snapshot["scope_id"],
            "city": snapshot["city"],
            "mall_name": snapshot["mall_name"],
            "category": snapshot["category"],
        }
        if len(scored) >= MIN_REPUTATION_POOL:
            return scored, baseline, "same_mall_category"

        # 只有与当前范围同城同品类且时间相邻的 released snapshot 才能作为降级比较池，
        # 避免把不同时间的累计评价混成一个“当天基准”。
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT observation.observation_id, observation.source_record_key,
                           observation.source_url, observation.payload,
                           observation.entity_mapping_status, observation.brand_id, observation.store_id
                    FROM data_snapshots AS peer_snapshot
                    JOIN trusted_monitoring_scopes AS peer_scope ON peer_scope.scope_id = peer_snapshot.scope_id
                    JOIN raw_observations AS observation
                      ON observation.collection_run_id = peer_snapshot.collection_run_id
                     AND observation.scope_id = peer_snapshot.scope_id
                    WHERE peer_snapshot.status IN ('ready', 'published')
                      AND peer_scope.city = :city
                      AND peer_scope.category = :category
                      AND peer_snapshot.observed_at BETWEEN :from_time AND :to_time
                      AND observation.source_name = 'dianping_webbridge'
                      AND observation.record_type = 'dp_shop_metric'
                      AND observation.quality_status = 'accepted'
                    """
                ),
                {
                    "city": snapshot["city"],
                    "category": snapshot["category"],
                    "from_time": datetime.fromisoformat(str(snapshot["observed_at"]))
                    .replace(hour=0, minute=0, second=0, microsecond=0),
                    "to_time": datetime.fromisoformat(str(snapshot["observed_at"]))
                    .replace(hour=23, minute=59, second=59, microsecond=999999),
                },
            ).mappings().all()
        fallback = [
            dict(row) for row in rows
            if _numeric((row.get("payload") or {}).get("score")) is not None
            and (_int((row.get("payload") or {}).get("review_count")) or 0) > 0
        ]
        if len(fallback) >= MIN_REPUTATION_POOL:
            return fallback, {
                "city": snapshot["city"],
                "category": snapshot["category"],
                "same_day": str(snapshot["observed_at"])[:10],
            }, "same_city_category_same_day"
        return scored, baseline, "insufficient_sample"

    def _previous_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT snapshot_id
                    FROM data_snapshots
                    WHERE scope_id = :scope_id
                      AND status IN ('ready', 'published')
                      AND observed_at < :observed_at
                      AND EXISTS (
                          SELECT 1 FROM snapshot_source_results AS result
                          WHERE result.snapshot_id = data_snapshots.snapshot_id
                            AND result.source_name = 'dianping_webbridge'
                            AND result.status = 'success'
                            AND result.validated_count > 0
                      )
                    ORDER BY observed_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "scope_id": snapshot["scope_id"],
                    "observed_at": snapshot["observed_at"],
                },
            ).mappings().first()
        return self.snapshots.get(str(row["snapshot_id"])) if row else None

    def _upsert_metrics(self, metric_run_id: str, metrics: Iterable[Dict[str, Any]]) -> int:
        rows = list(metrics)
        if not rows:
            return 0
        sql = text(
            """
            INSERT INTO metric_observations (
                metric_observation_id, snapshot_id, scope_id, metric_run_id, metric_key,
                metric_version, entity_type, entity_key, brand_id, store_id, source_name,
                time_window_days, value, unit, quality_status, baseline_scope, baseline_level,
                sample_size, parameters, evidence, calculated_at
            ) VALUES (
                :metric_observation_id, :snapshot_id, :scope_id, :metric_run_id, :metric_key,
                :metric_version, :entity_type, :entity_key, :brand_id, :store_id, :source_name,
                :time_window_days, :value, :unit, :quality_status, CAST(:baseline_scope AS jsonb), :baseline_level,
                :sample_size, CAST(:parameters AS jsonb), CAST(:evidence AS jsonb), CURRENT_TIMESTAMP
            )
            ON CONFLICT (snapshot_id, metric_key, entity_type, entity_key, source_name) DO UPDATE SET
                metric_run_id = EXCLUDED.metric_run_id,
                value = EXCLUDED.value,
                unit = EXCLUDED.unit,
                quality_status = EXCLUDED.quality_status,
                baseline_scope = EXCLUDED.baseline_scope,
                baseline_level = EXCLUDED.baseline_level,
                sample_size = EXCLUDED.sample_size,
                parameters = EXCLUDED.parameters,
                evidence = EXCLUDED.evidence,
                calculated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        with self.client.engine.begin() as conn:
            for row in rows:
                row = {
                    **row,
                    "metric_observation_id": f"metric_{hashlib_sha(row['snapshot_id'], row['metric_key'], row['entity_type'], row['entity_key'], row['source_name'])}",
                    "metric_run_id": metric_run_id,
                    "baseline_scope": _json(row["baseline_scope"]),
                    "parameters": _json(row["parameters"]),
                    "evidence": _json(row["evidence"]),
                }
                conn.execute(sql, row)
        return len(rows)

    def calculate(self, snapshot_id: str) -> Dict[str, Any]:
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            raise ValueError("数据快照不存在")
        if snapshot["status"] not in {"ready", "published"}:
            raise ValueError("只有 ready/published 快照可以计算正式指标")
        metric_run_id = self._start_run(snapshot_id)
        dp_rows = self._raw(snapshot, "dianping_webbridge", "dp_shop_metric")
        xhs_rows = self._raw(snapshot, "xiaohongshu_webbridge", "xhs_note")
        metrics: list[Dict[str, Any]] = []
        try:
            scope_key = str(snapshot["scope_id"])
            dp_reviews = [
                _int((row.get("payload") or {}).get("review_count")) or 0
                for row in dp_rows
            ]
            dp_total = sum(dp_reviews)
            metrics.extend([
                self._metric(
                    snapshot=snapshot,
                    metric_key="dp_review_count_stock",
                    entity_type="scope",
                    entity_key=scope_key,
                    value=float(dp_total),
                    unit="条",
                    source_name="dianping_webbridge",
                    evidence={"observation_count": len(dp_rows), "source": "dianping_webbridge"},
                ),
                self._metric(
                    snapshot=snapshot,
                    metric_key="dp_store_count_observed",
                    entity_type="scope",
                    entity_key=scope_key,
                    value=float(len(dp_rows)),
                    unit="家",
                    source_name="dianping_webbridge",
                    evidence={"observation_count": len(dp_rows), "definition": "通过校验的点评搜索结果门店数"},
                ),
            ])

            pool, baseline_scope, baseline_level = self._reputation_pool(snapshot, dp_rows)
            scored_pool = [
                (_numeric((row["payload"] or {}).get("score")), _int((row["payload"] or {}).get("review_count")) or 0)
                for row in pool
            ]
            if len(scored_pool) >= MIN_REPUTATION_POOL:
                total_reviews = sum(review_count for _, review_count in scored_pool)
                average = sum(score * review_count for score, review_count in scored_pool) / total_reviews
                threshold = statistics.median([review_count for _, review_count in scored_pool]) or 1.0
            else:
                average = threshold = None

            for row, review_count in zip(dp_rows, dp_reviews):
                payload = row.get("payload") or {}
                score = _numeric(payload.get("score"))
                evidence = {
                    "observation_id": row["observation_id"],
                    "source_record_key": row["source_record_key"],
                    "source_url": row["source_url"],
                    "shop_name": payload.get("shop_name"),
                    "review_count": review_count,
                    "score": score,
                }
                share_quality = "valid" if dp_total > 0 else "not_comparable"
                metrics.append(self._metric(
                    snapshot=snapshot,
                    metric_key="dianping_review_share",
                    entity_type="shop",
                    entity_key=row["source_record_key"],
                    value=(review_count / dp_total) if dp_total > 0 else None,
                    unit="比例",
                    source_name="dianping_webbridge",
                    quality_status=share_quality,
                    baseline_scope={"scope_id": scope_key, "denominator": "same_scope_dp_review_count_stock"},
                    baseline_level="same_mall_category",
                    sample_size=len(dp_rows),
                    evidence={**evidence, "denominator": dp_total},
                    brand_id=row.get("brand_id") if row.get("entity_mapping_status") == "confirmed" else None,
                    store_id=row.get("store_id") if row.get("entity_mapping_status") == "confirmed" else None,
                ))
                reputation_quality = "valid" if average is not None and score is not None else "insufficient_sample"
                metrics.append(self._metric(
                    snapshot=snapshot,
                    metric_key="bayesian_reputation",
                    entity_type="shop",
                    entity_key=row["source_record_key"],
                    value=(bayesian_weight(score, review_count, average, threshold)
                           if average is not None and score is not None else None),
                    unit="分",
                    source_name="dianping_webbridge",
                    quality_status=reputation_quality,
                    baseline_scope=baseline_scope,
                    baseline_level=baseline_level,
                    sample_size=len(scored_pool),
                    parameters={
                        "formula": "WR=(v/(v+m))*R+(m/(v+m))*C",
                        "R": score,
                        "v": review_count,
                        "C": round(average, 6) if average is not None else None,
                        "m": threshold,
                        "minimum_pool": MIN_REPUTATION_POOL,
                    },
                    evidence=evidence,
                    brand_id=row.get("brand_id") if row.get("entity_mapping_status") == "confirmed" else None,
                    store_id=row.get("store_id") if row.get("entity_mapping_status") == "confirmed" else None,
                ))

            source_results = {item["source_name"]: item for item in snapshot.get("source_results", [])}
            xhs_success = source_results.get("xiaohongshu_webbridge", {}).get("status") == "success"
            if xhs_success:
                likes = [_int((row.get("payload") or {}).get("likes")) for row in xhs_rows]
                known_likes = [value for value in likes if value is not None]
                metrics.extend([
                    self._metric(
                        snapshot=snapshot,
                        metric_key="xhs_content_count_observed",
                        entity_type="scope",
                        entity_key=scope_key,
                        value=float(len(xhs_rows)),
                        unit="篇",
                        source_name="xiaohongshu_webbridge",
                        evidence={"observation_count": len(xhs_rows)},
                    ),
                    self._metric(
                        snapshot=snapshot,
                        metric_key="xhs_likes_stock",
                        entity_type="scope",
                        entity_key=scope_key,
                        value=float(sum(known_likes)) if known_likes else None,
                        unit="赞",
                        source_name="xiaohongshu_webbridge",
                        quality_status="valid" if len(known_likes) == len(xhs_rows) else "partial",
                        evidence={"content_count": len(xhs_rows), "likes_available_count": len(known_likes)},
                    ),
                ])

            expected_sources = snapshot.get("expected_sources") or []
            successful_sources = [item for item in snapshot.get("source_results", []) if item["status"] == "success"]
            metrics.append(self._metric(
                snapshot=snapshot,
                metric_key="source_coverage_ratio",
                entity_type="scope",
                entity_key=scope_key,
                value=(len(successful_sources) / len(expected_sources)) if expected_sources else None,
                unit="比例",
                quality_status="valid" if expected_sources else "insufficient_sample",
                evidence={
                    "expected_sources": expected_sources,
                    "successful_sources": [item["source_name"] for item in successful_sources],
                    "source_results": snapshot.get("source_results", []),
                },
            ))
            all_raw = dp_rows + xhs_rows
            mapped = [
                row for row in all_raw
                if row.get("entity_mapping_status") == "confirmed" and (row.get("brand_id") or row.get("store_id"))
            ]
            metrics.append(self._metric(
                snapshot=snapshot,
                metric_key="entity_mapping_coverage",
                entity_type="scope",
                entity_key=scope_key,
                value=(len(mapped) / len(all_raw)) if all_raw else None,
                unit="比例",
                quality_status="valid" if all_raw else "insufficient_sample",
                evidence={"confirmed_mapping_count": len(mapped), "raw_observation_count": len(all_raw)},
            ))

            previous = self._previous_snapshot(snapshot)
            if previous:
                previous_dp = self._raw(previous, "dianping_webbridge", "dp_shop_metric")
                previous_total = sum(
                    _int((row.get("payload") or {}).get("review_count")) or 0
                    for row in previous_dp
                )
                current_time = datetime.fromisoformat(str(snapshot["observed_at"]))
                previous_time = datetime.fromisoformat(str(previous["observed_at"]))
                interval_days = max((current_time - previous_time).total_seconds() / 86400.0, 0.0)
                comparable = is_comparable_cumulative_stock(
                    current_total=dp_total,
                    previous_total=previous_total,
                    interval_days=interval_days,
                    current_source_success=(
                        source_results.get("dianping_webbridge", {}).get("status") == "success"
                    ),
                )
                trend_evidence = {
                    "previous_snapshot_id": previous["snapshot_id"],
                    "previous_total": previous_total,
                    "current_total": dp_total,
                    "interval_days": round(interval_days, 4),
                    "maximum_interval_days": MAX_COMPARABLE_INTERVAL_DAYS,
                }
                trend_quality = "valid" if comparable else "not_comparable"
                reason = "" if comparable else (
                    "采集间隔、来源完整性或累计评价数不满足可比条件；不输出趋势结论"
                )
                metrics.extend([
                    self._metric(
                        snapshot=snapshot,
                        metric_key="dp_review_count_delta",
                        entity_type="scope",
                        entity_key=scope_key,
                        value=float(dp_total - previous_total) if comparable else None,
                        unit="条",
                        source_name="dianping_webbridge",
                        time_window_days=max(math.ceil(interval_days), 1),
                        quality_status=trend_quality,
                        baseline_scope={"previous_snapshot_id": previous["snapshot_id"]},
                        baseline_level="same_scope_previous_comparable_snapshot",
                        evidence={**trend_evidence, "reason": reason},
                    ),
                    self._metric(
                        snapshot=snapshot,
                        metric_key="dp_review_count_growth_rate",
                        entity_type="scope",
                        entity_key=scope_key,
                        value=((dp_total - previous_total) / previous_total) if comparable else None,
                        unit="比例",
                        source_name="dianping_webbridge",
                        time_window_days=max(math.ceil(interval_days), 1),
                        quality_status=trend_quality,
                        baseline_scope={"previous_snapshot_id": previous["snapshot_id"]},
                        baseline_level="same_scope_previous_comparable_snapshot",
                        evidence={**trend_evidence, "reason": reason},
                    ),
                ])

            output_count = self._upsert_metrics(metric_run_id, metrics)
            self._finish_run(
                metric_run_id,
                status="completed",
                input_summary={
                    "snapshot_id": snapshot_id,
                    "dp_observations": len(dp_rows),
                    "xhs_observations": len(xhs_rows),
                    "snapshot_quality_grade": snapshot["quality_grade"],
                },
                output_count=output_count,
            )
            # 机会信号是指标之上的可解释衍生物。其生成故障不能把已成功写入的
            # 指标计算标记为失败；失败会由机会接口/任务日志暴露，下一次受控重算可恢复。
            try:
                from brandpulse.opportunities.service import OpportunityService

                opportunity_result = OpportunityService().generate(snapshot_id)
            except Exception as exc:  # pragma: no cover - 数据库异常由集成环境观测
                opportunity_result = {"status": "failed", "error": str(exc)}
            return {
                "metric_run_id": metric_run_id,
                "snapshot_id": snapshot_id,
                "status": "completed",
                "output_count": output_count,
                "opportunities": opportunity_result,
            }
        except Exception as exc:
            self._finish_run(
                metric_run_id,
                status="failed",
                input_summary={"snapshot_id": snapshot_id, "dp_observations": len(dp_rows), "xhs_observations": len(xhs_rows)},
                output_count=0,
                failure_reason=str(exc),
            )
            raise


def hashlib_sha(*values: str) -> str:
    """短稳定 ID；避免依赖数据库 UUID 函数。"""
    import hashlib

    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()[:40]
