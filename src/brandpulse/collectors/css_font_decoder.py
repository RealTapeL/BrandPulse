"""
通用 CSS 字体反爬解码器

参考：崔庆才《大众点评还不会爬？跟着我，我教你》
https://cuiqingcai.com/6341.html

大众点评等网站会把关键数字（评分、评论数、人均消费）用 CSS 背景图偏移 + SVG 字体
的方式渲染。HTML 源码里看不到真实数字，必须从 CSS 和 SVG 中反解。

解码流程：
1. 从目标页面提取 CSS 链接（含 svgtextcss 等关键字）
2. 解析 CSS，得到每个 class -> (x_offset, y_position)
3. 解析 SVG 字体文件，得到每行数字串及其 y 阈值
4. 对 HTML 中的每个 <span class="xxx">：
   - index = ceil(abs(x_offset) / font_size)
   - 根据 y_position 找到对应行
   - digit = row_text[index]
"""
import math
import re
from typing import Dict, List, Optional, Tuple

import requests
from lxml import etree

from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


class CssFontDecoder:
    """CSS 字体反爬解码器"""

    def __init__(self, font_size: int = 12, timeout: int = 30):
        self.font_size = font_size
        self.timeout = timeout
        self.class_to_px: Dict[str, Tuple[float, float]] = {}
        self.svg_rows: List[Tuple[int, str]] = []  # (y_threshold, digit_string)

    def load_css(self, css_url: str, px_regex: Optional[str] = None) -> str:
        """
        加载 CSS 文件并解析 class -> (x_offset, y_position)

        Args:
            css_url: CSS 文件 URL
            px_regex: 自定义正则，默认匹配 .class{background:-157.0px -103.0px}

        Returns:
            CSS 文本内容
        """
        if px_regex is None:
            px_regex = r"(\.[-a-zA-Z0-9_]+)\{background:\s*(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px"

        logger.info(f"加载 CSS: {css_url}")
        resp = requests.get(css_url, timeout=self.timeout)
        resp.raise_for_status()
        css_text = resp.text

        pattern = re.compile(px_regex)
        matches = pattern.findall(css_text)
        if not matches:
            raise ValueError(f"未从 CSS 中解析到 class/px 映射，请检查正则: {px_regex}")

        self.class_to_px = {}
        for cls, x_off, y_pos in matches:
            class_name = cls.lstrip(".")
            self.class_to_px[class_name] = (float(x_off), float(y_pos))

        logger.info(f"CSS 解析完成: {len(self.class_to_px)} 个 class")
        return css_text

    def load_svg(self, svg_url: str) -> None:
        """
        加载 SVG 字体文件并解析每行数字串及其 y 阈值

        SVG 示例：
        <text x="0" y="38">0123456789</text>
        <text x="0" y="83">9876543210</text>
        """
        logger.info(f"加载 SVG: {svg_url}")
        resp = requests.get(svg_url, timeout=self.timeout)
        resp.raise_for_status()

        root = etree.HTML(resp.content)
        texts = root.xpath("//text")
        rows = []
        for text in texts:
            y_attr = text.get("y")
            digit_str = "".join(text.xpath("./text()"))
            if y_attr is not None and digit_str:
                rows.append((int(float(y_attr)), digit_str))

        if not rows:
            raise ValueError("未从 SVG 中解析到数字行")

        # 按 y 升序排列
        self.svg_rows = sorted(rows, key=lambda x: x[0])
        logger.info(f"SVG 解析完成: {len(self.svg_rows)} 行")

    def decode_class(self, class_name: str) -> Optional[str]:
        """解码单个 class 对应的数字字符"""
        if class_name not in self.class_to_px:
            return None

        x_off, y_pos = self.class_to_px[class_name]
        # index: 1-based，因为 offset 是从 0 开始，ceil(abs(offset)/font_size)
        index = math.ceil(abs(x_off) / self.font_size) - 1

        # 根据 abs(y_pos) 找对应行：第一个 y_threshold >= abs(y_pos) 的行
        target_y = abs(y_pos)
        for y_threshold, digit_str in self.svg_rows:
            if target_y <= y_threshold:
                if 0 <= index < len(digit_str):
                    return digit_str[index]
                return None
        return None

    def decode_number(self, class_names: List[str]) -> Optional[int]:
        """
        把一系列 class 解码成一个整数

        例如 HTML 中：<b class="vxth5"></b><b class="vxt20"></b> 表示 643
        """
        digits = []
        for cls in class_names:
            digit = self.decode_class(cls)
            if digit is None:
                return None
            digits.append(digit)
        try:
            return int("".join(digits))
        except ValueError:
            return None

    @classmethod
    def build_from_page(
        cls,
        html_text: str,
        css_url_regex: str = r'href="([^"]+svgtextcss[^"]+)"',
        svg_regex_template: Optional[str] = None,
        class_tag_regex: str = r'<b\s+class="([^"]+)"></b>',
        font_size: int = 12,
    ) -> Optional["CssFontDecoder"]:
        """
        从 HTML 页面自动提取 CSS/SVG 并构建解码器

        Args:
            html_text: 页面 HTML 源码
            css_url_regex: 匹配 CSS URL 的正则
            svg_regex_template: 匹配 SVG URL 的正则模板，通常需要 class 前缀 tag
            class_tag_regex: 用于推断 SVG regex 所需 tag 的 class 列表正则
            font_size: 字体大小

        Returns:
            构建好的解码器，若页面没有 CSS 字体反爬则返回 None
        """
        # 1. 找 CSS URL
        match = re.search(css_url_regex, html_text)
        if not match:
            logger.info("页面未检测到 CSS 字体反爬")
            return None

        css_url = match.group(1)
        if css_url.startswith("//"):
            css_url = "https:" + css_url
        elif css_url.startswith("/"):
            # 相对路径缺少 base_url，无法构造完整 URL，直接放弃
            logger.info("CSS URL 为相对路径且未提供 base_url，跳过字体反爬处理")
            return None

        # 2. 推断 tag，用于匹配 SVG URL
        tag = None
        if svg_regex_template is not None and "{tag}" in svg_regex_template:
            classes = re.findall(class_tag_regex, html_text)
            tag = _infer_tag(classes)
            if tag:
                svg_regex = svg_regex_template.format(tag=tag)
            else:
                svg_regex = None
        else:
            svg_regex = svg_regex_template

        decoder = cls(font_size=font_size)
        css_text = decoder.load_css(css_url)

        # 3. 从 CSS 内容里匹配 SVG URL
        if svg_regex:
            svg_match = re.search(svg_regex, css_text)
            if svg_match:
                svg_url = svg_match.group(1)
                if svg_url.startswith("//"):
                    svg_url = "https:" + svg_url
                decoder.load_svg(svg_url)
            else:
                logger.warning("未匹配到 SVG URL")

        return decoder


def _infer_tag(classes: List[str]) -> Optional[str]:
    """
    从 class 列表推断公共前缀 tag。

    例如 class 列表 ["vxth5", "vxt20", "vxt33"] -> 公共前缀 "vxt"
    """
    if not classes:
        return None
    if len(classes) == 1:
        # 单个时取前 3 个字符作为 tag（大众点评常见）
        return classes[0][:3] if len(classes[0]) >= 3 else classes[0]

    prefix = ""
    min_len = min(len(c) for c in classes)
    for i in range(min_len):
        chars = {c[i] for c in classes}
        if len(chars) == 1:
            prefix += classes[0][i]
        else:
            break
    return prefix if prefix else None
