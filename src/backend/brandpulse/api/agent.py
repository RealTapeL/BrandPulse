"""Agent 控制台 API：创建 RQ 后台任务并查询其持久化状态。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from brandpulse.agent.queue import AgentTaskEnqueueError, enqueue_agent
from brandpulse.storage.agent_task_repository import AgentTaskRepository

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentExecuteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/execute")
def execute_agent(payload: AgentExecuteRequest):
    """先落库，再入队；入队失败时把任务明确标记为 failed。"""
    repository = AgentTaskRepository()
    task = repository.create(payload.prompt.strip(), payload.context)
    try:
        rq_job_id = enqueue_agent(task["id"])
        repository.set_rq_job(task["id"], rq_job_id)
    except Exception as exc:
        if not isinstance(exc, AgentTaskEnqueueError):
            exc = AgentTaskEnqueueError(f"Agent 任务入队后状态写回失败: {exc}")
        repository.append_log(task["id"], "任务入队失败")
        repository.finish_failure(task["id"], str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"task_id": task["id"], "rq_job_id": rq_job_id, "status": "pending"}


@router.get("/tasks")
def list_agent_tasks(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """查询持久化历史，页面刷新后仍可恢复任务列表。"""
    repository = AgentTaskRepository()
    repository.recover_stale_pending()
    return repository.list(status=status, limit=size, offset=(page - 1) * size)


@router.get("/tasks/{task_id}")
def get_agent_task(task_id: str):
    task = AgentTaskRepository().get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    return task
