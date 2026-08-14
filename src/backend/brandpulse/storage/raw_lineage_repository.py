"""原始记录级血缘仓储。"""

import json
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text


class RawLineageRepository:
    @staticmethod
    def record(
        conn,
        *,
        run_id: str,
        source_name: str,
        record_type: str,
        record_key: str,
        crawl_date: str,
        crawl_job_id: Optional[str] = None,
        scope_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """在原始记录事务中同步登记一次来源观察。"""
        conn.execute(text("""
            INSERT INTO raw_record_lineage (
                lineage_id, run_id, crawl_job_id, scope_id, source_name,
                record_type, record_key, crawl_date, metadata
            ) VALUES (
                :lineage_id, :run_id, :crawl_job_id, :scope_id, :source_name,
                :record_type, :record_key, :crawl_date, CAST(:metadata AS jsonb)
            )
            ON CONFLICT (run_id, record_type, record_key) DO UPDATE SET
                crawl_job_id = COALESCE(EXCLUDED.crawl_job_id, raw_record_lineage.crawl_job_id),
                scope_id = COALESCE(EXCLUDED.scope_id, raw_record_lineage.scope_id),
                metadata = EXCLUDED.metadata
        """), {
            "lineage_id": f"rawlin_{uuid4().hex}",
            "run_id": run_id,
            "crawl_job_id": crawl_job_id,
            "scope_id": scope_id,
            "source_name": source_name,
            "record_type": record_type,
            "record_key": record_key,
            "crawl_date": crawl_date,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        })
