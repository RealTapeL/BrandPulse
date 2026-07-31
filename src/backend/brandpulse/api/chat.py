"""对话助手 HTTP 入口，复用 Agent 的数据工具和系统提示词。"""
from typing import List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from brandpulse.agent.task_runner import answer_question

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=10)


@router.post("")
def chat(payload: ChatRequest):
    try:
        answer = answer_question(payload.question.strip(), [message.model_dump() for message in payload.history])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"对话服务调用失败: {exc}") from exc
    return {"answer": answer}
