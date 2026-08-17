"""可信数据层仓储。

历史表继续服务兼容 API；本模块是范围、采集运行、来源结果、原始观测和可发布快照的
唯一写入入口。所有正式查询都应以 ``scope_id`` 和 ``snapshot_id`` 关联，不能再用
旧 ``brand_id`` 拼接城市和商场范围。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


DEFAULT_SOURCE_REQUIREMENTS = (
    {
        "source_name": "dianping_webbridge",
        "is_required": True,
        "allow_empty": False,
        "max_age_hours": 72,
    },
    {
        "source_name": "xiaohongshu_webbridge",
        "is_required": False,
        "allow_empty": True,
        "max_age_hours": 72,
    },
)
RELEASED_SNAPSHOT_STATUSES = ("ready", "published")


def scope_key(city: str, mall_name: str, category: str) -> str:
    """城市×商场×品类的稳定范围键，不包含任何品牌或数据集 ID。"""
    normalized = "|".join(value.strip() for value in (city, mall_name, category))
    return f"scopekey_{hashlib.md5(normalized.encode('utf-8')).hexdigest()}"


def compatibility_dataset_key(city: str, mall_name: str, category: str) -> str:
    """为旧表/API 保留稳定数据集键；不能当作真实品牌 ID 使用。"""
    normalized = "|".join(value.strip() for value in (city, mall_name, category))
    return f"MALL_{hashlib.md5(normalized.encode('utf-8')).hexdigest()[:8]}"


def new_scope_id(city: str, mall_name: str, category: str) -> str:
    """新范围的稳定 ID。历史范围可继续复用它们已有的 scope_id。"""
    digest = hashlib.sha256(
        "|".join(value.strip() for value in (city, mall_name, category)).encode("utf-8")
    ).hexdigest()[:24]
    return f"scope_{digest}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _serialize(row: Any) -> Dict[str, Any]:
    item = dict(row)
    for key, value in list(item.items()):
        if isinstance(value, datetime):
            item[key] = value.isoformat(sep=" ")
    return item


class TrustedScopeRepository:
    """规范监测范围及其旧表兼容映射。"""

    def __init__(self):
        self.client = PostgresClient()

    def _requirements(self, conn, scope_id: str) -> list[Dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT source_name, is_required, allow_empty, max_age_hours, is_active
                FROM scope_source_requirements
                WHERE scope_id = :scope_id
                ORDER BY source_name
                """
            ),
            {"scope_id": scope_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _presentation(row: Any, requirements: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        item = _serialize(row)
        # brand_id 是旧前端/旧 API 的兼容别名，语义明确标为 dataset key。
        item["brand_id"] = item.get("legacy_dataset_key", "")
        item["requirements"] = list(requirements)
        return item

    def _select(self, where: str, params: Dict[str, Any]) -> list[Dict[str, Any]]:
        sql = f"""
            SELECT scope.*,
                   snapshot.snapshot_id AS latest_snapshot_id,
                   snapshot.status AS latest_snapshot_status,
                   snapshot.observed_at AS latest_snapshot_at,
                   snapshot.freshness_status AS latest_snapshot_freshness,
                   snapshot.quality_grade AS latest_snapshot_quality_grade,
                   snapshot.data_mode AS latest_snapshot_data_mode,
                   snapshot.source_coverage AS latest_source_coverage,
                   source_dates.latest_dianping_date,
                   source_dates.latest_xiaohongshu_date
            FROM trusted_monitoring_scopes AS scope
            LEFT JOIN LATERAL (
                SELECT snapshot_id, status, observed_at, freshness_status, quality_grade,
                       data_mode, source_coverage
                FROM data_snapshots
                WHERE scope_id = scope.scope_id
                  AND status IN ('ready', 'published')
                ORDER BY observed_at DESC NULLS LAST, created_at DESC
                LIMIT 1
            ) AS snapshot ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    MAX(observed_date) FILTER (WHERE source_name = 'dianping_webbridge') AS latest_dianping_date,
                    MAX(observed_date) FILTER (WHERE source_name = 'xiaohongshu_webbridge') AS latest_xiaohongshu_date
                FROM raw_observations
                WHERE scope_id = scope.scope_id
                  AND quality_status = 'accepted'
            ) AS source_dates ON TRUE
            WHERE {where}
            ORDER BY scope.city, scope.mall_name, scope.category, scope.created_at
        """
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
            return [self._presentation(row, self._requirements(conn, row["scope_id"])) for row in rows]

    def get(self, scope_id: str) -> Optional[Dict[str, Any]]:
        rows = self._select("scope.scope_id = :scope_id", {"scope_id": scope_id})
        return rows[0] if rows else None

    def list(self, *, active_only: bool = True) -> List[Dict[str, Any]]:
        where = "scope.status = 'active'" if active_only else "1=1"
        return self._select(where, {})

    def source_requirements(self, scope_id: str) -> list[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            return [
                _serialize(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT * FROM scope_source_requirements
                        WHERE scope_id = :scope_id
                        ORDER BY source_name
                        """
                    ),
                    {"scope_id": scope_id},
                ).mappings().all()
            ]

    def register(
        self,
        *,
        city: str,
        mall_name: str,
        category: str,
        legacy_dataset_key: Optional[str] = None,
        data_origin: str = "external_webbridge",
    ) -> Dict[str, Any]:
        """登记范围，并同时写入旧 monitoring_scopes 兼容行。

        ``legacy_dataset_key`` 只帮助旧任务/旧表保持可读；它不会参与可信范围唯一性。
        """
        city, mall_name, category = (value.strip() for value in (city, mall_name, category))
        if not all((city, mall_name, category)):
            raise ValueError("城市、商场和品类不能为空")
        key = scope_key(city, mall_name, category)
        dataset_key = legacy_dataset_key or compatibility_dataset_key(city, mall_name, category)
        with self.client.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT scope_id FROM trusted_monitoring_scopes WHERE scope_key = :scope_key"),
                {"scope_key": key},
            ).mappings().first()
            if existing:
                scope_id = str(existing["scope_id"])
            else:
                scope_id = new_scope_id(city, mall_name, category)
                # 旧表拥有者不同，但应用用户具有 DML 权限；写入只为保持旧 FK/API 正常。
                conn.execute(
                    text(
                        """
                        INSERT INTO monitoring_scopes
                            (scope_id, brand_id, city, mall_name, category, data_origin)
                        VALUES
                            (:scope_id, :brand_id, :city, :mall_name, :category, :data_origin)
                        ON CONFLICT (scope_id) DO NOTHING
                        """
                    ),
                    {
                        "scope_id": scope_id,
                        "brand_id": dataset_key,
                        "city": city,
                        "mall_name": mall_name,
                        "category": category,
                        "data_origin": data_origin,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO trusted_monitoring_scopes
                            (scope_id, scope_key, city, mall_name, category, legacy_dataset_key, data_origin)
                        VALUES
                            (:scope_id, :scope_key, :city, :mall_name, :category, :legacy_dataset_key, :data_origin)
                        """
                    ),
                    {
                        "scope_id": scope_id,
                        "scope_key": key,
                        "city": city,
                        "mall_name": mall_name,
                        "category": category,
                        "legacy_dataset_key": dataset_key,
                        "data_origin": data_origin,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO legacy_scope_links
                            (legacy_scope_id, scope_id, legacy_dataset_key, link_status, evidence)
                        VALUES
                            (:scope_id, :scope_id, :legacy_dataset_key, 'canonical', CAST(:evidence AS jsonb))
                        ON CONFLICT (legacy_scope_id) DO NOTHING
                        """
                    ),
                    {
                        "scope_id": scope_id,
                        "legacy_dataset_key": dataset_key,
                        "evidence": _json({"method": "new_scope_registration"}),
                    },
                )
                for requirement in DEFAULT_SOURCE_REQUIREMENTS:
                    conn.execute(
                        text(
                            """
                            INSERT INTO scope_source_requirements
                                (requirement_id, scope_id, source_name, is_required, allow_empty, max_age_hours)
                            VALUES
                                (:requirement_id, :scope_id, :source_name, :is_required, :allow_empty, :max_age_hours)
                            ON CONFLICT (scope_id, source_name) DO NOTHING
                            """
                        ),
                        {
                            "requirement_id": f"req_{uuid4().hex}",
                            "scope_id": scope_id,
                            **requirement,
                        },
                    )
        created = self.get(scope_id)
        if not created:
            raise RuntimeError("监测范围创建后无法读取")
        return created


class CollectionRunRepository:
    """采集批次及来源运行。"""

    def __init__(self):
        self.client = PostgresClient()

    def create(
        self,
        *,
        scope_id: str,
        crawl_job_id: Optional[str],
        trigger_type: str,
        requested_brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        requirements = TrustedScopeRepository().source_requirements(scope_id)
        if not requirements:
            raise ValueError("监测范围没有启用的来源要求")
        run_id = f"collect_{uuid4().hex}"
        expected_sources = [
            {
                "source_name": item["source_name"],
                "required": bool(item["is_required"]),
                "allow_empty": bool(item["allow_empty"]),
                "max_age_hours": int(item["max_age_hours"]),
            }
            for item in requirements
            if item.get("is_active", True)
        ]
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO collection_runs
                        (collection_run_id, scope_id, crawl_job_id, trigger_type, expected_sources, requested_brand_id)
                    VALUES
                        (:collection_run_id, :scope_id, :crawl_job_id, :trigger_type,
                         CAST(:expected_sources AS jsonb), :requested_brand_id)
                    RETURNING *
                    """
                ),
                {
                    "collection_run_id": run_id,
                    "scope_id": scope_id,
                    "crawl_job_id": crawl_job_id,
                    "trigger_type": trigger_type,
                    "expected_sources": _json(expected_sources),
                    "requested_brand_id": requested_brand_id,
                },
            ).mappings().one()
        return _serialize(row)

    def get(self, collection_run_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM collection_runs WHERE collection_run_id = :collection_run_id"),
                {"collection_run_id": collection_run_id},
            ).mappings().first()
        return _serialize(row) if row else None

    def mark_collecting(self, collection_run_id: str) -> bool:
        with self.client.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE collection_runs
                    SET status = 'collecting', started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE collection_run_id = :collection_run_id
                      AND status IN ('draft', 'collecting', 'partial')
                    """
                ),
                {"collection_run_id": collection_run_id},
            )
        return bool(result.rowcount)

    def start_source_run(self, collection_run_id: str, source_name: str) -> Dict[str, Any]:
        source_run_id = f"source_{uuid4().hex}"
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO source_runs
                        (source_run_id, collection_run_id, source_name, status, started_at)
                    VALUES
                        (:source_run_id, :collection_run_id, :source_name, 'collecting', CURRENT_TIMESTAMP)
                    ON CONFLICT (collection_run_id, source_name) DO UPDATE SET
                        status = 'collecting', failure_reason = '', started_at = CURRENT_TIMESTAMP,
                        finished_at = NULL, updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """
                ),
                {
                    "source_run_id": source_run_id,
                    "collection_run_id": collection_run_id,
                    "source_name": source_name,
                },
            ).mappings().one()
        return _serialize(row)

    def finish_source_run(
        self,
        source_run_id: str,
        *,
        status: str,
        record_count: int,
        validated_count: int,
        raw_saved_count: int,
        external_run_id: Optional[str] = None,
        failure_reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE source_runs
                    SET status = :status,
                        record_count = :record_count,
                        validated_count = :validated_count,
                        raw_saved_count = :raw_saved_count,
                        external_run_id = COALESCE(:external_run_id, external_run_id),
                        failure_reason = :failure_reason,
                        metadata = CAST(:metadata AS jsonb),
                        finished_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE source_run_id = :source_run_id
                    RETURNING *
                    """
                ),
                {
                    "source_run_id": source_run_id,
                    "status": status,
                    "record_count": max(int(record_count), 0),
                    "validated_count": max(int(validated_count), 0),
                    "raw_saved_count": max(int(raw_saved_count), 0),
                    "external_run_id": external_run_id,
                    "failure_reason": failure_reason,
                    "metadata": _json(metadata or {}),
                },
            ).mappings().one()
        return _serialize(row)

    def list_for_collection(self, collection_run_id: str) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM source_runs
                    WHERE collection_run_id = :collection_run_id
                    ORDER BY source_name
                    """
                ),
                {"collection_run_id": collection_run_id},
            ).mappings().all()
        return [_serialize(row) for row in rows]

    def finish_collection(self, collection_run_id: str, *, status: str, failure_reason: str = "") -> None:
        with self.client.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE collection_runs
                    SET status = :status, failure_reason = :failure_reason,
                        finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE collection_run_id = :collection_run_id
                    """
                ),
                {
                    "collection_run_id": collection_run_id,
                    "status": status,
                    "failure_reason": failure_reason,
                },
            )


class RawObservationRepository:
    """新原始观测层；与旧原始表在同一事务中双写。"""

    @staticmethod
    def upsert(conn, observation: Dict[str, Any]) -> None:
        values = {
            "observation_id": observation["observation_id"],
            "scope_id": observation.get("scope_id"),
            "collection_run_id": observation.get("collection_run_id"),
            "source_run_id": observation.get("source_run_id"),
            "source_name": observation["source_name"],
            "record_type": observation["record_type"],
            "source_record_key": observation["source_record_key"],
            "source_url": observation.get("source_url") or "",
            "legacy_dataset_key": observation.get("legacy_dataset_key") or "",
            "observed_date": observation["observed_date"],
            "raw_category": observation.get("raw_category") or "",
            "standard_category": observation.get("standard_category") or "",
            "category_mapping_status": observation.get("category_mapping_status") or "pending",
            "candidate_brand_id": observation.get("candidate_brand_id"),
            "brand_id": observation.get("brand_id"),
            "store_id": observation.get("store_id"),
            "entity_mapping_status": observation.get("entity_mapping_status") or "pending",
            "mapping_confidence": observation.get("mapping_confidence"),
            "quality_status": observation.get("quality_status") or "accepted",
            "payload": _json(observation.get("payload") or {}),
        }
        conn.execute(
            text(
                """
                INSERT INTO raw_observations (
                    observation_id, scope_id, collection_run_id, source_run_id,
                    source_name, record_type, source_record_key, source_url, legacy_dataset_key,
                    observed_date, raw_category, standard_category, category_mapping_status,
                    candidate_brand_id, brand_id, store_id, entity_mapping_status,
                    mapping_confidence, quality_status, payload
                ) VALUES (
                    :observation_id, :scope_id, :collection_run_id, :source_run_id,
                    :source_name, :record_type, :source_record_key, :source_url, :legacy_dataset_key,
                    :observed_date, :raw_category, :standard_category, :category_mapping_status,
                    :candidate_brand_id, :brand_id, :store_id, :entity_mapping_status,
                    :mapping_confidence, :quality_status, CAST(:payload AS jsonb)
                )
                ON CONFLICT DO UPDATE SET
                    collection_run_id = COALESCE(EXCLUDED.collection_run_id, raw_observations.collection_run_id),
                    source_run_id = COALESCE(EXCLUDED.source_run_id, raw_observations.source_run_id),
                    source_url = EXCLUDED.source_url,
                    raw_category = EXCLUDED.raw_category,
                    standard_category = EXCLUDED.standard_category,
                    category_mapping_status = EXCLUDED.category_mapping_status,
                    candidate_brand_id = COALESCE(EXCLUDED.candidate_brand_id, raw_observations.candidate_brand_id),
                    payload = EXCLUDED.payload,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            values,
        )


