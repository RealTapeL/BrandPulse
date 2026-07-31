"""Agent 控制台 API：创建后台任务并查询其状态。"""
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from brandpulse.agent.task_runner import run_agent_task
from brandpulse.storage.agent_task_repository import AgentTaskRepository

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentExecuteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/execute")
def execute_agent(payload: AgentExecuteRequest, background_tasks: BackgroundTasks):
    task = AgentTaskRepository().create(payload.prompt.strip(), payload.context)
    background_tasks.add_task(run_agent_task, task["id"])
    return {"task_id": task["id"]}


@router.get("/tasks/{task_id}")
def get_agent_task(task_id: str):
    task = AgentTaskRepository().get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    return task
