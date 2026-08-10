"""Agent-Reach 适配层测试：默认关闭、URL 安全边界和上游命令参数。"""

from types import SimpleNamespace

from brandpulse.agent import agent_reach
from brandpulse.config.config import Config


def test_status_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(Config, "AGENT_REACH_ENABLED", False)
    status = agent_reach.get_status()
    assert status["status"] == "disabled"
    assert status["enabled"] is False


def test_read_public_url_rejects_private_address(monkeypatch):
    monkeypatch.setattr(Config, "AGENT_REACH_ENABLED", True)
    result = agent_reach.read_public_url("http://127.0.0.1:8000/docs")
    assert "不允许访问内网" in result


def test_read_public_url_uses_jina_and_limits_content(monkeypatch):
    monkeypatch.setattr(Config, "AGENT_REACH_ENABLED", True)
    monkeypatch.setattr(Config, "AGENT_REACH_MAX_RESPONSE_CHARS", 10)
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return SimpleNamespace(text="abcdefghijklmnop", raise_for_status=lambda: None)

    monkeypatch.setattr(agent_reach.requests, "get", fake_get)
    result = agent_reach.read_public_url("https://example.com/article")

    assert captured["url"] == "https://r.jina.ai/https://example.com/article"
    assert "abcdefghijkl" not in result
    assert "内容过长" in result


def test_search_public_web_passes_arguments_without_shell(monkeypatch):
    monkeypatch.setattr(Config, "AGENT_REACH_ENABLED", True)
    monkeypatch.setattr(agent_reach, "_command_path", lambda command: "/usr/bin/mcporter")
    captured = {}

    def fake_run(args):
        captured["args"] = args
        return {"returncode": 0, "stdout": "result", "stderr": ""}

    monkeypatch.setattr(agent_reach, "_run_command", fake_run)
    result = agent_reach.search_public_web("苏州中心 咖啡", limit=99)

    assert captured["args"] == [
        "/usr/bin/mcporter",
        "call",
        "exa.web_search_exa",
        "query=苏州中心 咖啡",
        "numResults=10",
    ]
    assert "result" in result
