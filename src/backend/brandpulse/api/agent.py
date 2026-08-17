"""Agent 控制台 API：创建 RQ 后台任务并查询其持久化状态。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from brandpulse.agent.queue import AgentTaskEnqueueError, enqueue_agent
from brandpulse.agent.agent_reach import get_status
from brandpulse.api.auth import require_auth
from brandpulse.security.permissions import ROLE_ADMIN, agent_tools_for_role
from brandpulse.storage.agent_task_repository import AgentTaskRepository

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentExecuteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    context: Dict[str, Any] = Field(default_factory=dict)


@router.get("/external/status")
def external_research_status(_auth: Dict[str, Any] = Depends(require_auth)):
    """返回 Agent-Reach 外部研究能力状态，不包含 Cookie/Token 等凭据。"""
    return get_status()


@router.post("/execute")
def execute_agent(payload: AgentExecuteRequest, auth: Dict[str, Any] = Depends(require_auth)):
    """先落库，再入队；入队失败时把任务明确标记为 failed。"""
    repository = AgentTaskRepository()
    allowed_tools = sorted(agent_tools_for_role(str(auth["role"]), advanced=str(auth["role"]) == ROLE_ADMIN))
    task = repository.create(
        payload.prompt.strip(),
        payload.context,
        actor_id=str(auth["sub"]),
        actor_username=str(auth["username"]),
        actor_role=str(auth["role"]),
        allowed_tools=allowed_tools,
    )
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
    auth: Dict[str, Any] = Depends(require_auth),
):
    """查询持久化历史，页面刷新后仍可恢复任务列表。"""
    repository = AgentTaskRepository()
    actor_id = None if auth["role"] == ROLE_ADMIN else str(auth["sub"])
    repository.recover_stale_pending(actor_id=actor_id)
    result = repository.list(status=status, limit=size, offset=(page - 1) * size, actor_id=actor_id)
    if auth["role"] != ROLE_ADMIN:
        for task in result["items"]:
            task.pop("logs", None)
            task.pop("allowed_tools", None)
            task.pop("rq_job_id", None)
    return result


@router.get("/tasks/{task_id}")
def get_agent_task(task_id: str, auth: Dict[str, Any] = Depends(require_auth)):
    task = AgentTaskRepository().get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    if auth["role"] != ROLE_ADMIN and task.get("actor_id") != str(auth["sub"]):
        raise HTTPException(status_code=403, detail="无权查看其他用户的 Agent 任务")
    if auth["role"] != ROLE_ADMIN:
        task.pop("logs", None)
        task.pop("allowed_tools", None)
        task.pop("rq_job_id", None)
    return task
