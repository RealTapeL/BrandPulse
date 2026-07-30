"""
通用配置化爬虫引擎单元测试

模拟一个带 CSS 字体反爬的站点，验证 GenericWebCrawler 能按配置文件正确抓取。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "backend"
sys.path.insert(0, str(SRC_DIR))

from brandpulse.collectors.crawler import GenericWebCrawler


def build_demo_site_html():
    """构造一个模拟的商业平台搜索页"""
    html = """
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" type="text/css" href="https://demo.local/svgtextcss/style.css">
</head>
<body>
  <div class="shop-list">
    <div class="shop">
      <span class="name">瑞幸咖啡（朝阳大悦城店）</span>
      <div class="rating">
        <b class="demo_a"></b><b class="demo_b"></b><b class="demo_c"></b><b class="demo_d"></b>条评论
      </div>
    </div>
    <div class="shop">
      <span class="name">瑞幸咖啡（三里屯店）</span>
      <div class="rating">
        <b class="demo_a"></b><b class="demo_b"></b>条评论
      </div>
    </div>
  </div>
</body>
</html>
"""
    return html


def build_demo_css():
    return """
span[class^="demo_"]{background-image:url(//demo.local/fonts/digits.svg);}
.demo_a{background:-12.0px -30.0px;}
.demo_b{background:-24.0px -30.0px;}
.demo_c{background:-36.0px -70.0px;}
.demo_d{background:-24.0px -70.0px;}
"""


def build_demo_svg():
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg>
  <text x="0" y="30">01234567890123</text>
  <text x="0" y="70">98765432109876</text>
</svg>"""


def test_generic_crawler_with_css_font():
    html = build_demo_site_html()
    css = build_demo_css()
    svg = build_demo_svg()

    class FakeResponse:
        def __init__(self, text):
            self.text = text
            self.content = text.encode("utf-8")

        def raise_for_status(self):
            pass

    import requests as req_module

    original_get = req_module.get

    def fake_get(url, **kwargs):
        if "svgtextcss" in url or ".css" in url:
            return FakeResponse(css)
        elif ".svg" in url:
            return FakeResponse(svg)
        return FakeResponse(html)

    req_module.get = fake_get
    try:
        crawler = GenericWebCrawler(
            config_path=Path(__file__).resolve().parent.parent
            / "src"
            / "backend"
            / "brandpulse"
            / "collectors"
            / "config"
            / "crawler_sites.yaml"
        )

        # 临时把 demo_css_font 启用，并指向假 URL
        crawler.sites["demo_css_font"].enabled = True
        crawler.sites["demo_css_font"].base_url = "https://demo.local/search?keyword={keyword}"

        results = crawler.crawl_site(
            site_id="demo_css_font",
            brand_id="LK001",
            brand_name="瑞幸咖啡",
            city="北京",
        )

        assert len(results) == 2, f"应返回 2 条结果，实际 {len(results)}"
        assert results[0]["name"] == "瑞幸咖啡（朝阳大悦城店）"
        assert results[0]["review_count"] == 178
        assert results[1]["name"] == "瑞幸咖啡（三里屯店）"
        assert results[1]["review_count"] == 1  # demo_a(0) + demo_b(1) -> 01 -> 1
        print("✓ 通用爬虫 + CSS 字体反爬测试通过")
    finally:
        req_module.get = original_get


if __name__ == "__main__":
    test_generic_crawler_with_css_font()
