"""Web Agent 的异步任务执行器，复用 CLI 的 Pydantic AI Agent。"""
import json
from typing import Any, Dict, Iterable

from brandpulse.agent.agent import ask
from brandpulse.storage.agent_task_repository import AgentTaskRepository


def _context_suffix(context: Dict[str, Any]) -> str:
    if not context:
        return ""
    return "\n\n已知业务上下文（JSON）：\n" + json.dumps(context, ensure_ascii=False, sort_keys=True)


def _history_suffix(history: Iterable[Dict[str, str]]) -> str:
    messages = []
    for item in history:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            speaker = "用户" if role == "user" else "助手"
            messages.append(f"{speaker}: {content}")
    if not messages:
        return ""
    return "\n\n本轮之前的对话上下文：\n" + "\n".join(messages[-8:])


def answer_question(question: str, history: Iterable[Dict[str, str]] = ()) -> str:
    """供聊天 API 同步调用，并把浏览器历史压缩成模型可读上下文。"""
    answer, _ = ask(question + _history_suffix(history))
    return answer


def run_agent_task(task_id: str) -> None:
    """后台执行一条控制台任务，并把可轮询的状态写回 PostgreSQL。"""
    repository = AgentTaskRepository()
    task = repository.get(task_id)
    if not task:
        return
    repository.mark_running(task_id)
    repository.append_log(task_id, "任务开始，初始化 BrandPulse Agent")
    try:
        answer, _ = ask(task["input"] + _context_suffix(task["context"]))
    except Exception as exc:
        repository.append_log(task_id, "任务执行失败")
        repository.finish_failure(task_id, str(exc))
        return
    repository.append_log(task_id, "Agent 已完成工具调用并生成结论")
    repository.finish_success(task_id, answer)
