"""主数据运营仓储。

该模块只根据人工确认及可追溯证据写入映射，不根据名称相似度猜测品牌或门店。映射变更
会登记受影响快照的回算请求，调用方可据此幂等重算正式指标。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.data_governance.normalizer import normalize_text
from brandpulse.db_clients.postgres_client import PostgresClient


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


class MasterDataRepository:
    """原始观测映射、门店生命周期和范围门店关系。"""

    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        return _serialize(dict(row))

    def list_mapping_observations(
        self,
        *,
        scope_id: Optional[str],
        mapping_status: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        conditions = ["observation.scope_id IS NOT NULL", "observation.quality_status = 'accepted'"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if scope_id:
            conditions.append("observation.scope_id = :scope_id")
            params["scope_id"] = scope_id
        if mapping_status:
            conditions.append("observation.entity_mapping_status = :mapping_status")
            params["mapping_status"] = mapping_status
        where = " AND ".join(conditions)
        base = f"""
            FROM raw_observations AS observation
            JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = observation.scope_id
            LEFT JOIN entity_mapping_decisions AS decision
              ON decision.observation_id = observation.observation_id AND decision.is_current = TRUE
            WHERE {where}
        """
        with self.client.engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar_one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT observation.observation_id, observation.scope_id, observation.collection_run_id,
                           observation.source_name, observation.record_type, observation.source_record_key,
                           observation.source_url, observation.observed_date, observation.raw_category,
                           observation.standard_category, observation.category_mapping_status,
                           observation.entity_mapping_status, observation.mapping_confidence,
                           observation.brand_id, observation.store_id, observation.payload,
                           scope.city, scope.mall_name, scope.category,
                           decision.mapping_id, decision.mapping_status AS decision_status,
                           decision.match_method, decision.evidence AS decision_evidence,
                           decision.effective_from, decision.effective_to, decision.reviewed_by,
                           decision.reviewed_at
                    {base}
                    ORDER BY observation.observed_date DESC, observation.source_name, observation.source_record_key
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
        return {"items": [self._row(row) for row in rows], "total": int(total)}

    def get_mapping_observation(self, observation_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT observation.*, scope.city, scope.mall_name, scope.category
                    FROM raw_observations AS observation
                    JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = observation.scope_id
                    WHERE observation.observation_id = :observation_id
                    """
                ),
                {"observation_id": observation_id},
            ).mappings().first()
        return self._row(row) if row else None

    def mapping_candidates(self, observation_id: str, *, limit: int = 50) -> Dict[str, Any]:
        observation = self.get_mapping_observation(observation_id)
        if not observation:
            raise ValueError("原始观测不存在或不属于可信监测范围")
        payload = observation.get("payload") or {}
        raw_name = str(payload.get("shop_name") or payload.get("title") or "")
        normalized = normalize_text(raw_name)
        candidates: list[Dict[str, Any]] = []
        if normalized:
            with self.client.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT DISTINCT store.store_id, store.brand_id, store.store_name,
                               store.city, store.mall_name, store.address,
                               alias.match_method, alias.confidence
                        FROM store_aliases AS alias
                        JOIN stores AS store ON store.store_id = alias.store_id
                        WHERE alias.match_status = 'confirmed'
                          AND alias.normalized_store_name = :normalized
                          AND alias.city = :city
                          AND (alias.mall_name = :mall_name OR alias.mall_name = '')
                        ORDER BY alias.confidence DESC NULLS LAST, store.store_name
                        LIMIT :limit
                        """
                    ),
                    {
                        "normalized": normalized,
                        "city": observation["city"],
                        "mall_name": observation["mall_name"],
                        "limit": limit,
                    },
                ).mappings().all()
            candidates = [self._row(row) for row in rows]
        return {
            "observation": observation,
            "normalized_name": normalized,
            "items": candidates,
            "message": (
                "候选仅来自已确认门店别名的精确名称/城市/商场匹配；仍需人工核对来源链接后确认。"
                if candidates else "没有可自动推荐的候选，请通过门店主数据搜索后人工确认或拒绝归属。"
            ),
        }

    @staticmethod
    def _recalculation_requests(conn, *, observation: Dict[str, Any], mapping_id: str, actor: str, reason: str) -> list[Dict[str, Any]]:
        snapshots = conn.execute(
            text(
                """
                SELECT snapshot_id
                FROM data_snapshots
                WHERE scope_id = :scope_id
                  AND collection_run_id = :collection_run_id
                  AND status IN ('ready', 'published')
                """
            ),
            {
                "scope_id": observation["scope_id"],
                "collection_run_id": observation["collection_run_id"],
            },
        ).mappings().all()
        requests = []
        for snapshot in snapshots:
            request_id = f"mapping_recalc_{uuid4().hex}"
            row = conn.execute(
                text(
                    """
                    INSERT INTO mapping_recalculation_requests (
                        request_id, mapping_id, snapshot_id, scope_id, status, reason, requested_by
                    ) VALUES (
                        :request_id, :mapping_id, :snapshot_id, :scope_id, 'pending', :reason, :requested_by
                    )
                    ON CONFLICT (mapping_id, snapshot_id) DO UPDATE SET
                        status = 'pending', reason = EXCLUDED.reason, requested_by = EXCLUDED.requested_by,
                        requested_at = CURRENT_TIMESTAMP, started_at = NULL, finished_at = NULL,
                        error_message = '', updated_at = CURRENT_TIMESTAMP
                    RETURNING request_id, snapshot_id, scope_id
                    """
                ),
                {
                    "request_id": request_id,
                    "mapping_id": mapping_id,
                    "snapshot_id": snapshot["snapshot_id"],
                    "scope_id": observation["scope_id"],
                    "reason": reason,
                    "requested_by": actor,
                },
            ).mappings().one()
            requests.append(dict(row))
        return requests

    def decide_mapping(
        self,
        *,
        observation_id: str,
        mapping_status: str,
        store_id: Optional[str],
        evidence_note: str,
        effective_from: Optional[date],
        actor: str,
    ) -> Dict[str, Any]:
        if mapping_status not in {"confirmed", "rejected"}:
            raise ValueError("映射决策只能为 confirmed 或 rejected")
        if mapping_status == "confirmed" and not store_id:
            raise ValueError("确认映射时必须选择真实门店")
        if len(evidence_note.strip()) < 3:
            raise ValueError("请填写至少 3 个字符的核验依据")
        with self.client.engine.begin() as conn:
            observation = conn.execute(
                text(
                    """
                    SELECT observation.*, scope.city, scope.mall_name, scope.category
                    FROM raw_observations AS observation
                    JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = observation.scope_id
                    WHERE observation.observation_id = :observation_id
                    FOR UPDATE
                    """
                ),
                {"observation_id": observation_id},
            ).mappings().first()
            if not observation:
                raise ValueError("原始观测不存在或不属于可信监测范围")
            observation_data = dict(observation)
            store = None
            if store_id:
                store = conn.execute(
                    text(
                        """
                        SELECT store_id, brand_id, store_name, city, mall_name, address
                        FROM stores WHERE store_id = :store_id
                        """
                    ),
                    {"store_id": store_id},
                ).mappings().first()
                if not store:
                    raise ValueError("选择的门店主数据不存在")
            current = conn.execute(
                text(
                    """
                    SELECT mapping_id FROM entity_mapping_decisions
                    WHERE observation_id = :observation_id AND is_current = TRUE
                    FOR UPDATE
                    """
                ),
                {"observation_id": observation_id},
            ).mappings().first()
            if current:
                conn.execute(
                    text(
                        """
                        UPDATE entity_mapping_decisions
                        SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP
                        WHERE mapping_id = :mapping_id
                        """
                    ),
                    {"mapping_id": current["mapping_id"]},
                )
            mapping_id = f"mapping_{uuid4().hex}"
            payload = observation_data.get("payload") or {}
            evidence = {
                "note": evidence_note.strip(),
                "source_url": observation_data.get("source_url") or "",
                "source_record_key": observation_data["source_record_key"],
                "raw_entity_name": payload.get("shop_name") or payload.get("title") or "",
                "verified_at": datetime.now().isoformat(timespec="seconds"),
            }
            conn.execute(
                text(
                    """
                    INSERT INTO entity_mapping_decisions (
                        mapping_id, observation_id, scope_id, source_name, source_record_key,
                        mapping_status, brand_id, store_id, match_method, confidence, evidence,
                        effective_from, is_current, supersedes_mapping_id, reviewed_by
                    ) VALUES (
                        :mapping_id, :observation_id, :scope_id, :source_name, :source_record_key,
                        :mapping_status, :brand_id, :store_id, 'manual', :confidence, CAST(:evidence AS jsonb),
                        :effective_from, TRUE, :supersedes_mapping_id, :reviewed_by
                    )
                    """
                ),
                {
                    "mapping_id": mapping_id,
                    "observation_id": observation_id,
                    "scope_id": observation_data["scope_id"],
                    "source_name": observation_data["source_name"],
                    "source_record_key": observation_data["source_record_key"],
                    "mapping_status": mapping_status,
                    "brand_id": store["brand_id"] if store and mapping_status == "confirmed" else None,
                    "store_id": store["store_id"] if store and mapping_status == "confirmed" else None,
                    "confidence": 1.0 if mapping_status == "confirmed" else None,
                    "evidence": _json(evidence),
                    "effective_from": effective_from,
                    "supersedes_mapping_id": current["mapping_id"] if current else None,
                    "reviewed_by": actor,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE raw_observations
                    SET brand_id = :brand_id, store_id = :store_id,
                        entity_mapping_status = :mapping_status,
                        mapping_confidence = :confidence, updated_at = CURRENT_TIMESTAMP
                    WHERE observation_id = :observation_id
                    """
                ),
                {
                    "observation_id": observation_id,
                    "brand_id": store["brand_id"] if store and mapping_status == "confirmed" else None,
                    "store_id": store["store_id"] if store and mapping_status == "confirmed" else None,
                    "mapping_status": mapping_status,
                    "confidence": 1.0 if mapping_status == "confirmed" else None,
                },
            )
            requests = self._recalculation_requests(
                conn,
                observation=observation_data,
                mapping_id=mapping_id,
                actor=actor,
                reason=f"原始观测映射{mapping_status}",
            )
            row = conn.execute(
                text("SELECT * FROM entity_mapping_decisions WHERE mapping_id = :mapping_id"),
                {"mapping_id": mapping_id},
            ).mappings().one()
        return {"decision": self._row(row), "recalculation_requests": [self._row(item) for item in requests]}

    def revert_mapping(self, *, mapping_id: str, actor: str, evidence_note: str) -> Dict[str, Any]:
        if len(evidence_note.strip()) < 3:
            raise ValueError("请填写至少 3 个字符的撤销依据")
        with self.client.engine.begin() as conn:
            current = conn.execute(
                text(
                    """
                    SELECT decision.*, observation.collection_run_id
                    FROM entity_mapping_decisions AS decision
                    JOIN raw_observations AS observation ON observation.observation_id = decision.observation_id
                    WHERE decision.mapping_id = :mapping_id AND decision.is_current = TRUE
                    FOR UPDATE
                    """
                ),
                {"mapping_id": mapping_id},
            ).mappings().first()
            if not current:
                raise ValueError("只能撤销当前生效的映射决策")
            current_data = dict(current)
            previous = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mapping_decisions
                    WHERE observation_id = :observation_id
                      AND mapping_id <> :mapping_id
                      AND mapping_status IN ('confirmed', 'rejected')
                    ORDER BY reviewed_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """
                ),
                {"observation_id": current_data["observation_id"], "mapping_id": mapping_id},
            ).mappings().first()
            evidence = dict(current_data.get("evidence") or {})
            evidence["revoke_note"] = evidence_note.strip()
            evidence["revoked_by"] = actor
            evidence["revoked_at"] = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                text(
                    """
                    UPDATE entity_mapping_decisions
                    SET mapping_status = 'revoked', is_current = FALSE, evidence = CAST(:evidence AS jsonb),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_id = :mapping_id
                    """
                ),
                {"mapping_id": mapping_id, "evidence": _json(evidence)},
            )
            restored = dict(previous) if previous else None
            if restored:
                conn.execute(
                    text(
                        """
                        UPDATE entity_mapping_decisions
                        SET is_current = TRUE, updated_at = CURRENT_TIMESTAMP
                        WHERE mapping_id = :mapping_id
                        """
                    ),
                    {"mapping_id": restored["mapping_id"]},
                )
            conn.execute(
                text(
                    """
                    UPDATE raw_observations
                    SET brand_id = :brand_id, store_id = :store_id,
                        entity_mapping_status = :mapping_status,
                        mapping_confidence = :confidence, updated_at = CURRENT_TIMESTAMP
                    WHERE observation_id = :observation_id
                    """
                ),
                {
                    "observation_id": current_data["observation_id"],
                    "brand_id": restored.get("brand_id") if restored else None,
                    "store_id": restored.get("store_id") if restored else None,
                    "mapping_status": restored.get("mapping_status") if restored else "pending",
                    "confidence": restored.get("confidence") if restored else None,
                },
            )
            observation = {
                "scope_id": current_data["scope_id"],
                "collection_run_id": current_data["collection_run_id"],
            }
            requests = self._recalculation_requests(
                conn,
                observation=observation,
                mapping_id=mapping_id,
                actor=actor,
                reason="撤销原始观测映射",
            )
            revoked = conn.execute(
                text("SELECT * FROM entity_mapping_decisions WHERE mapping_id = :mapping_id"),
                {"mapping_id": mapping_id},
            ).mappings().one()
        return {
            "decision": self._row(revoked),
            "restored_mapping_id": restored.get("mapping_id") if restored else None,
            "recalculation_requests": [self._row(item) for item in requests],
        }

    def list_recalculation_requests(self, *, scope_id: Optional[str], status: Optional[str], limit: int) -> list[Dict[str, Any]]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}
        if scope_id:
            conditions.append("request.scope_id = :scope_id")
            params["scope_id"] = scope_id
        if status:
            conditions.append("request.status = :status")
            params["status"] = status
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT request.*, snapshot.observed_at
                    FROM mapping_recalculation_requests AS request
                    JOIN data_snapshots AS snapshot ON snapshot.snapshot_id = request.snapshot_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY request.requested_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._row(row) for row in rows]

    def claim_recalculation_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE mapping_recalculation_requests
                    SET status = 'running', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE request_id = :request_id AND status = 'pending'
                    RETURNING *
                    """
                ),
                {"request_id": request_id},
            ).mappings().first()
        return self._row(row) if row else None

    def finish_recalculation_request(self, request_id: str, *, error_message: str = "") -> None:
        status = "failed" if error_message else "completed"
        with self.client.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE mapping_recalculation_requests
                    SET status = :status, error_message = :error_message,
                        finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE request_id = :request_id
                    """
                ),
                {"request_id": request_id, "status": status, "error_message": error_message},
            )

    def list_scope_store_mappings(self, scope_id: str) -> list[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT mapping.*, store.store_name, store.brand_id, store.city, store.mall_name,
                           brand.brand_name_cn
                    FROM scope_store_mappings AS mapping
                    JOIN stores AS store ON store.store_id = mapping.store_id
                    LEFT JOIN brands AS brand ON brand.brand_id = store.brand_id
                    WHERE mapping.scope_id = :scope_id
                    ORDER BY mapping.mapping_status, store.store_name
                    """
                ),
                {"scope_id": scope_id},
            ).mappings().all()
        return [self._row(row) for row in rows]

    def upsert_scope_store_mapping(
        self,
        *,
        scope_id: str,
        store_id: str,
        mapping_status: str,
        effective_from: Optional[date],
        evidence_note: str,
        actor: str,
    ) -> Dict[str, Any]:
        if mapping_status not in {"candidate", "confirmed", "excluded", "revoked"}:
            raise ValueError("项目门店映射状态不合法")
        if len(evidence_note.strip()) < 3:
            raise ValueError("请填写至少 3 个字符的映射依据")
        mapping_id = f"scope_store_{uuid4().hex}"
        with self.client.engine.begin() as conn:
            scope_exists = conn.execute(
                text("SELECT 1 FROM trusted_monitoring_scopes WHERE scope_id = :scope_id"),
                {"scope_id": scope_id},
            ).first()
            store_exists = conn.execute(
                text("SELECT 1 FROM stores WHERE store_id = :store_id"),
                {"store_id": store_id},
            ).first()
            if not scope_exists or not store_exists:
                raise ValueError("监测范围或门店主数据不存在")
            row = conn.execute(
                text(
                    """
                    INSERT INTO scope_store_mappings (
                        scope_store_mapping_id, scope_id, store_id, mapping_status,
                        effective_from, evidence, confirmed_by
                    ) VALUES (
                        :mapping_id, :scope_id, :store_id, :mapping_status,
                        :effective_from, CAST(:evidence AS jsonb), :confirmed_by
                    )
                    ON CONFLICT (scope_id, store_id) DO UPDATE SET
                        mapping_status = EXCLUDED.mapping_status,
                        effective_from = EXCLUDED.effective_from,
                        evidence = EXCLUDED.evidence,
                        confirmed_by = EXCLUDED.confirmed_by,
                        confirmed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """
                ),
                {
                    "mapping_id": mapping_id,
                    "scope_id": scope_id,
                    "store_id": store_id,
                    "mapping_status": mapping_status,
                    "effective_from": effective_from,
                    "evidence": _json({"note": evidence_note.strip()}),
                    "confirmed_by": actor,
                },
            ).mappings().one()
        return self._row(row)
