"""Agent 任务持久化，支持前端在请求结束后继续轮询状态。"""
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


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
        for key in ("created_at", "updated_at", "finished_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(text("""
                INSERT INTO agent_tasks (task_id, prompt, context, status, logs)
                VALUES (:task_id, :prompt, CAST(:context AS jsonb), 'pending', '[]'::jsonb)
                RETURNING *
            """), {"task_id": task_id, "prompt": prompt, "context": json.dumps(context, ensure_ascii=False)}).mappings().one()
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

    def mark_running(self, task_id: str) -> None:
        self._update(task_id, status="running")

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
