"""Web Agent 的异步任务执行器，复用 CLI 的 Pydantic AI Agent。"""
import json
from typing import Any, Dict, Iterable

from brandpulse.agent.agent import ask
from brandpulse.logger.logger import get_logger
from brandpulse.storage.agent_task_repository import AgentTaskRepository

logger = get_logger(__name__)


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
    try:
        if not repository.mark_running(task_id):
            logger.warning("Agent 任务已处于终态，跳过重复执行: %s", task_id)
            return
        repository.append_log(task_id, "任务开始，初始化 BrandPulse Agent")
        answer, _ = ask(task["input"] + _context_suffix(task["context"]))
    except Exception as exc:
        logger.exception("Agent 任务执行失败: %s", task_id)
        try:
            repository.append_log(task_id, "任务执行失败")
            repository.finish_failure(task_id, str(exc))
        except Exception:
            logger.exception("Agent 任务失败状态写回失败: %s", task_id)
        # 同时让 RQ 记录失败，便于运维查看失败注册表；业务状态已经持久化到 agent_tasks。
        raise
    try:
        repository.append_log(task_id, "Agent 已完成工具调用并生成结论")
        repository.finish_success(task_id, answer)
    except Exception:
        logger.exception("Agent 任务成功状态写回失败: %s", task_id)
        raise
