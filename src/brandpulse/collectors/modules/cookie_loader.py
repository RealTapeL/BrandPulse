"""
Cookie 加载工具

支持从本地浏览器导出的 JSON cookies 文件加载。

文件格式（Cookie-Editor / EditThisCookie 等插件导出）：
[
    {
        "name": "...",
        "value": "...",
        "domain": ".dianping.com",
        "path": "/",
        "expires": -1,
        "httpOnly": false,
        "secure": false,
        "sameSite": "None"
    }
]
"""
import json
from pathlib import Path
from typing import Dict, List

from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)


def load_cookies(domain_filter: str = "") -> List[Dict]:
    """
    从 COOKIE_DIR 加载 cookies。

    Args:
        domain_filter: 只返回包含该字符串的 domain 的 cookies，
                       空字符串则返回所有。

    Returns:
        标准化后的 cookies 列表
    """
    cookie_dir = Config.COOKIE_DIR
    if not cookie_dir.exists():
        logger.warning(f"Cookie 目录不存在: {cookie_dir}")
        return []

    cookies = []
    for cookie_file in sorted(cookie_dir.glob("*.json")):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.warning(f"Cookie 文件格式错误（应为 list）: {cookie_file}")
                continue

            for cookie in data:
                if not isinstance(cookie, dict):
                    continue
                if domain_filter and domain_filter not in str(cookie.get("domain", "")):
                    continue

                # 确保 cookies 字段完整
                normalized = {
                    "name": str(cookie.get("name", "")),
                    "value": str(cookie.get("value", "")),
                    "domain": str(cookie.get("domain", "")),
                    "path": str(cookie.get("path", "/")),
                }
                if cookie.get("expires") is not None:
                    try:
                        normalized["expires"] = float(cookie["expires"])
                    except (ValueError, TypeError):
                        pass
                if cookie.get("httpOnly") is not None:
                    normalized["httpOnly"] = bool(cookie["httpOnly"])
                if cookie.get("secure") is not None:
                    normalized["secure"] = bool(cookie["secure"])
                if cookie.get("sameSite") is not None:
                    normalized["sameSite"] = str(cookie["sameSite"])

                if normalized["name"] and normalized["domain"]:
                    cookies.append(normalized)

            logger.info(f"从 {cookie_file} 加载了 {len(data)} 条 cookie")
        except Exception as e:
            logger.warning(f"读取 cookie 文件 {cookie_file} 失败: {e}")

    if domain_filter:
        logger.info(f"共加载 {len(cookies)} 条 domain 包含 '{domain_filter}' 的 cookie")
    else:
        logger.info(f"共加载 {len(cookies)} 条 cookie")

    return cookies


def save_cookies(cookies: List[Dict], filename: str = "cookies.json") -> Path:
    """保存 cookies 到 COOKIE_DIR"""
    cookie_dir = Config.COOKIE_DIR
    cookie_dir.mkdir(parents=True, exist_ok=True)
    path = cookie_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    logger.info(f"Cookies 已保存到 {path}")
    return path
