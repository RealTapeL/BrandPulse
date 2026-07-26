"""
美团搜索 extractor 占位/示例

美团 PC 端有签名验证、cookie 校验和字体反爬，requests 直接请求难度大。
建议实现方案：
1. Playwright 访问美团，复用已登录 cookie
2. 等待页面 JS 渲染，提取 DOM 中的门店/评分/销量
3. 若遇字体反爬，复用 css_font_decoder.CssFontDecoder

本文件提供一个最小示例框架，用户可按需扩展。
"""
from typing import Any, Dict, List, Optional

from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)


def extract_search(
    html_text: str,
    brand_id: str,
    brand_name: str,
    city: Optional[str],
    url: str,
    site: Any,
) -> List[Dict[str, Any]]:
    """美团 extractor 占位"""
    logger.warning("美团 extractor 尚未实现，返回空结果")
    logger.info(f"传入 HTML 长度: {len(html_text)}, URL: {url}")
    return []
