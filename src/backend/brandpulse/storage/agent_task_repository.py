"""Agent 任务持久化，支持前端在请求结束后继续轮询状态。"""
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def _rq_job_state(rq_job_id: str) -> tuple[str, Optional[str]]:
    """读取 RQ 的真实状态；Redis 暂时不可用时不误判业务任务。"""
    from redis.exceptions import RedisError
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from brandpulse.agent.queue import get_agent_queue

    try:
        job = Job.fetch(rq_job_id, connection=get_agent_queue().connection)
        raw_status = job.get_status(refresh=True)
        status = getattr(raw_status, "value", str(raw_status))
        error = (job.exc_info or "").strip() or None
        return status, error
    except NoSuchJobError:
        return "missing", "RQ 中不存在对应任务"
    except RedisError as exc:
        logger.warning("Agent 任务状态对账暂不可用: %s", exc)
        return "unavailable", None


class AgentTaskRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["id"] = item.pop("task_id")
        item["input"] = item.pop("prompt")
        item["logs"] = item.get("logs") or []
        item["context"] = item.get("context") or {}
        for key in ("created_at", "updated_at", "started_at", "finished_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        prompt: str,
        context: Dict[str, Any],
        *,
        actor_id: str,
        actor_username: str,
        actor_role: str,
        allowed_tools: list[str],
    ) -> Dict[str, Any]:
        task_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                INSERT INTO agent_tasks (
                    task_id, prompt, context, status, logs,
                    actor_id, actor_username, actor_role, allowed_tools
                )
                VALUES (
                    :task_id, :prompt, CAST(:context AS jsonb), 'pending', '[]'::jsonb,
                    :actor_id, :actor_username, :actor_role, CAST(:allowed_tools AS jsonb)
                )
                RETURNING *
            """), {
                "task_id": task_id,
                "prompt": prompt,
                "context": json.dumps(context, ensure_ascii=False),
                "actor_id": actor_id,
                "actor_username": actor_username,
                "actor_role": actor_role,
                "allowed_tools": json.dumps(sorted(set(allowed_tools)), ensure_ascii=False),
            }).mappings().one()
            conn.commit()
        return self._row_to_dict(row)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM agent_tasks WHERE task_id = :task_id"), {"task_id": task_id}).mappings().first()
        return self._row_to_dict(row) if row else None

    def append_log(self, task_id: str, message: str) -> None:
        task = self.get(task_id)
        if not task:
            return
        logs = task["logs"]
        logs.append({"time": datetime.now().strftime("%H:%M:%S"), "message": message})
        self._update(task_id, logs=logs)

    def finish_success(self, task_id: str, output: str) -> None:
        self._update(task_id, status="success", output=output, error=None, finished=True)

    def finish_failure(self, task_id: str, error: str) -> None:
        self._update(task_id, status="failed", error=error, finished=True)

    def mark_running(self, task_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(text("""
                UPDATE agent_tasks
                SET status = 'running',
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                    attempt_count = attempt_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = :task_id AND status IN ('pending', 'running')
            """), {"task_id": task_id})
            conn.commit()
        return bool(result.rowcount)

    def set_rq_job(self, task_id: str, rq_job_id: str) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(text("""
                UPDATE agent_tasks
                SET rq_job_id = :rq_job_id, updated_at = CURRENT_TIMESTAMP
                WHERE task_id = :task_id
            """), {"task_id": task_id, "rq_job_id": rq_job_id})
            conn.commit()

    def delete(self, task_id: str) -> bool:
        """精确删除单条任务，供测试清理与受控运维使用。"""
        with self.client.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM agent_tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
        return bool(result.rowcount)

    def recover_stale_pending(
        self, stale_minutes: int = 10, *, actor_id: Optional[str] = None
    ) -> int:
        """将陈旧中间态与 RQ 实际状态对账；非管理员只处理自己的任务。"""
        owner_clause = ""
        owner_params: Dict[str, Any] = {}
        if actor_id is not None:
            owner_clause = " AND actor_id = :actor_id"
            owner_params["actor_id"] = actor_id
        with self.client.engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE agent_tasks
                SET status = 'failed',
                    error = '任务创建后未成功进入队列，已自动终止，请重新提交',
                    updated_at = CURRENT_TIMESTAMP,
                    finished_at = CURRENT_TIMESTAMP
                WHERE status = 'pending'
                  AND rq_job_id IS NULL
                  AND created_at < CURRENT_TIMESTAMP - (:stale_minutes * INTERVAL '1 minute')
            """ + owner_clause), {"stale_minutes": stale_minutes, **owner_params})
            recovered = result.rowcount or 0
            candidates = conn.execute(text("""
                SELECT task_id, rq_job_id, status
                FROM agent_tasks
                WHERE status IN ('pending', 'running')
                  AND rq_job_id IS NOT NULL
                  AND updated_at < CURRENT_TIMESTAMP - (:stale_minutes * INTERVAL '1 minute')
                  """ + owner_clause + """
                ORDER BY updated_at
                LIMIT 100
            """), {"stale_minutes": stale_minutes, **owner_params}).mappings().all()

        for candidate in candidates:
            rq_status, rq_error = _rq_job_state(candidate["rq_job_id"])
            if rq_status in {"unavailable", "queued", "deferred", "scheduled"}:
                continue
            if rq_status == "started":
                with self.client.engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE agent_tasks
                            SET status = 'running',
                                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE task_id = :task_id AND status = 'pending'
                        """ + owner_clause),
                        {"task_id": candidate["task_id"], **owner_params},
                    )
                continue

            if rq_status == "finished":
                reason = "RQ 任务已结束但业务结果未写回，已终止，请重新提交"
            elif rq_status == "missing":
                reason = "队列任务不存在或已过期，已自动终止，请重新提交"
            else:
                detail = rq_error[-1000:] if rq_error else rq_status
                reason = f"RQ 任务已进入终态（{rq_status}）：{detail}"
            with self.client.engine.begin() as conn:
                updated = conn.execute(
                    text("""
                        UPDATE agent_tasks
                        SET status = 'failed', error = :error,
                            updated_at = CURRENT_TIMESTAMP,
                            finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
                        WHERE task_id = :task_id AND status IN ('pending', 'running')
                    """ + owner_clause),
                    {"task_id": candidate["task_id"], "error": reason, **owner_params},
                )
                recovered += updated.rowcount or 0
        return recovered

    def list(
        self,
        *,
        status: Optional[str],
        limit: int,
        offset: int,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if actor_id is not None:
            conditions.append("actor_id = :actor_id")
            params["actor_id"] = actor_id
        where = " AND ".join(conditions)
        with self.client.engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM agent_tasks WHERE {where}"), params).scalar_one()
            rows = conn.execute(text(f"""
                SELECT * FROM agent_tasks
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        return {"items": [self._row_to_dict(row) for row in rows], "total": total}

    def _update(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        logs: Optional[list] = None,
        finished: bool = False,
    ) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(text("""
                UPDATE agent_tasks
                SET status = COALESCE(:status, status),
                    output = COALESCE(:output, output),
                    error = :error,
                    logs = COALESCE(CAST(:logs AS jsonb), logs),
                    updated_at = CURRENT_TIMESTAMP,
                    finished_at = CASE WHEN :finished THEN CURRENT_TIMESTAMP ELSE finished_at END
                WHERE task_id = :task_id
            """), {
                "task_id": task_id,
                "status": status,
                "output": output,
                "error": error,
                "logs": json.dumps(logs, ensure_ascii=False) if logs is not None else None,
                "finished": finished,
            })
            conn.commit()
