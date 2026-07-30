"""Agent 工具测试（不依赖 LLM API Key）"""
import pytest

from brandpulse.agent import agent as agent_module
from brandpulse.agent import tools


class TestAgentModuleImport:
    """agent 模块可在无 LLM_API_KEY 时正常导入（惰性初始化）"""

    def test_import_agent_module(self):
        assert agent_module.SYSTEM_PROMPT
        assert callable(agent_module.build_agent)
        assert callable(agent_module.ask)

    def test_build_agent_or_clear_error(self):
        """配置了 LLM_API_KEY 则构建成功，否则抛出指向 .env 的清晰错误"""
        from brandpulse.config.config import Config

        if Config.LLM_API_KEY and Config.LLM_MODEL:
            assert agent_module.build_agent() is not None
        else:
            with pytest.raises(RuntimeError, match=".env"):
                agent_module.build_agent()


class TestQueryDbSafety:
    """query_db 只读 SQL 安全校验"""

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE dp_shop_metrics",
            "SELECT 1; DROP TABLE dp_shop_metrics",  # 多语句
            "UPDATE dp_shop_metrics SET score = 5",
            "DELETE FROM xhs_notes",
            "INSERT INTO xhs_notes (note_id) VALUES ('x')",
            "TRUNCATE brand_heat_daily",
            "ALTER TABLE dp_shop_metrics ADD COLUMN x INT",
            "GRANT SELECT ON dp_shop_metrics TO public",
            "WITH x AS (DELETE FROM dp_shop_metrics RETURNING *) SELECT * FROM x",
        ],
    )
    def test_reject_unsafe_sql(self, sql):
        result = tools.query_db(sql)
        assert result.startswith("SQL 被拒绝")

    def test_reject_empty_sql(self):
        assert tools.query_db("   ").startswith("SQL 被拒绝")

    def test_allow_normal_select(self):
        result = tools.query_db("SELECT 1 AS one, 'ok' AS msg")
        assert "one" in result
        assert "ok" in result

    def test_allow_select_with_trailing_semicolon(self):
        result = tools.query_db("SELECT 2 AS two;")
        assert "two" in result

    def test_allow_with_cte(self):
        result = tools.query_db("WITH t AS (SELECT 1 AS a) SELECT * FROM t")
        assert "a" in result


class TestListTables:
    def test_list_tables_returns_business_tables(self):
        result = tools.list_tables()
        assert "dp_shop_metrics" in result
        assert "xhs_notes" in result
        assert "brand_indicators_daily" in result
        assert "brand_heat_daily" in result
        # 带列说明
        assert "shop_name" in result
