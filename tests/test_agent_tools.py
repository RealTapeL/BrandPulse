"""
tools_registry 单元测试：验证 Tool 标准接口、run_sql 只读拦截、start_crawl mock 入队。
"""
from brandpulse.agent.tools_registry import REGISTRY, execute_tool, list_tools


def test_list_tools_returns_metadata():
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert "run_sql" in names
    assert "start_crawl" in names
    assert "query_brand" in names
    assert "external_research" in names
    assert all("input_schema" in t for t in tools)


def test_execute_unknown_tool():
    result = execute_tool("not_exists", {})
    assert result["success"] is False
    assert "未知工具" in result["error"]


def test_run_sql_rejects_write(monkeypatch):
    # 直接调用工具，不应真正连接数据库；非法 SQL 会被校验拦截
    result = execute_tool("run_sql", {"sql": "DROP TABLE brands;"})
    assert result["success"] is False
    assert "DROP" in result["error"]


def test_start_crawl_returns_job_id(monkeypatch):
    captured = []

    def fake_enqueue(meta):
        captured.append(meta)
        return "job-abc"

    monkeypatch.setattr("brandpulse.agent.tools_registry.enqueue_crawl", fake_enqueue)

    result = execute_tool("start_crawl", {
        "brand_id": "LK001",
        "mall": "苏州中心",
        "category": "咖啡",
    })

    assert result["success"] is True
    assert result["result"]["job_id"] == "job-abc"
    assert captured[0]["cities"] == ["苏州"]


def test_query_brand_not_found():
    # 数据库可能没有 LK999，验证路径返回空结果而非异常
    result = execute_tool("query_brand", {"brand_id": "LK999"})
    assert result["success"] is True
    assert result["result"] is None
