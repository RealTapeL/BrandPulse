"""Agent Worker 执行器的状态落库测试。"""
from uuid import uuid4

from brandpulse.agent import task_runner
from brandpulse.storage import agent_task_repository as repository_module
from brandpulse.storage.agent_task_repository import AgentTaskRepository


def test_run_agent_task_persists_success_and_logs(monkeypatch):
    repository = AgentTaskRepository()
    task = repository.create(f"Worker 测试任务 {uuid4().hex}", {})
    monkeypatch.setattr(task_runner, "ask", lambda _question: ("来自 Worker 的真实执行结果", []))

    try:
        task_runner.run_agent_task(task["id"])

        result = repository.get(task["id"])
        assert result["status"] == "success"
        assert result["output"] == "来自 Worker 的真实执行结果"
        assert result["attempt_count"] == 1
        assert [item["message"] for item in result["logs"]] == [
            "任务开始，初始化 BrandPulse Agent",
            "Agent 已完成工具调用并生成结论",
        ]
    finally:
        repository.delete(task["id"])


def test_recover_stale_task_when_rq_job_is_missing(monkeypatch):
    repository = AgentTaskRepository()
    task = repository.create(f"RQ 对账测试任务 {uuid4().hex}", {})
    repository.set_rq_job(task["id"], f"missing-{uuid4().hex}")
    monkeypatch.setattr(
        repository_module,
        "_rq_job_state",
        lambda _rq_job_id: ("missing", "RQ 中不存在对应任务"),
    )
    try:
        assert repository.recover_stale_pending(stale_minutes=0) >= 1
        result = repository.get(task["id"])
        assert result["status"] == "failed"
        assert "队列任务不存在" in result["error"]
    finally:
        repository.delete(task["id"])
