"""
collectors/queue.py 单元测试：用 fakeredis mock Redis，验证任务入队。
"""
import pytest
from fakeredis import FakeRedis

from brandpulse.collectors import queue


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """所有测试使用 FakeRedis，不依赖真实 Redis 服务。"""
    fake = FakeRedis(decode_responses=True)
    monkeypatch.setattr(queue, "_redis_conn", lambda: fake)


def test_enqueue_crawl_returns_job_id():
    # worker 函数字符串化后不会被真正执行，只需要验证入队
    job_id = queue.enqueue_crawl({
        "brand_id": "LK001",
        "mall": "苏州中心",
        "category": "咖啡",
        "cities": ["苏州"],
    })
    assert isinstance(job_id, str)
    assert len(job_id) > 0


def test_get_queue_returns_same_queue():
    q = queue.get_queue()
    assert q.name == queue.QUEUE_NAME
