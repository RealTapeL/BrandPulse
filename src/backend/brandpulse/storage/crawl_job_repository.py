"""采集任务状态仓储：PostgreSQL 是任务状态的唯一事实来源。"""
import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class CrawlJobRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ("created_at", "updated_at", "started_at", "finished_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def set_rq_job(self, job_id: str, rq_job_id: str) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(text("""
                UPDATE crawl_jobs
                SET rq_job_id = :rq_job_id, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """), {"job_id": job_id, "rq_job_id": rq_job_id})
            conn.commit()

    def mark_running(self, job_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(text("""
                UPDATE crawl_jobs
                SET status = 'running',
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                    attempt_count = attempt_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id AND status IN ('pending', 'running')
            """), {"job_id": job_id})
            conn.commit()
        return bool(result.rowcount)

    def finish(self, job_id: str, *, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(text("""
                UPDATE crawl_jobs
                SET status = :status,
                    result = COALESCE(:result, result),
                    finished_at = CASE
                        WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP
                        ELSE finished_at
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """), {
                "job_id": job_id,
                "status": status,
                "result": json.dumps(result, ensure_ascii=False) if result is not None else None,
            })
            conn.commit()

    def prepare_retry(self, job_id: str, error: str) -> bool:
        """保留同一任务台账并回到 pending，供延迟重试重新领取。"""
        with self.client.engine.connect() as conn:
            result = conn.execute(text("""
                UPDATE crawl_jobs
                SET status = 'pending',
                    result = :result,
                    rq_job_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id AND status = 'running'
            """), {
                "job_id": job_id,
                "result": json.dumps({"retrying": True, "error": error}, ensure_ascii=False),
            })
            conn.commit()
        return bool(result.rowcount)

    def recover_stale_pending(self, stale_minutes: int = 10) -> int:
        with self.client.engine.connect() as conn:
            result = conn.execute(text("""
                UPDATE crawl_jobs
                SET status = 'failed',
                    result = '{"error":"任务创建后未成功进入队列，已自动终止，请重新提交"}',
                    updated_at = CURRENT_TIMESTAMP,
                    finished_at = CURRENT_TIMESTAMP
                WHERE status = 'pending'
                  AND rq_job_id IS NULL
                  AND created_at < CURRENT_TIMESTAMP - (:stale_minutes * INTERVAL '1 minute')
            """), {"stale_minutes": stale_minutes})
            conn.commit()
        return result.rowcount or 0

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM crawl_jobs WHERE job_id = :job_id"), {"job_id": job_id}).mappings().first()
        return self._row_to_dict(row) if row else None

    def list(self, *, brand_id: Optional[str], status: Optional[str], limit: int, offset: int) -> Dict[str, Any]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if brand_id:
            conditions.append("brand_id = :brand_id")
            params["brand_id"] = brand_id
        if status:
            conditions.append("status = :status")
            params["status"] = status
        where = " AND ".join(conditions)
        with self.client.engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM crawl_jobs WHERE {where}"), params).scalar_one()
            rows = conn.execute(text(f"""
                SELECT * FROM crawl_jobs WHERE {where}
                ORDER BY created_at DESC LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        return {"items": [self._row_to_dict(row) for row in rows], "total": total}
