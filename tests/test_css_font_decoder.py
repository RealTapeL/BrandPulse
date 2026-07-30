"""
CSS 字体反爬解码器单元测试

模拟大众点评式 CSS 字体反爬：
- 页面中的数字由 <span class="cls"></span> 占位
- CSS 定义每个 class 对应的 background 偏移
- SVG 字体文件里有多行数字，通过 y 阈值选择行、通过 x 偏移选择列
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "backend"
sys.path.insert(0, str(SRC_DIR))

from brandpulse.collectors.css_font_decoder import CssFontDecoder


def build_test_assets():
    """
    构造一组假的 CSS/SVG/HTML，用于验证解码器。

    设计：
    - 两行 SVG 数字：
        第 1 行 y=30: "01234567890123"
        第 2 行 y=70: "98765432109876"
    - 字体大小 12
    - class px 映射：
        .demo_a -> offset=-12, position=-30 => index=0, 行1 => '0'
        .demo_b -> offset=-24, position=-30 => index=1, 行1 => '1'
        .demo_c -> offset=-36, position=-70 => index=2, 行2 => '7'
        .demo_d -> offset=-24, position=-70 => index=1, 行2 => '8'
    """
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg>
  <text x="0" y="30">01234567890123</text>
  <text x="0" y="70">98765432109876</text>
</svg>"""

    css_content = """
span[class^="demo_"]{background-image:url(//s3plus.meituan.net/v1/xxx.svg);}
.demo_a{background:-12.0px -30.0px;}
.demo_b{background:-24.0px -30.0px;}
.demo_c{background:-36.0px -70.0px;}
.demo_d{background:-24.0px -70.0px;}
"""

    html_content = """
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" type="text/css" href="https://s3plus.meituan.net/v1/mss_xxx/svgtextcss/xxx.css">
</head>
<body>
  <div class="shop">
    <span class="name">Demo Shop</span>
    <b class="demo_a"></b><b class="demo_b"></b><b class="demo_c"></b><b class="demo_d"></b>条评论
  </div>
</body>
</html>
"""
    return html_content, css_content, svg_content


def test_decode_single_class():
    decoder = CssFontDecoder(font_size=12)

    # 不访问网络，直接喂入 CSS/SVG 内容
    decoder.class_to_px = {
        "demo_a": (-12.0, -30.0),
        "demo_b": (-24.0, -30.0),
        "demo_c": (-36.0, -70.0),
        "demo_d": (-24.0, -70.0),
    }
    decoder.svg_rows = [
        (30, "01234567890123"),
        (70, "98765432109876"),
    ]

    assert decoder.decode_class("demo_a") == "0"
    assert decoder.decode_class("demo_b") == "1"
    assert decoder.decode_class("demo_c") == "7"
    assert decoder.decode_class("demo_d") == "8"
    assert decoder.decode_class("z") is None
    print("✓ 单 class 解码正确")


def test_decode_number():
    decoder = CssFontDecoder(font_size=12)
    decoder.class_to_px = {
        "demo_a": (-12.0, -30.0),
        "demo_b": (-24.0, -30.0),
        "demo_c": (-36.0, -70.0),
        "demo_d": (-24.0, -70.0),
    }
    decoder.svg_rows = [
        (30, "01234567890123"),
        (70, "98765432109876"),
    ]

    assert decoder.decode_number(["demo_a", "demo_b", "demo_c", "demo_d"]) == 178
    print("✓ 多 class 数字拼接正确")


def test_infer_tag():
    from brandpulse.collectors.css_font_decoder import _infer_tag

    assert _infer_tag(["vxth5", "vxt20", "vxt33"]) == "vxt"
    assert _infer_tag(["abc123", "abc456"]) == "abc"
    assert _infer_tag([]) is None
    print("✓ class 公共前缀推断正确")


def test_build_from_page(monkeypatch_requests=None):
    """
    测试从 HTML 页面自动构建解码器。
    这里用本地字符串模拟网络请求。
    """
    html_content, css_content, svg_content = build_test_assets()

    # 为了不走网络，直接 mock requests.get
    class FakeResponse:
        def __init__(self, text):
            self.text = text
            self.content = text.encode("utf-8")

        def raise_for_status(self):
            pass

    original_get = __import__("requests", fromlist=["get"]).get
    call_count = {"n": 0}

    def fake_get(url, timeout=None):
        call_count["n"] += 1
        if "svgtextcss" in url:
            return FakeResponse(css_content)
        elif ".svg" in url:
            return FakeResponse(svg_content)
        # HTML 页面请求
        return FakeResponse(html_content)

    import requests as req_module

    req_module.get = fake_get
    try:
        decoder = CssFontDecoder.build_from_page(
            html_text=html_content,
            css_url_regex=r'href="([^"]+svgtextcss[^"]+)\.css"',
            svg_regex_template=r'background-image:\s*url\(([^)]+)\);',
            class_tag_regex=r'<b\s+class="([^"]+)"></b>',
            font_size=12,
        )
        assert decoder is not None
        assert decoder.decode_number(["demo_a", "demo_b", "demo_c", "demo_d"]) == 178
        print("✓ 从页面自动构建解码器成功")
    finally:
        req_module.get = original_get


if __name__ == "__main__":
    test_decode_single_class()
    test_decode_number()
    test_infer_tag()
    test_build_from_page()
    print("\n所有 CSS 字体反爬测试通过")
