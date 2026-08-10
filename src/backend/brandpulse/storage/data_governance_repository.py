"""数据治理仓储：别名、质量问题、扫描记录和采集血缘。"""
import json
from datetime import datetime
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class DataGovernanceRepository:
    def __init__(self):
        self.client = PostgresClient()

    def seed_brand_aliases(self, conn) -> int:
        """把明确的品牌主数据字段补入别名表；不会处理外部记录。"""
        rows = conn.execute(text("""
            SELECT brand_id, brand_name_cn, brand_name_en, search_keywords
            FROM brands WHERE is_active IS DISTINCT FROM FALSE
        """)).mappings().all()
        count = 0
        from brandpulse.data_governance.normalizer import normalize_text, stable_key

        for row in rows:
            values = [
                (row["brand_name_cn"], "brand_name_cn", 1.0),
                (row.get("brand_name_en"), "brand_name_en", 1.0),
                (row.get("search_keywords"), "search_keywords", 0.9),
            ]
            for alias_text, source_name, confidence in values:
                normalized = normalize_text(alias_text)
                if not normalized:
                    continue
                result = conn.execute(text("""
                    INSERT INTO brand_aliases (
                        alias_id, brand_id, alias_text, normalized_alias,
                        source_name, status, confidence, note
                    ) VALUES (
                        :alias_id, :brand_id, :alias_text, :normalized_alias,
                        :source_name, 'confirmed', :confidence, :note
                    )
                    ON CONFLICT (brand_id, normalized_alias, source_name) DO NOTHING
                """), {
                    "alias_id": f"seed_{stable_key(row['brand_id'], source_name, alias_text)[:40]}",
                    "brand_id": row["brand_id"],
                    "alias_text": alias_text,
                    "normalized_alias": normalized,
                    "source_name": "brands",
                    "confidence": confidence,
                    "note": f"由 brands.{source_name} 初始化",
                })
                count += result.rowcount or 0
        return count

    def sync_store_aliases(self, conn) -> int:
        """同步门店主数据和点评原始记录的别名，不自动做模糊归属。"""
        from brandpulse.data_governance.normalizer import normalize_address, normalize_text, stable_key

        stores = conn.execute(text("""
            SELECT store_id, brand_id, store_name, city, mall_name, address, data_source
            FROM stores
            WHERE NULLIF(TRIM(COALESCE(store_name, '')), '') IS NOT NULL
        """)).mappings().all()
        count = 0
        for row in stores:
            raw_name = row["store_name"] or ""
            normalized = normalize_text(raw_name)
            city = row["city"] or ""
            mall = row["mall_name"] or ""
            address = row["address"] or ""
            result = conn.execute(text("""
                INSERT INTO store_aliases (
                    alias_id, store_id, brand_id, raw_store_name,
                    normalized_store_name, city, mall_name, address,
                    source_name, match_status, match_method, confidence, note
                ) VALUES (
                    :alias_id, :store_id, :brand_id, :raw_store_name,
                    :normalized_store_name, :city, :mall_name, :address,
                    :source_name, 'confirmed', 'canonical_store', 1.0, :note
                )
                ON CONFLICT (source_name, normalized_store_name, city, mall_name, address)
                DO UPDATE SET
                    store_id = EXCLUDED.store_id,
                    brand_id = EXCLUDED.brand_id,
                    match_status = 'confirmed',
                    match_method = 'canonical_store',
                    confidence = 1.0,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "alias_id": f"store_{stable_key('stores', row['store_id'])[:40]}",
                "store_id": row["store_id"],
                "brand_id": row["brand_id"],
                "raw_store_name": raw_name,
                "normalized_store_name": normalized,
                "city": city,
                "mall_name": mall,
                "address": address,
                "source_name": row.get("data_source") or "stores",
                "note": "来自 stores 主数据",
            })
            count += result.rowcount or 0

        # 点评门店可能没有真实品牌/门店 ID。先保存待匹配别名，供人工确认，绝不写回错误的 store_id。
        dp_rows = conn.execute(text("""
            SELECT shop_name, brand_id, city, place, source_url
            FROM dp_shop_metrics
            GROUP BY shop_name, brand_id, city, place, source_url
        """)).mappings().all()
        for row in dp_rows:
            raw_name = row["shop_name"] or ""
            normalized = normalize_text(raw_name)
            city = row["city"] or ""
            mall = row["place"] or ""
            # PostgreSQL 不依赖自定义函数；匹配使用 Python 标准化后的已有 alias 表。
            candidates = conn.execute(text("""
                SELECT DISTINCT store_id, brand_id
                FROM store_aliases
                WHERE normalized_store_name = :normalized
                  AND city = :city
                  AND (mall_name = :mall OR mall_name = '')
                  AND match_status = 'confirmed'
            """), {"normalized": normalized, "city": city, "mall": mall}).mappings().all()
            store_id = candidates[0]["store_id"] if len(candidates) == 1 else None
            brand_id = candidates[0]["brand_id"] if len(candidates) == 1 else None
            status = "confirmed" if store_id else "pending"
            method = "exact_name_city_mall" if store_id else "unmatched"
            result = conn.execute(text("""
                INSERT INTO store_aliases (
                    alias_id, store_id, brand_id, raw_store_name,
                    normalized_store_name, city, mall_name, address,
                    source_name, match_status, match_method, confidence, note
                ) VALUES (
                    :alias_id, :store_id, :brand_id, :raw_store_name,
                    :normalized_store_name, :city, :mall_name, '',
                    'dianping_webbridge', :match_status, :match_method,
                    :confidence, :note
                )
                ON CONFLICT (source_name, normalized_store_name, city, mall_name, address)
                DO UPDATE SET
                    store_id = CASE
                        WHEN store_aliases.match_method = 'manual' THEN store_aliases.store_id
                        ELSE COALESCE(store_aliases.store_id, EXCLUDED.store_id)
                    END,
                    brand_id = CASE
                        WHEN store_aliases.match_method = 'manual' THEN store_aliases.brand_id
                        ELSE COALESCE(store_aliases.brand_id, EXCLUDED.brand_id)
                    END,
                    match_status = CASE
                        WHEN store_aliases.match_method = 'manual' THEN store_aliases.match_status
                        WHEN store_aliases.match_status = 'confirmed' THEN 'confirmed'
                        ELSE EXCLUDED.match_status
                    END,
                    match_method = CASE
                        WHEN store_aliases.match_method = 'manual' THEN store_aliases.match_method
                        WHEN store_aliases.match_status = 'confirmed' THEN store_aliases.match_method
                        ELSE EXCLUDED.match_method
                    END,
                    confidence = CASE
                        WHEN store_aliases.match_method = 'manual' THEN store_aliases.confidence
                        ELSE COALESCE(store_aliases.confidence, EXCLUDED.confidence)
                    END,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "alias_id": f"dp_{stable_key('dianping_webbridge', raw_name, city, mall)[:40]}",
                "store_id": store_id,
                "brand_id": brand_id,
                "raw_store_name": raw_name,
                "normalized_store_name": normalized,
                "city": city,
                "mall_name": mall,
                "match_status": status,
                "match_method": method,
                "confidence": 1.0 if store_id else None,
                "note": "点评原始门店名；未确认前不归属到 stores",
            })
            count += result.rowcount or 0
        return count

    def upsert_issue(self, conn, issue: Dict[str, Any]) -> None:
        conn.execute(text("""
            INSERT INTO data_quality_issues (
                issue_id, issue_key, entity_type, entity_key, source_name,
                issue_type, severity, status, message, details, first_seen, last_seen
            ) VALUES (
                :issue_id, :issue_key, :entity_type, :entity_key, :source_name,
                :issue_type, :severity, 'open', :message, CAST(:details AS JSONB),
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (issue_key) DO UPDATE SET
                entity_type = EXCLUDED.entity_type,
                entity_key = EXCLUDED.entity_key,
                source_name = EXCLUDED.source_name,
                issue_type = EXCLUDED.issue_type,
                severity = EXCLUDED.severity,
                message = EXCLUDED.message,
                details = EXCLUDED.details,
                last_seen = CURRENT_TIMESTAMP,
                status = CASE
                    WHEN data_quality_issues.status IN ('resolved', 'ignored') THEN 'open'
                    ELSE data_quality_issues.status
                END,
                resolved_at = CASE
                    WHEN data_quality_issues.status IN ('resolved', 'ignored') THEN NULL
                    ELSE data_quality_issues.resolved_at
                END
        """), {
            **issue,
            "details": json.dumps(issue.get("details", {}), ensure_ascii=False),
        })

    def list_issues(self, *, status: Optional[str], severity: Optional[str], limit: int, offset: int) -> Dict[str, Any]:
        where = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            where.append("status = :status")
            params["status"] = status
        if severity:
            where.append("severity = :severity")
            params["severity"] = severity
        condition = " AND ".join(where)
        with self.client.engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM data_quality_issues WHERE {condition}"), params).scalar_one()
            rows = conn.execute(text(f"""
                SELECT issue_id, issue_key, entity_type, entity_key, source_name,
                       issue_type, severity, status, message, details,
                       first_seen, last_seen, resolved_at, resolution_note
                FROM data_quality_issues
                WHERE {condition}
                ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'error' THEN 2
                                      WHEN 'warning' THEN 3 ELSE 4 END,
                         last_seen DESC
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        return {"items": [dict(row) for row in rows], "total": total}

    def update_issue(self, issue_id: str, status: str, resolution_note: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE data_quality_issues
                SET status = :status,
                    resolution_note = :resolution_note,
                    resolved_at = CASE WHEN :status IN ('resolved', 'ignored') THEN CURRENT_TIMESTAMP ELSE NULL END
                WHERE issue_id = :issue_id
                RETURNING *
            """), {"issue_id": issue_id, "status": status, "resolution_note": resolution_note}).mappings().first()
        return dict(row) if row else None

    def list_brand_aliases(self, *, brand_id: Optional[str], status: Optional[str]) -> list[Dict[str, Any]]:
        where = ["1=1"]
        params: Dict[str, Any] = {}
        if brand_id:
            where.append("brand_id = :brand_id")
            params["brand_id"] = brand_id
        if status:
            where.append("status = :status")
            params["status"] = status
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT alias_id, brand_id, alias_text, normalized_alias, source_name,
                       status, confidence, note, created_at, updated_at
                FROM brand_aliases WHERE {' AND '.join(where)}
                ORDER BY brand_id, alias_text
            """), params).mappings().all()
        return [dict(row) for row in rows]

    def create_brand_alias(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from brandpulse.data_governance.normalizer import normalize_text, stable_key

        alias_text = str(payload["alias_text"]).strip()
        normalized = normalize_text(alias_text)
        if not normalized:
            raise ValueError("alias_text 标准化后为空")
        data = {
            "alias_id": f"manual_{stable_key(payload['brand_id'], alias_text, payload.get('source_name', 'manual'))[:40]}",
            "brand_id": payload["brand_id"],
            "alias_text": alias_text,
            "normalized_alias": normalized,
            "source_name": payload.get("source_name") or "manual",
            "status": payload.get("status") or "confirmed",
            "confidence": payload.get("confidence"),
            "note": payload.get("note") or "",
        }
        with self.client.engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO brand_aliases (
                    alias_id, brand_id, alias_text, normalized_alias,
                    source_name, status, confidence, note
                ) VALUES (
                    :alias_id, :brand_id, :alias_text, :normalized_alias,
                    :source_name, :status, :confidence, :note
                )
                ON CONFLICT (brand_id, normalized_alias, source_name)
                DO UPDATE SET
                    alias_text = EXCLUDED.alias_text,
                    status = EXCLUDED.status,
                    confidence = EXCLUDED.confidence,
                    note = EXCLUDED.note,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
            """), data).mappings().one()
        return dict(row)

    def list_store_aliases(self, *, status: Optional[str], limit: int, offset: int) -> Dict[str, Any]:
        where = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            where.append("match_status = :status")
            params["status"] = status
        condition = " AND ".join(where)
        with self.client.engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM store_aliases WHERE {condition}"), params).scalar_one()
            rows = conn.execute(text(f"""
                SELECT alias_id, store_id, brand_id, raw_store_name,
                       normalized_store_name, city, mall_name, address,
                       source_name, match_status, match_method, confidence, note,
                       created_at, updated_at
                FROM store_aliases WHERE {condition}
                ORDER BY match_status, source_name, raw_store_name
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        return {"items": [dict(row) for row in rows], "total": total}

    def list_store_options(self, *, q: Optional[str], city: Optional[str], limit: int) -> list[Dict[str, Any]]:
        where = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}
        if q:
            where.append("(store_name ILIKE :q OR address ILIKE :q)")
            params["q"] = f"%{q}%"
        if city:
            where.append("city = :city")
            params["city"] = city
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT store_id, brand_id, store_name, city, mall_name, address
                FROM stores WHERE {' AND '.join(where)}
                ORDER BY store_name, store_id LIMIT :limit
            """), params).mappings().all()
        return [dict(row) for row in rows]

    def update_store_alias(self, alias_id: str, *, store_id: Optional[str], status: str, note: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.begin() as conn:
            if store_id:
                exists = conn.execute(text("SELECT 1 FROM stores WHERE store_id = :store_id"), {"store_id": store_id}).first()
                if not exists:
                    raise ValueError("store_id 不存在，不能确认门店匹配")
            if store_id:
                row = conn.execute(text("""
                    UPDATE store_aliases AS alias
                    SET store_id = :store_id,
                        brand_id = store.brand_id,
                        match_status = :status,
                        match_method = 'manual',
                        confidence = 1.0,
                        note = :note,
                        updated_at = CURRENT_TIMESTAMP
                    FROM stores AS store
                    WHERE alias.alias_id = :alias_id AND store.store_id = :store_id
                    RETURNING alias.*
                """), {"alias_id": alias_id, "store_id": store_id, "status": status, "note": note}).mappings().first()
            else:
                row = conn.execute(text("""
                    UPDATE store_aliases
                    SET store_id = NULL, brand_id = NULL, match_status = :status,
                        match_method = 'manual', confidence = NULL,
                        note = :note, updated_at = CURRENT_TIMESTAMP
                    WHERE alias_id = :alias_id
                    RETURNING *
                """), {"alias_id": alias_id, "status": status, "note": note}).mappings().first()
        return dict(row) if row else None

    def lineage(self, *, source_name: Optional[str], limit: int) -> list[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        where = "1=1"
        if source_name:
            where = "source_name = :source_name"
            params["source_name"] = source_name
        with self.client.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT log_id, run_id, trace_id, source_name, source_type,
                       entity_type, entity_id, record_count, status, error_message,
                       executed_at, started_at, finished_at, metadata
                FROM data_source_logs
                WHERE {where}
                ORDER BY executed_at DESC LIMIT :limit
            """), params).mappings().all()
        return [dict(row) for row in rows]

    def summary(self) -> Dict[str, Any]:
        with self.client.engine.connect() as conn:
            issue_counts = conn.execute(text("""
                SELECT status, severity, COUNT(*) AS count
                FROM data_quality_issues GROUP BY status, severity
                ORDER BY status, severity
            """)).mappings().all()
            alias_counts = conn.execute(text("""
                SELECT 'brand' AS kind, status, COUNT(*) AS count FROM brand_aliases GROUP BY status
                UNION ALL
                SELECT 'store' AS kind, match_status AS status, COUNT(*) AS count FROM store_aliases GROUP BY match_status
            """)).mappings().all()
            latest_scan = conn.execute(text("""
                SELECT scan_id, trigger_type, status, issue_count, summary, started_at, finished_at
                FROM data_quality_scan_runs ORDER BY started_at DESC LIMIT 1
            """)).mappings().first()
            current = conn.execute(text("""
                SELECT
                  (SELECT COUNT(*) FROM brands) AS brands,
                  (SELECT COUNT(*) FROM stores) AS stores,
                  (SELECT COUNT(*) FROM dp_shop_metrics) AS dp_shop_metrics,
                  (SELECT COUNT(*) FROM xhs_notes) AS xhs_notes,
                  (SELECT COUNT(*) FROM data_source_logs) AS lineage_logs,
                  (SELECT COUNT(*) FROM data_quality_issues WHERE status IN ('open','acknowledged')) AS open_issues
            """)).mappings().one()
        return {
            "records": dict(current),
            "issue_counts": [dict(row) for row in issue_counts],
            "alias_counts": [dict(row) for row in alias_counts],
            "latest_scan": dict(latest_scan) if latest_scan else None,
        }
