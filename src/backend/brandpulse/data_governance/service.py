"""数据治理服务。

扫描坚持保守原则：可以确认的才自动标记 confirmed，无法确认的记录进入 pending/open，
不修改现有原始数据的品牌归属。
"""
from collections import Counter, defaultdict
from datetime import datetime
import json
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.data_governance.normalizer import normalize_address, normalize_text, stable_key
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.storage.data_governance_repository import DataGovernanceRepository


class DataGovernanceService:
    def __init__(self):
        self.client = PostgresClient()
        self.repo = DataGovernanceRepository()

    @staticmethod
    def _issue(
        *,
        entity_type: str,
        entity_key: str,
        source_name: str,
        issue_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        issue_key = stable_key(entity_type, entity_key, source_name, issue_type)
        return {
            "issue_id": f"issue_{issue_key[:40]}",
            "issue_key": issue_key,
            "entity_type": entity_type,
            "entity_key": entity_key,
            "source_name": source_name,
            "issue_type": issue_type,
            "severity": severity,
            "message": message,
            "details": details or {},
        }

    def record_source_log(
        self,
        *,
        run_id: str,
        trace_id: Optional[str],
        source_name: str,
        source_type: str,
        entity_type: str,
        entity_id: Optional[str],
        record_count: int,
        status: str,
        error_message: str = "",
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        log_id = f"log_{uuid4().hex}"
        self.client.execute("""
            INSERT INTO data_source_logs (
                log_id, run_id, trace_id, source_name, source_type,
                entity_type, entity_id, record_count, status, error_message,
                executed_at, started_at, finished_at, metadata
            ) VALUES (
                :log_id, :run_id, :trace_id, :source_name, :source_type,
                :entity_type, :entity_id, :record_count, :status, :error_message,
                CURRENT_TIMESTAMP, :started_at, :finished_at, CAST(:metadata AS JSONB)
            )
        """, {
            "log_id": log_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "source_name": source_name,
            "source_type": source_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "record_count": record_count,
            "status": status,
            "error_message": error_message,
            "started_at": started_at,
            "finished_at": finished_at,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        })
        return log_id

    def scan(self, trigger_type: str = "manual") -> Dict[str, Any]:
        scan_id = f"scan_{uuid4().hex}"
        issues: list[Dict[str, Any]] = []
        started_at = datetime.now()

        try:
            with self.client.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO data_quality_scan_runs (scan_id, trigger_type, status, started_at)
                    VALUES (:scan_id, :trigger_type, 'running', :started_at)
                """), {"scan_id": scan_id, "trigger_type": trigger_type, "started_at": started_at})
                self.repo.seed_brand_aliases(conn)
                self.repo.sync_store_aliases(conn)

                brands = conn.execute(text("""
                    SELECT brand_id, brand_name_cn, brand_name_en, search_keywords
                    FROM brands
                """)).mappings().all()
                brand_ids = {row["brand_id"] for row in brands}

                # 同一个 confirmed 别名对应多个品牌时，禁止自动解析。
                for row in conn.execute(text("""
                    SELECT normalized_alias, array_agg(DISTINCT brand_id) AS brand_ids,
                           COUNT(DISTINCT brand_id) AS brand_count
                    FROM brand_aliases
                    WHERE status = 'confirmed'
                    GROUP BY normalized_alias
                    HAVING COUNT(DISTINCT brand_id) > 1
                """)).mappings().all():
                    issues.append(self._issue(
                        entity_type="brand_alias",
                        entity_key=row["normalized_alias"],
                        source_name="brand_aliases",
                        issue_type="conflicting_brand_alias",
                        severity="error",
                        message=f"标准化别名 {row['normalized_alias']} 同时指向多个品牌，禁止自动归属",
                        details={"brand_ids": list(row["brand_ids"])},
                    ))

                stores = conn.execute(text("""
                    SELECT store_id, brand_id, store_name, city, mall_name, address,
                           longitude, latitude, source_url
                    FROM stores
                """)).mappings().all()
                store_groups: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
                for row in stores:
                    key = (
                        normalize_text(row["store_name"]),
                        normalize_text(row["city"]),
                        normalize_text(row["mall_name"]),
                        normalize_address(row["address"]),
                    )
                    if all(key):
                        store_groups[key].append(row["store_id"])
                    if row["brand_id"] not in brand_ids:
                        issues.append(self._issue(
                            entity_type="store", entity_key=row["store_id"], source_name="stores",
                            issue_type="invalid_brand_reference", severity="error",
                            message=f"门店 {row['store_id']} 引用了不存在的品牌 {row['brand_id']}",
                            details={"brand_id": row["brand_id"]},
                        ))
                    if not (row["store_name"] or "").strip():
                        issues.append(self._issue(
                            entity_type="store", entity_key=row["store_id"], source_name="stores",
                            issue_type="missing_store_name", severity="error",
                            message=f"门店 {row['store_id']} 缺少门店名称",
                        ))
                    if not (row["city"] or "").strip():
                        issues.append(self._issue(
                            entity_type="store", entity_key=row["store_id"], source_name="stores",
                            issue_type="missing_city", severity="warning",
                            message=f"门店 {row['store_id']} 缺少城市",
                        ))
                    if (row["longitude"] is None) != (row["latitude"] is None):
                        issues.append(self._issue(
                            entity_type="store", entity_key=row["store_id"], source_name="stores",
                            issue_type="incomplete_coordinates", severity="warning",
                            message=f"门店 {row['store_id']} 的经纬度只填写了一项",
                        ))

                for key, store_ids in store_groups.items():
                    if len(store_ids) > 1:
                        issues.append(self._issue(
                            entity_type="store", entity_key="|".join(sorted(store_ids)), source_name="stores",
                            issue_type="duplicate_store_identity", severity="error",
                            message=f"发现 {len(store_ids)} 条可能重复的门店主数据，需要人工确认",
                            details={"identity": list(key), "store_ids": sorted(store_ids)},
                        ))

                dp_unknown = conn.execute(text("""
                    SELECT brand_id, COUNT(*) AS count
                    FROM dp_shop_metrics
                    WHERE NOT EXISTS (SELECT 1 FROM brands b WHERE b.brand_id = dp_shop_metrics.brand_id)
                      AND NOT EXISTS (
                          SELECT 1 FROM monitoring_scopes scope
                          WHERE scope.brand_id = dp_shop_metrics.brand_id
                            AND scope.city = dp_shop_metrics.city
                            AND scope.mall_name = COALESCE(dp_shop_metrics.place, '')
                      )
                    GROUP BY brand_id
                """)).mappings().all()
                for row in dp_unknown:
                    issues.append(self._issue(
                        entity_type="dp_shop_metrics", entity_key=row["brand_id"], source_name="dianping_webbridge",
                        issue_type="unresolved_dataset_brand", severity="warning",
                        message=(f"点评数据使用 {row['brand_id']} 数据集 ID，不对应 brands 中的真实品牌；"
                                 "当前只能作为商场×品类公开竞品数据，不能直接归入品牌指标"),
                        details={"brand_id": row["brand_id"], "record_count": row["count"]},
                    ))
                dp_invalid = conn.execute(text("""
                    SELECT COUNT(*) AS count FROM dp_shop_metrics
                    WHERE (score IS NOT NULL AND (score < 0 OR score > 5))
                       OR (review_count IS NOT NULL AND review_count < 0)
                """)).scalar_one()
                if dp_invalid:
                    issues.append(self._issue(
                        entity_type="dp_shop_metrics", entity_key="range", source_name="dianping_webbridge",
                        issue_type="invalid_metric_range", severity="error",
                        message=f"点评原始指标存在 {dp_invalid} 条评分或评价数越界记录",
                        details={"count": dp_invalid},
                    ))
                dp_missing_url = conn.execute(text("""
                    SELECT COUNT(*) FROM dp_shop_metrics WHERE NULLIF(TRIM(COALESCE(source_url, '')), '') IS NULL
                """)).scalar_one()
                if dp_missing_url:
                    issues.append(self._issue(
                        entity_type="dp_shop_metrics", entity_key="source_url", source_name="dianping_webbridge",
                        issue_type="missing_source_url", severity="warning",
                        message=f"点评原始数据有 {dp_missing_url} 条记录缺少来源链接",
                        details={"count": dp_missing_url},
                    ))

                xhs_unknown = conn.execute(text("""
                    SELECT brand_id, COUNT(*) AS count
                    FROM xhs_notes
                    WHERE NOT EXISTS (SELECT 1 FROM brands b WHERE b.brand_id = xhs_notes.brand_id)
                      AND NOT EXISTS (
                          SELECT 1 FROM monitoring_scopes scope
                          WHERE scope.brand_id = xhs_notes.brand_id
                            AND scope.city = xhs_notes.city
                            AND scope.mall_name = COALESCE(xhs_notes.mall_name, '')
                      )
                    GROUP BY brand_id
                """)).mappings().all()
                for row in xhs_unknown:
                    issues.append(self._issue(
                        entity_type="xhs_notes", entity_key=row["brand_id"], source_name="xiaohongshu_webbridge",
                        issue_type="unresolved_dataset_brand", severity="warning",
                        message=(f"小红书数据使用 {row['brand_id']} 数据集 ID，不对应 brands 中的真实品牌；"
                                 "当前只能作为商场×品类公开讨论数据"),
                        details={"brand_id": row["brand_id"], "record_count": row["count"]},
                    ))
                xhs_invalid = conn.execute(text("""
                    SELECT COUNT(*) FROM xhs_notes WHERE likes IS NOT NULL AND likes < 0
                """)).scalar_one()
                if xhs_invalid:
                    issues.append(self._issue(
                        entity_type="xhs_notes", entity_key="likes", source_name="xiaohongshu_webbridge",
                        issue_type="invalid_metric_range", severity="error",
                        message=f"小红书原始数据有 {xhs_invalid} 条点赞数为负的记录",
                        details={"count": xhs_invalid},
                    ))

                pending_aliases = conn.execute(text("""
                    SELECT source_name, city, mall_name, COUNT(*) AS count
                    FROM store_aliases WHERE match_status = 'pending'
                    GROUP BY source_name, city, mall_name
                """)).mappings().all()
                for row in pending_aliases:
                    scope = f"{row['source_name']}|{row['city']}|{row['mall_name']}"
                    issues.append(self._issue(
                        entity_type="store_alias", entity_key=scope, source_name=row["source_name"],
                        issue_type="pending_store_match", severity="warning",
                        message=f"有 {row['count']} 条外部门店别名尚未匹配到 stores 主数据",
                        details={"city": row["city"], "mall_name": row["mall_name"], "count": row["count"]},
                    ))

                for issue in issues:
                    self.repo.upsert_issue(conn, issue)

                # 本服务执行的是全量扫描：本次扫描范围内不再出现的问题自动结案，
                # 但保留历史记录、首次发现时间和处理备注，便于追溯治理效果。
                conn.execute(text("""
                    UPDATE data_quality_issues
                    SET status = 'resolved',
                        resolved_at = CURRENT_TIMESTAMP,
                        resolution_note = CASE
                            WHEN NULLIF(TRIM(resolution_note), '') IS NULL
                            THEN '全量质量扫描未再次发现'
                            ELSE resolution_note
                        END
                    WHERE status IN ('open', 'acknowledged')
                      AND last_seen < :started_at
                """), {"started_at": started_at})

                severity_counts = Counter(issue["severity"] for issue in issues)
                summary = {
                    "issue_count": len(issues),
                    "severity_counts": dict(severity_counts),
                    "records_checked": {
                        "brands": len(brands),
                        "stores": len(stores),
                        "dp_shop_metrics": conn.execute(text("SELECT COUNT(*) FROM dp_shop_metrics")).scalar_one(),
                        "xhs_notes": conn.execute(text("SELECT COUNT(*) FROM xhs_notes")).scalar_one(),
                    },
                }
                conn.execute(text("""
                    UPDATE data_quality_scan_runs
                    SET status = 'completed', issue_count = :issue_count,
                        summary = CAST(:summary AS JSONB), finished_at = CURRENT_TIMESTAMP
                    WHERE scan_id = :scan_id
                """), {
                    "scan_id": scan_id,
                    "issue_count": len(issues),
                    "summary": json.dumps(summary, ensure_ascii=False),
                })
            return {"scan_id": scan_id, "status": "completed", **summary}
        except Exception as exc:
            with self.client.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE data_quality_scan_runs
                    SET status = 'failed', error_message = :error, finished_at = CURRENT_TIMESTAMP
                    WHERE scan_id = :scan_id
                """), {"scan_id": scan_id, "error": str(exc)})
            raise