class SnapshotRepository:
    """快照发布状态与来源覆盖计算。"""

    def __init__(self):
        self.client = PostgresClient()
        self.collection_runs = CollectionRunRepository()

    @staticmethod
    def _coverage(requirements: List[Dict[str, Any]], source_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        run_by_source = {str(run["source_name"]): run for run in source_runs}
        expected = [item for item in requirements if item.get("is_active", True)]
        results = []
        for requirement in expected:
            source_name = str(requirement["source_name"])
            run = run_by_source.get(source_name)
            results.append({
                "source_name": source_name,
                "required": bool(requirement["is_required"]),
                "allow_empty": bool(requirement["allow_empty"]),
                "status": run.get("status") if run else "skipped",
                "record_count": int(run.get("record_count") or 0) if run else 0,
                "validated_count": int(run.get("validated_count") or 0) if run else 0,
                "raw_saved_count": int(run.get("raw_saved_count") or 0) if run else 0,
                "observation_count": int(run.get("observation_count") or 0) if run else 0,
                "source_run_id": run.get("source_run_id") if run else None,
                "failure_reason": run.get("failure_reason") if run else "未执行",
                "metadata": run.get("metadata") if run else {},
                "observed_at": run.get("finished_at") if run else None,
            })
        # 保留配置外的来源；它们不可自动提升快照等级，但有审计价值。
        known_sources = {item["source_name"] for item in expected}
        for run in source_runs:
            if run["source_name"] not in known_sources:
                results.append({
                    "source_name": run["source_name"],
                    "required": False,
                    "allow_empty": False,
                    "status": run["status"],
                    "record_count": int(run.get("record_count") or 0),
                    "validated_count": int(run.get("validated_count") or 0),
                    "raw_saved_count": int(run.get("raw_saved_count") or 0),
                    "observation_count": int(run.get("observation_count") or 0),
                    "source_run_id": run["source_run_id"],
                    "failure_reason": run.get("failure_reason") or "",
                    "metadata": run.get("metadata") or {},
                    "observed_at": run.get("finished_at"),
                })
        return {
            "expected_count": len(expected),
            "executed_count": len(source_runs),
            "success_count": sum(item["status"] == "success" for item in results),
            "empty_validated_count": sum(item["status"] == "empty_validated" for item in results),
            "failed_count": sum(item["status"] == "failed" for item in results),
            "sources": results,
        }

    @staticmethod
    def _status(coverage: Dict[str, Any]) -> tuple[str, str, str, str]:
        sources = coverage["sources"]
        required = [item for item in sources if item["required"]]
        successful = [
            item for item in sources
            if item["status"] == "success" and item["observation_count"] > 0
        ]
        required_ready = all(
            (
                item["status"] == "success" and item["observation_count"] > 0
            ) or (
                item["status"] == "empty_validated" and item["allow_empty"]
            )
            for item in required
        )
        if not successful:
            return "failed", "F", "raw_only", "没有任何来源写入可验证的原始观测"
        source_names = {item["source_name"] for item in successful}
        if len(source_names) > 1:
            mode = "multi_source"
        elif "dianping_webbridge" in source_names:
            mode = "dianping_single_source"
        else:
            mode = "single_source"
        optional_problem = any(
            not item["required"] and item["status"] in {"failed", "skipped", "stale"}
            for item in sources
        )
        all_expected_success = bool(sources) and all(item["status"] == "success" for item in sources)
        if required_ready:
            return "ready", "A" if all_expected_success else ("C" if optional_problem else "B"), mode, ""
        return "partial", "C", mode, "必需来源缺失、失败或未通过空结果校验"

    def finalize_collection(self, collection_run_id: str) -> Dict[str, Any]:
        collection = self.collection_runs.get(collection_run_id)
        if not collection:
            raise ValueError("采集批次不存在")
        requirements = TrustedScopeRepository().source_requirements(str(collection["scope_id"]))
        source_runs = self.collection_runs.list_for_collection(collection_run_id)
        source_run_ids = [run["source_run_id"] for run in source_runs]
        if source_run_ids:
            with self.client.engine.connect() as conn:
                counts = conn.execute(
                    text(
                        """
                        SELECT source_run_id, COUNT(*) AS observation_count
                        FROM raw_observations
                        WHERE source_run_id = ANY(:source_run_ids)
                          AND quality_status = 'accepted'
                        GROUP BY source_run_id
                        """
                    ),
                    {"source_run_ids": source_run_ids},
                ).mappings().all()
            observed_counts = {
                str(row["source_run_id"]): int(row["observation_count"])
                for row in counts
            }
            for run in source_runs:
                run["observation_count"] = observed_counts.get(str(run["source_run_id"]), 0)
        coverage = self._coverage(requirements, source_runs)
        status, grade, data_mode, failure_reason = self._status(coverage)
        now = datetime.now()
        snapshot_id = f"snapshot_{hashlib.sha256(collection_run_id.encode('utf-8')).hexdigest()[:40]}"
        source_times = [
            datetime.fromisoformat(str(item["observed_at"]))
            for item in coverage["sources"]
            if item.get("observed_at")
        ]
        observed_at = max(source_times) if source_times else now
        freshness_status = "fresh"
        if source_times:
            max_age = max((int(item.get("max_age_hours") or 72) for item in requirements), default=72)
            freshness_status = "fresh" if observed_at >= now - timedelta(hours=max_age) else "stale"
        with self.client.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO data_snapshots (
                        snapshot_id, scope_id, collection_run_id, status, expected_sources,
                        source_coverage, observed_at, captured_at, freshness_status,
                        quality_grade, data_mode, failure_reason
                    ) VALUES (
                        :snapshot_id, :scope_id, :collection_run_id, :status, CAST(:expected_sources AS jsonb),
                        CAST(:source_coverage AS jsonb), :observed_at, CURRENT_TIMESTAMP, :freshness_status,
                        :quality_grade, :data_mode, :failure_reason
                    )
                    ON CONFLICT (collection_run_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        expected_sources = EXCLUDED.expected_sources,
                        source_coverage = EXCLUDED.source_coverage,
                        observed_at = EXCLUDED.observed_at,
                        captured_at = EXCLUDED.captured_at,
                        freshness_status = EXCLUDED.freshness_status,
                        quality_grade = EXCLUDED.quality_grade,
                        data_mode = EXCLUDED.data_mode,
                        failure_reason = EXCLUDED.failure_reason,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "snapshot_id": snapshot_id,
                    "scope_id": collection["scope_id"],
                    "collection_run_id": collection_run_id,
                    "status": status,
                    "expected_sources": _json(collection.get("expected_sources") or []),
                    "source_coverage": _json(coverage),
                    "observed_at": observed_at,
                    "freshness_status": freshness_status,
                    "quality_grade": grade,
                    "data_mode": data_mode,
                    "failure_reason": failure_reason,
                },
            )
            for item in coverage["sources"]:
                conn.execute(
                    text(
                        """
                        INSERT INTO snapshot_source_results (
                            snapshot_source_result_id, snapshot_id, source_run_id, source_name, is_required,
                            status, record_count, validated_count, observed_at, failure_reason, metadata
                        ) VALUES (
                            :id, :snapshot_id, :source_run_id, :source_name, :is_required,
                            :status, :record_count, :validated_count, :observed_at, :failure_reason,
                            CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (snapshot_id, source_name) DO UPDATE SET
                            source_run_id = EXCLUDED.source_run_id,
                            is_required = EXCLUDED.is_required,
                            status = EXCLUDED.status,
                            record_count = EXCLUDED.record_count,
                            validated_count = EXCLUDED.validated_count,
                            observed_at = EXCLUDED.observed_at,
                            failure_reason = EXCLUDED.failure_reason,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "id": f"snapshot_source_{uuid4().hex}",
                        "snapshot_id": snapshot_id,
                        "source_run_id": item["source_run_id"],
                        "source_name": item["source_name"],
                        "is_required": item["required"],
                        "status": item["status"],
                        "record_count": item["record_count"],
                        "validated_count": item["validated_count"],
                        "observed_at": item["observed_at"],
                        "failure_reason": item["failure_reason"] or "",
                        "metadata": _json(item["metadata"] or {}),
                    },
                )
        collection_status = "completed" if status == "ready" else status
        self.collection_runs.finish_collection(
            collection_run_id,
            status=collection_status,
            failure_reason=failure_reason,
        )
        return self.get(snapshot_id) or {"snapshot_id": snapshot_id, "status": status}

    def get(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT snapshot.*, scope.city, scope.mall_name, scope.category
                    FROM data_snapshots AS snapshot
                    JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = snapshot.scope_id
                    WHERE snapshot.snapshot_id = :snapshot_id
                    """
                ),
                {"snapshot_id": snapshot_id},
            ).mappings().first()
            if not row:
                return None
            item = _serialize(row)
            results = conn.execute(
                text(
                    """
                    SELECT * FROM snapshot_source_results
                    WHERE snapshot_id = :snapshot_id
                    ORDER BY source_name
                    """
                ),
                {"snapshot_id": snapshot_id},
            ).mappings().all()
        item["source_results"] = [_serialize(result) for result in results]
        return item

    def list(
        self,
        *,
        scope_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 200)}
        if scope_id:
            conditions.append("snapshot.scope_id = :scope_id")
            params["scope_id"] = scope_id
        if status:
            conditions.append("snapshot.status = :status")
            params["status"] = status
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT snapshot.*, scope.city, scope.mall_name, scope.category
                    FROM data_snapshots AS snapshot
                    JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = snapshot.scope_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY snapshot.observed_at DESC NULLS LAST, snapshot.created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [_serialize(row) for row in rows]

    def latest_released(self, scope_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT snapshot_id
                    FROM data_snapshots
                    WHERE scope_id = :scope_id AND status IN ('ready', 'published')
                    ORDER BY observed_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                    """
                ),
                {"scope_id": scope_id},
            ).mappings().first()
        return self.get(str(row["snapshot_id"])) if row else None

    def publish(self, snapshot_id: str) -> Dict[str, Any]:
        """显式发布一个 ready 快照，并将同范围旧 published 快照置为 superseded。"""
        with self.client.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT scope_id, status FROM data_snapshots
                    WHERE snapshot_id = :snapshot_id
                    FOR UPDATE
                    """
                ),
                {"snapshot_id": snapshot_id},
            ).mappings().first()
            if not row:
                raise ValueError("快照不存在")
            if row["status"] not in RELEASED_SNAPSHOT_STATUSES:
                raise ValueError("只有 ready 或已发布快照可以发布")
            conn.execute(
                text(
                    """
                    UPDATE data_snapshots
                    SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
                    WHERE scope_id = :scope_id AND status = 'published' AND snapshot_id <> :snapshot_id
                    """
                ),
                {"scope_id": row["scope_id"], "snapshot_id": snapshot_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE data_snapshots
                    SET status = 'published', published_at = COALESCE(published_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE snapshot_id = :snapshot_id
                    """
                ),
                {"snapshot_id": snapshot_id},
            )
        published = self.get(snapshot_id)
        if not published:
            raise RuntimeError("发布后无法读取快照")
        return published

    def source_health(self, scope_id: str) -> List[Dict[str, Any]]:
        snapshot = self.latest_released(scope_id)
        requirements = TrustedScopeRepository().source_requirements(scope_id)
        by_source = {row["source_name"]: row for row in (snapshot or {}).get("source_results", [])}
        return [
            {
                **requirement,
                "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
                "snapshot_status": snapshot.get("status") if snapshot else "unavailable",
                "result": by_source.get(requirement["source_name"]),
            }
            for requirement in requirements
        ]
