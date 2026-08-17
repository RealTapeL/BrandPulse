"""对话助手 HTTP 入口，复用 Agent 的数据工具和系统提示词。"""
import json
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from brandpulse.agent.task_runner import answer_question
from brandpulse.agent.tools import get_scope_snapshot_evidence
from brandpulse.api.auth import require_auth
from brandpulse.security.permissions import agent_tools_for_role

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=10)
    scope_id: Optional[str] = Field(default=None, max_length=64)


@router.post("")
def chat(payload: ChatRequest, auth: dict = Depends(require_auth)):
    try:
        history = [message.model_dump() for message in payload.history]
        # 只读角色不会把采集或指标刷新工具注册给 LLM。
        answer = answer_question(
            payload.question.strip() + (
                f"\n\n当前页面已选择监测范围 scope_id={payload.scope_id}。"
                "请先读取该范围的可信快照证据；若不可用，明确说明不能形成结论。"
                if payload.scope_id else "\n\n当前页面没有选择监测范围；先询问或列出范围，不能假定范围。"
            ),
            history,
            allowed_tools=agent_tools_for_role(str(auth["role"])),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"对话服务调用失败: {exc}") from exc
    evidence: dict = {"status": "scope_not_selected"}
    if payload.scope_id:
        try:
            raw_evidence = get_scope_snapshot_evidence(payload.scope_id)
            evidence = json.loads(raw_evidence)
        except Exception as exc:
            evidence = {"status": "unavailable", "message": str(exc)}
    return {"answer": answer, "evidence": evidence}
