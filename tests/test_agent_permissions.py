"""普通 Agent 必须使用语义化快照工具；自由 SQL 只属于管理员高级诊断。"""

from brandpulse.security.permissions import agent_tools_for_role


def test_business_agent_tools_are_semantic_and_side_effect_free():
    tools = agent_tools_for_role("operator")
    assert "get_scope_snapshot_evidence" in tools
    assert "get_brand_evidence" in tools
    assert "query_db" not in tools
    assert "crawl" not in tools
    assert "run_indicators" not in tools


def test_sql_is_limited_to_admin_advanced_mode():
    assert "query_db" not in agent_tools_for_role("admin")
    assert "query_db" in agent_tools_for_role("admin", advanced=True)
    assert "query_db" not in agent_tools_for_role("viewer", advanced=True)
