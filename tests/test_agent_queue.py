"""Agent RQ 队列契约测试。"""
import pytest
from fakeredis import FakeRedis

from brandpulse.agent import queue


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis(decode_responses=True)
    monkeypatch.setattr(queue, "_redis_conn", lambda: fake)


def test_enqueue_agent_returns_job_id():
    job_id = queue.enqueue_agent("task-1")
    assert isinstance(job_id, str)
    assert len(job_id) > 0


def test_agent_queue_name_is_separate_from_crawl_queue():
    assert queue.get_agent_queue().name == queue.QUEUE_NAME
    assert queue.QUEUE_NAME == "brandpulse-agent"
