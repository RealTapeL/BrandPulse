"""快照驱动的机会信号生成。

这里输出的是待人工核实的公开数据线索，而非经营结论或自动招商决定。所有信号均绑定
一个 snapshot_id、指标证据、来源覆盖和质量等级。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.trusted_data_repository import SnapshotRepository


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _serialize(row: Any) -> Dict[str, Any]:
    item = dict(row)
    for key, value in list(item.items()):
        if hasattr(value, "as_tuple"):
            item[key] = float(value)
        elif isinstance(value, datetime):
            item[key] = value.isoformat(sep=" ")
    return item


class OpportunityService:
    def __init__(self):
        self.client = PostgresClient()
        self.snapshots = SnapshotRepository()

    @staticmethod
    def _signal_id(snapshot_id: str, signal_type: str, entity_type: str, entity_key: str) -> str:
        digest = hashlib.sha256(
            "\x1f".join((snapshot_id, signal_type, entity_type, entity_key)).encode("utf-8")
        ).hexdigest()[:40]
        return f"signal_{digest}"

    def _upsert(self, conn, signal: Dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO opportunity_signals (
                    signal_id, snapshot_id, scope_id, brand_id, store_id, entity_type, entity_key,
                    entity_name, signal_type, signal_class, trigger_rule, metric_evidence,
                    source_evidence, quality_grade, confidence, recommended_action
                ) VALUES (
                    :signal_id, :snapshot_id, :scope_id, :brand_id, :store_id, :entity_type, :entity_key,
                    :entity_name, :signal_type, :signal_class, :trigger_rule, CAST(:metric_evidence AS jsonb),
                    CAST(:source_evidence AS jsonb), :quality_grade, :confidence, :recommended_action
                )
                ON CONFLICT (snapshot_id, signal_type, entity_type, entity_key) DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    trigger_rule = EXCLUDED.trigger_rule,
                    metric_evidence = EXCLUDED.metric_evidence,
                    source_evidence = EXCLUDED.source_evidence,
                    quality_grade = EXCLUDED.quality_grade,
                    confidence = EXCLUDED.confidence,
                    recommended_action = EXCLUDED.recommended_action,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                **signal,
                "metric_evidence": _json(signal["metric_evidence"]),
                "source_evidence": _json(signal["source_evidence"]),
            },
        )

    def generate(self, snapshot_id: str) -> Dict[str, Any]:
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            raise ValueError("数据快照不存在")
        if snapshot["status"] not in {"ready", "published"}:
            raise ValueError("只有 ready/published 快照可以生成正式机会信号")
        scope_id = str(snapshot["scope_id"])
        source_coverage = snapshot.get("source_coverage") or {}
        signals: List[Dict[str, Any]] = []
        with self.client.engine.begin() as conn:
            quality = conn.execute(
                text(
                    """
                    SELECT metric_key, value, quality_status, evidence
                    FROM metric_observations
                    WHERE snapshot_id = :snapshot_id
                      AND entity_type = 'scope'
                      AND metric_key IN ('entity_mapping_coverage', 'source_coverage_ratio')
                    """
                ),
                {"snapshot_id": snapshot_id},
            ).mappings().all()
            quality_by_key = {row["metric_key"]: dict(row) for row in quality}
            mapping = quality_by_key.get("entity_mapping_coverage")
            if mapping and mapping["value"] is not None and float(mapping["value"]) < 1:
                coverage = float(mapping["value"])
                signals.append({
                    "signal_id": self._signal_id(snapshot_id, "data_mapping_incomplete", "scope", scope_id),
                    "snapshot_id": snapshot_id,
                    "scope_id": scope_id,
                    "brand_id": None,
                    "store_id": None,
                    "entity_type": "scope",
                    "entity_key": scope_id,
                    "entity_name": f"{snapshot['city']}·{snapshot['mall_name']}·{snapshot['category']}",
                    "signal_type": "data_mapping_incomplete",
                    "signal_class": "data_quality",
                    "trigger_rule": "实体映射覆盖率低于 100%，未确认记录不得生成正式品牌招商判断。",
                    "metric_evidence": {"metric_key": "entity_mapping_coverage", "value": coverage, "evidence": mapping.get("evidence") or {}},
                    "source_evidence": {"snapshot_id": snapshot_id, "source_coverage": source_coverage},
                    "quality_grade": snapshot["quality_grade"],
                    "confidence": None,
                    "recommended_action": "在数据中心核对原始链接、门店地址和品牌主数据，完成或拒绝映射后再评估品牌机会。",
                })
            source = quality_by_key.get("source_coverage_ratio")
            if source and source["value"] is not None and float(source["value"]) < 1:
                signals.append({
                    "signal_id": self._signal_id(snapshot_id, "source_coverage_incomplete", "scope", scope_id),
                    "snapshot_id": snapshot_id,
                    "scope_id": scope_id,
                    "brand_id": None,
                    "store_id": None,
                    "entity_type": "scope",
                    "entity_key": scope_id,
                    "entity_name": f"{snapshot['city']}·{snapshot['mall_name']}·{snapshot['category']}",
                    "signal_type": "source_coverage_incomplete",
                    "signal_class": "data_quality",
                    "trigger_rule": "预期来源未全部成功；跨来源综合指标和正式结论保持不可用。",
                    "metric_evidence": {"metric_key": "source_coverage_ratio", "value": float(source["value"]), "evidence": source.get("evidence") or {}},
                    "source_evidence": {"snapshot_id": snapshot_id, "source_coverage": source_coverage},
                    "quality_grade": snapshot["quality_grade"],
                    "confidence": None,
                    "recommended_action": "检查采集来源登录态、解析失败或空结果校验；来源恢复后使用新快照重新评估。",
                })

            # 仅统计已经人工确认到真实品牌的观测。每个份额的分母仍为同一 scope 的点评累计评价总量。
            brand_rows = conn.execute(
                text(
                    """
                    WITH shop_metrics AS (
                        SELECT entity_key,
                               MAX(value) FILTER (WHERE metric_key = 'bayesian_reputation') AS reputation,
                               MAX(value) FILTER (WHERE metric_key = 'dianping_review_share') AS review_share
                        FROM metric_observations
                        WHERE snapshot_id = :snapshot_id
                          AND entity_type = 'shop'
                          AND source_name = 'dianping_webbridge'
                        GROUP BY entity_key
                    )
                    SELECT observation.brand_id, MAX(brand.brand_name_cn) AS brand_name,
                           AVG(metric.reputation) AS reputation,
                           SUM(metric.review_share) AS review_share,
                           COUNT(*) AS observed_store_count
                    FROM raw_observations AS observation
                    JOIN shop_metrics AS metric ON metric.entity_key = observation.source_record_key
                    JOIN brands AS brand ON brand.brand_id = observation.brand_id
                    WHERE observation.scope_id = :scope_id
                      AND observation.collection_run_id = :collection_run_id
                      AND observation.source_name = 'dianping_webbridge'
                      AND observation.record_type = 'dp_shop_metric'
                      AND observation.quality_status = 'accepted'
                      AND observation.entity_mapping_status = 'confirmed'
                      AND observation.brand_id IS NOT NULL
                      AND metric.reputation IS NOT NULL
                      AND metric.review_share IS NOT NULL
                    GROUP BY observation.brand_id
                    ORDER BY observation.brand_id
                    """
                ),
                {"snapshot_id": snapshot_id, "scope_id": scope_id, "collection_run_id": snapshot["collection_run_id"]},
            ).mappings().all()
            if len(brand_rows) >= 3:
                avg_reputation = sum(float(row["reputation"]) for row in brand_rows) / len(brand_rows)
                avg_share = sum(float(row["review_share"]) for row in brand_rows) / len(brand_rows)
                for row in brand_rows:
                    reputation, review_share = float(row["reputation"]), float(row["review_share"])
                    if reputation >= avg_reputation and review_share < avg_share:
                        signals.append({
                            "signal_id": self._signal_id(snapshot_id, "high_reputation_low_review_share", "brand", str(row["brand_id"])),
                            "snapshot_id": snapshot_id,
                            "scope_id": scope_id,
                            "brand_id": row["brand_id"],
                            "store_id": None,
                            "entity_type": "brand",
                            "entity_key": row["brand_id"],
                            "entity_name": row["brand_name"],
                            "signal_type": "high_reputation_low_review_share",
                            "signal_class": "opportunity",
                            "trigger_rule": "同一可信快照内，品牌平均贝叶斯口碑不低于已确认品牌均值，且点评评价份额低于已确认品牌均值。",
                            "metric_evidence": {
                                "brand_reputation": reputation,
                                "brand_review_share": review_share,
                                "baseline_reputation": avg_reputation,
                                "baseline_review_share": avg_share,
                                "observed_store_count": int(row["observed_store_count"]),
                                "metric_version": "snapshot-v2",
                            },
                            "source_evidence": {"snapshot_id": snapshot_id, "source_name": "dianping_webbridge", "source_coverage": source_coverage},
                            "quality_grade": snapshot["quality_grade"],
                            "confidence": min(0.9, 0.45 + 0.1 * len(brand_rows)),
                            "recommended_action": "作为待核实招商线索：补齐品牌定位、价格带、目标客群、面积与竞品覆盖信息后，由招商负责人评审。",
                        })
            for signal in signals:
                self._upsert(conn, signal)
        return {"snapshot_id": snapshot_id, "generated_count": len(signals), "items": signals}

    def list(
        self,
        *,
        scope_id: str,
        snapshot_id: Optional[str] = None,
        signal_class: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        snapshot = self.snapshots.get(snapshot_id) if snapshot_id else self.snapshots.latest_released(scope_id)
        if not snapshot:
            return {"snapshot": None, "items": []}
        if snapshot["scope_id"] != scope_id:
            raise ValueError("快照不属于当前监测范围")
        conditions = ["signal.snapshot_id = :snapshot_id"]
        params: Dict[str, Any] = {"snapshot_id": snapshot["snapshot_id"], "limit": min(max(limit, 1), 200)}
        if signal_class:
            conditions.append("signal.signal_class = :signal_class")
            params["signal_class"] = signal_class
        if lifecycle_status:
            conditions.append("signal.lifecycle_status = :lifecycle_status")
            params["lifecycle_status"] = lifecycle_status
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT signal.*, snapshot.observed_at
                    FROM opportunity_signals AS signal
                    JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = signal.snapshot_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY CASE signal.signal_class WHEN 'data_quality' THEN 1 WHEN 'risk' THEN 2 ELSE 3 END,
                             signal.confidence DESC NULLS LAST, signal.generated_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return {"snapshot": snapshot, "items": [_serialize(row) for row in rows]}

    def update_lifecycle(
        self,
        *,
        signal_id: str,
        lifecycle_status: str,
        owner_id: Optional[str],
        human_comment: str,
        human_confirmed: Optional[bool],
    ) -> Optional[Dict[str, Any]]:
        allowed = {
            "discovered", "master_confirmed", "profile_incomplete", "under_review", "qualified",
            "outreach", "negotiation", "introduced", "rejected", "archived",
        }
        if lifecycle_status not in allowed:
            raise ValueError("机会生命周期状态不合法")
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE opportunity_signals
                    SET lifecycle_status = :lifecycle_status,
                        owner_id = :owner_id,
                        human_comment = :human_comment,
                        human_confirmed = COALESCE(:human_confirmed, human_confirmed),
                        resolved_at = CASE WHEN :lifecycle_status IN ('introduced', 'rejected', 'archived')
                                           THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE signal_id = :signal_id
                    RETURNING *
                    """
                ),
                {
                    "signal_id": signal_id,
                    "lifecycle_status": lifecycle_status,
                    "owner_id": owner_id or None,
                    "human_comment": human_comment,
                    "human_confirmed": human_confirmed,
                },
            ).mappings().first()
        return _serialize(row) if row else None
