"""Optional Agent-Reach integration for public external research.

Agent-Reach is a capability layer that selects upstream tools. BrandPulse
keeps this adapter narrow: it exposes health information, public URL reading
through the documented Jina Reader backend, and Exa search through the
documented ``mcporter`` command when that dependency is installed.

This module never accepts or persists cookies, tokens, or account credentials.
It is disabled by default and all external calls have bounded timeouts and
response sizes.
"""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def _enabled_error() -> str:
    return (
        "Agent-Reach 外部研究未启用。请在项目 .env 设置 "
        "AGENT_REACH_ENABLED=true，并先安装 Agent-Reach 后运行 agent-reach doctor。"
    )


def _command_path(command: str) -> Optional[str]:
    return shutil.which(command)


def _safe_command_output(value: str) -> str:
    """Remove accidental credential-like lines before returning CLI output."""
    lines = []
    for line in value.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("cookie", "token", "password", "secret", "api_key")):
            lines.append("[已隐藏凭据相关输出]")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _run_command(args: list[str]) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=Config.AGENT_REACH_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return {"returncode": 127, "stdout": "", "stderr": f"命令不存在: {args[0]}"}
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "命令执行超时"}
    return {
        "returncode": completed.returncode,
        "stdout": _safe_command_output(completed.stdout or ""),
        "stderr": _safe_command_output(completed.stderr or ""),
    }


def _doctor_summary(raw: str) -> Dict[str, Any]:
    """Keep the health API stable when Agent-Reach changes JSON shape."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw[: Config.AGENT_REACH_MAX_RESPONSE_CHARS]}

    if not isinstance(payload, dict):
        return {"raw": json.dumps(payload, ensure_ascii=False)[: Config.AGENT_REACH_MAX_RESPONSE_CHARS]}

    def redact(value: Any, key: str = "") -> Any:
        lowered = key.lower()
        if any(token in lowered for token in ("cookie", "token", "password", "secret", "api_key")):
            return "[已隐藏]"
        if isinstance(value, dict):
            return {str(k): redact(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(item, key) for item in value]
        return value

    payload = redact(payload)
    summary: Dict[str, Any] = {}
    for key in ("status", "version", "active_backend", "channels", "checks", "platforms"):
        if key in payload:
            summary[key] = payload[key]
    if not summary:
        summary["raw"] = json.dumps(payload, ensure_ascii=False)[: Config.AGENT_REACH_MAX_RESPONSE_CHARS]
    return summary


def get_status() -> Dict[str, Any]:
    """Return a credential-free status object for the UI and diagnostics."""
    enabled = Config.AGENT_REACH_ENABLED
    cli_path = _command_path(Config.AGENT_REACH_COMMAND)
    mcporter_path = _command_path(Config.AGENT_REACH_SEARCH_COMMAND)
    status: Dict[str, Any] = {
        "enabled": enabled,
        "installed": cli_path is not None,
        "command": Config.AGENT_REACH_COMMAND,
        "search_available": mcporter_path is not None,
        "status": "disabled" if not enabled else "not_installed" if not cli_path else "unknown",
    }
    if not enabled or not cli_path:
        return status

    result = _run_command([cli_path, "doctor", "--json"])
    status["status"] = "ready" if result["returncode"] == 0 else "error"
    status["doctor"] = _doctor_summary(result["stdout"] or result["stderr"])
    if result["returncode"] != 0:
        status["error"] = result["stderr"] or "Agent-Reach doctor 执行失败"
    return status


def _validate_public_url(url: str) -> str:
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("只允许读取 http/https 公共网页 URL")
    if parsed.username or parsed.password:
        raise ValueError("URL 不允许包含用户名或密码")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal")):
        raise ValueError("不允许访问本地或内部域名")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ValueError("不允许访问内网或保留 IP 地址")
    return cleaned


def read_public_url(url: str) -> str:
    """Read a public URL through Agent-Reach's documented Jina Reader backend."""
    if not Config.AGENT_REACH_ENABLED:
        return _enabled_error()
    try:
        target = _validate_public_url(url)
    except ValueError as exc:
        return f"外部网页读取失败：{exc}"
    reader_url = f"https://r.jina.ai/{target}"
    try:
        response = requests.get(
            reader_url,
            headers={"Accept": "text/plain", "User-Agent": "BrandPulse-Agent-Reach/1.0"},
            timeout=Config.AGENT_REACH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Agent-Reach 网页读取失败: %s", exc)
        return f"外部网页读取失败：{exc}"

    content = response.text.strip()
    if not content:
        return f"外部网页没有返回可读内容：{target}"
    content = content[: Config.AGENT_REACH_MAX_RESPONSE_CHARS]
    truncated = "\n（内容过长，已截断）" if len(response.text) > len(content) else ""
    return f"来源：Agent-Reach / Jina Reader\nURL：{target}\n\n{content}{truncated}"


def search_public_web(query: str, limit: int = 5) -> str:
    """Search public web through Agent-Reach's documented Exa/mcporter path."""
    if not Config.AGENT_REACH_ENABLED:
        return _enabled_error()
    cleaned = (query or "").strip()
    if not cleaned:
        return "外部搜索失败：搜索词不能为空"
    if len(cleaned) > 500:
        return "外部搜索失败：搜索词不能超过 500 个字符"
    search_limit = max(1, min(int(limit), 10))
    command = _command_path(Config.AGENT_REACH_SEARCH_COMMAND)
    if not command:
        return "外部搜索不可用：未找到 mcporter/Exa，请运行 agent-reach doctor 检查配置"

    result = _run_command([
        command,
        "call",
        "exa.web_search_exa",
        f"query={cleaned}",
        f"numResults={search_limit}",
    ])
    if result["returncode"] != 0:
        return f"外部搜索失败：{result['stderr'] or result['stdout'] or '未知错误'}"
    output = result["stdout"] or "（搜索没有返回结果）"
    return f"来源：Agent-Reach / Exa\n查询：{cleaned}\n\n{output[:Config.AGENT_REACH_MAX_RESPONSE_CHARS]}"


def research_status_text() -> str:
    return json.dumps(get_status(), ensure_ascii=False, indent=2)
