"""
通用配置化站点爬虫引擎

目标：一个配置文件即可新增要爬取的商业平台。

目前支持：
1. requests + lxml 静态页面抓取
2. 可选 CSS 字体反爬解码（大众点评式）
3. XPath / CSS 选择器提取字段
4. 自动写入 brand_metrics 表

扩展方式：
- 简单站点：在 crawler_sites.yaml 里配置 selectors
- 复杂站点：在 extractors/ 下写 Python 插件，在 config 里指定 extractor
"""
import importlib
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml
from lxml import etree

from brandpulse.collectors.modules.css_font_decoder import CssFontDecoder
from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger
from brandpulse.storage.modules.pg_repository import MetricsRepository

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class SiteConfig:
    """单个站点的配置包装"""

    def __init__(self, site_id: str, conf: Dict[str, Any]):
        self.site_id = site_id
        self.name = conf.get("name", site_id)
        self.enabled = conf.get("enabled", True)
        self.base_url = conf.get("base_url", "")
        self.method = conf.get("method", "GET").upper()
        self.headers = {**DEFAULT_HEADERS, **conf.get("headers", {})}
        self.timeout = conf.get("timeout", 30)
        self.delay = conf.get("delay", [2, 4])
        self.encoding = conf.get("encoding", "utf-8")
        self.css = conf.get("css", {})
        self.selectors = conf.get("selectors", {})
        self.fields = conf.get("fields", [])
        self.extractor = conf.get("extractor")  # 可选 Python 插件路径
        self.params = conf.get("params", {})
        self.headless = conf.get("headless", True)


class GenericWebCrawler:
    """通用站点爬虫"""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parents[2]
                / "collectors"
                / "config"
                / "crawler_sites.yaml"
            )
        self.config_path = config_path
        self.sites: Dict[str, SiteConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"爬虫配置文件不存在: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for site_id, conf in data.get("sites", {}).items():
            self.sites[site_id] = SiteConfig(site_id, conf)
        logger.info(f"加载了 {len(self.sites)} 个站点配置")

    def list_sites(self) -> List[str]:
        return [sid for sid, s in self.sites.items() if s.enabled]

    def crawl_site(
        self,
        site_id: str,
        brand_id: str,
        brand_name: str,
        city: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        爬取单个站点，返回结构化数据列表
        """
        if site_id not in self.sites:
            raise ValueError(f"未知站点: {site_id}")

        site = self.sites[site_id]
        if not site.enabled:
            logger.warning(f"站点 {site_id} 已禁用")
            return []

        # 如果配置了自定义 extractor，走插件逻辑
        if site.extractor:
            return self._run_extractor(site, brand_id, brand_name, city, **kwargs)

        url = self._build_url(site, brand_name=brand_name, city=city, **kwargs)
        logger.info(f"[{site_id}] 请求: {url}")

        html_text = self._fetch(url, site)
        decoder = self._maybe_build_decoder(html_text, site)

        root = etree.HTML(html_text)
        items = root.xpath(site.selectors.get("list", "//body"))
        results = []

        for idx, item in enumerate(items):
            record = self._extract_fields(item, site, decoder, idx)
            if record:
                # 补充元数据
                record.update(
                    {
                        "site_id": site_id,
                        "brand_id": brand_id,
                        "brand_name": brand_name,
                        "city": city,
                        "url": url,
                    }
                )
                results.append(record)

        self._sleep(site)
        return results

    def _build_url(
        self,
        site: SiteConfig,
        brand_name: str,
        city: Optional[str] = None,
        **kwargs,
    ) -> str:
        params = {**site.params}
        if city:
            params["city"] = city
        params["brand_name"] = brand_name
        params["keyword"] = brand_name

        # 也允许外部传入额外变量
        params.update(kwargs)
        return site.base_url.format(**params)

    def _fetch(self, url: str, site: SiteConfig) -> str:
        if site.method == "GET":
            resp = requests.get(url, headers=site.headers, timeout=site.timeout)
        elif site.method == "POST":
            resp = requests.post(url, headers=site.headers, timeout=site.timeout)
        else:
            raise ValueError(f"不支持的 HTTP 方法: {site.method}")

        resp.raise_for_status()
        resp.encoding = site.encoding
        return resp.text

    def _maybe_build_decoder(
        self, html_text: str, site: SiteConfig
    ) -> Optional[CssFontDecoder]:
        if not site.css.get("enabled"):
            return None

        conf = site.css
        try:
            decoder = CssFontDecoder.build_from_page(
                html_text=html_text,
                css_url_regex=conf.get("css_url_regex"),
                svg_regex_template=conf.get("svg_regex_template"),
                class_tag_regex=conf.get("class_tag_regex"),
                font_size=conf.get("font_size", 12),
            )
            return decoder
        except Exception as e:
            logger.warning(f"CSS 字体解码器构建失败: {e}")
            return None

    def _extract_fields(
        self,
        item: etree._Element,
        site: SiteConfig,
        decoder: Optional[CssFontDecoder],
        idx: int,
    ) -> Optional[Dict[str, Any]]:
        record = {}
        for field in site.fields:
            name = field["name"]
            ftype = field.get("type", "text")
            selector = field.get("selector")
            required = field.get("required", False)

            if not selector:
                continue

            value = None
            if ftype == "css_number":
                value = self._extract_css_number(item, selector, decoder)
            elif ftype == "text":
                value = self._extract_text(item, selector)
            elif ftype == "attr":
                attr = field.get("attr", "href")
                value = self._extract_attr(item, selector, attr)

            if value is None and required:
                logger.debug(f"字段 {name} 未解析到，跳过该条")
                return None

            record[name] = value

        if not record:
            return None
        return record

    def _extract_text(self, item: etree._Element, selector: str) -> Optional[str]:
        try:
            nodes = item.xpath(selector)
            if not nodes:
                return None
            if isinstance(nodes[0], etree._ElementUnicodeResult):
                return str(nodes[0]).strip()
            return nodes[0].text_content().strip()
        except Exception as e:
            logger.debug(f"提取文本失败: {e}")
            return None

    def _extract_attr(
        self, item: etree._Element, selector: str, attr: str
    ) -> Optional[str]:
        try:
            node = item.xpath(selector)[0]
            if isinstance(node, etree._Element):
                return node.get(attr)
            return None
        except Exception:
            return None

    def _extract_css_number(
        self,
        item: etree._Element,
        selector: str,
        decoder: Optional[CssFontDecoder],
    ) -> Optional[int]:
        """
        提取 CSS 字体反爬编码的数字
        selector 返回的节点中，文本节点直接作为数字，<span class="..."> 用 decoder 解码
        """
        if decoder is None:
            return None

        try:
            nodes = item.xpath(selector)
        except Exception:
            return None

        class_names = []
        plain_digits = []
        for node in nodes:
            if isinstance(node, etree._Element):
                cls = node.get("class")
                if cls:
                    class_names.append(cls)
            elif isinstance(node, etree._ElementUnicodeResult):
                text = str(node).strip()
                if text.isdigit():
                    plain_digits.append(text)

        if class_names:
            return decoder.decode_number(class_names)
        if plain_digits:
            return int("".join(plain_digits))
        return None

    def _run_extractor(
        self,
        site: SiteConfig,
        brand_id: str,
        brand_name: str,
        city: Optional[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """加载并执行自定义 extractor 插件"""
        module_path, func_name = site.extractor.rsplit(":", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        url = self._build_url(site, brand_name, city, **kwargs)

        # 把外部传入的额外参数（如 place）注入 site.params，供 extractor 读取
        extra_params = {k: v for k, v in kwargs.items() if v is not None}
        if extra_params:
            site.params = {**site.params, **extra_params}

        # WebBridge 等类 extractor 通常自己管理请求，默认不预取静态 HTML
        prefetch_html = site.params.get("prefetch_html", False)
        html_text = self._fetch(url, site) if prefetch_html else ""

        return func(
            html_text=html_text,
            brand_id=brand_id,
            brand_name=brand_name,
            city=city,
            url=url,
            site=site,
        )

    def _sleep(self, site: SiteConfig) -> None:
        delay = random.uniform(*site.delay)
        logger.debug(f"sleep {delay:.2f}s")
        time.sleep(delay)


def _save_raw_records(
    site_id: str,
    records: List[Dict[str, Any]],
    brand_id: str,
    city: Optional[str],
    crawl_date: str,
) -> int:
    """
    把爬虫原始结果写入对应的原始数据表（维度表/原始表分层架构）。

    - xiaohongshu_webbridge → xhs_notes
    - dianping_webbridge    → dp_shop_metrics（并自动登记 malls）

    Returns:
        成功写入的行数
    """
    from brandpulse.storage.modules.mall_heat_repository import (
        DpShopMetricRepository,
        MallRepository,
        XhsNoteRepository,
        make_mall_id,
    )

    saved = 0

    if site_id == "xiaohongshu_webbridge":
        repo = XhsNoteRepository()
        for r in records:
            if not r.get("note_id"):
                continue
            note = {
                "note_id": r["note_id"],
                "brand_id": brand_id,
                "city": city,
                "mall_name": r.get("place"),
                "title": r.get("title"),
                "author_name": r.get("author_name"),
                "likes": r.get("likes"),
                "publish_time": r.get("publish_time"),
                "note_url": r.get("url"),
                "keyword": r.get("keyword"),
                "crawl_date": crawl_date,
            }
            if repo.upsert_note(note):
                saved += 1

    elif site_id == "dianping_webbridge":
        repo = DpShopMetricRepository()
        mall_repo = MallRepository()
        for r in records:
            if not r.get("shop_name"):
                continue
            place = r.get("place")
            # shop_text 最后一段通常是商圈，如 "咖啡 | 观前街地区"
            business_area = None
            if r.get("shop_text") and "|" in r["shop_text"]:
                business_area = r["shop_text"].rsplit("|", 1)[-1].strip() or None
            shop = {
                "shop_name": r["shop_name"],
                "city": city,
                "crawl_date": crawl_date,
                "brand_id": brand_id,
                "place": place,
                "score": r.get("score"),
                "review_count": r.get("review_count"),
                "avg_price": r.get("avg_price"),
                "business_area": business_area,
                "shop_text": r.get("shop_text"),
                "source_url": r.get("url"),
            }
            if repo.upsert_shop_metric(shop):
                saved += 1
            # 自动登记商场维度
            if place:
                mall_repo.upsert_mall({
                    "mall_id": make_mall_id(city, place),
                    "mall_name": place,
                    "city": city,
                    "district": None,
                    "business_area": business_area,
                    "address": None,
                    "longitude": None,
                    "latitude": None,
                    "is_our_mall": False,
                    "data_source": "dianping_webbridge",
                })

    return saved


# 写入原始数据表后不再写旧 brand_metrics 的站点
_RAW_TABLE_SITES = {"xiaohongshu_webbridge", "dianping_webbridge"}


def run_from_config(site_id: str, brand_id: str, brand_name: str, city: Optional[str] = None, **kwargs):
    """
    便捷入口：从配置文件运行单个站点。

    数据流向（对应 docs/品牌热度布局分布_数据表设计.drawio）：
    1. 原始数据 → xhs_notes / dp_shop_metrics（webbridge 站点）
    2. 每日聚合 → brand_heat_daily
    3. 本地 JSON 缓存 → data/processed/metrics_*.json（全量备份）
    4. 其它站点沿用旧 brand_metrics 路径

    kwargs 中的额外参数（如 place）会透传给站点 extractor。
    """
    from brandpulse.storage.modules.file_repository import (
        FileMetricsRepository,
        is_db_disabled,
    )
    from brandpulse.storage.modules.mall_heat_repository import BrandHeatRepository

    crawler = GenericWebCrawler()
    records = crawler.crawl_site(site_id, brand_id=brand_id, brand_name=brand_name, city=city, **kwargs)

    today = time.strftime("%Y-%m-%d")
    place = kwargs.get("place")

    # 1. 原始数据表
    raw_saved = _save_raw_records(site_id, records, brand_id, city, today)

    # 2. 每日聚合热度（只聚合本次采集的平台；小红书非商场维度，mall_name 置空）
    heat_saved = 0
    if site_id in _RAW_TABLE_SITES and city:
        heat_repo = BrandHeatRepository()
        if site_id == "xiaohongshu_webbridge":
            agg = heat_repo.aggregate_for_brand_city(
                brand_id=brand_id, city=city, stat_date=today,
                mall_name="", platform="xiaohongshu",
            )
        else:
            agg = heat_repo.aggregate_for_brand_city(
                brand_id=brand_id, city=city, stat_date=today,
                mall_name=place or "", platform="dianping",
            )
        heat_saved = sum(agg.values())

    # 3. brand_metrics（webbridge 站点已由原始表承载，跳过）+ JSON 缓存
    db_disabled = is_db_disabled()
    metrics_repo = None if (db_disabled or site_id in _RAW_TABLE_SITES) else MetricsRepository()
    file_repo = FileMetricsRepository()
    db_saved = 0
    file_saved = 0

    for idx, record in enumerate(records):
        # 兼容不同平台的字段命名
        likes = record.get("likes") or record.get("like_count") or 0
        comments = record.get("comments") or record.get("comment_count") or 0
        collects = record.get("collects") or record.get("collect_count") or 0
        shares = record.get("shares") or record.get("share_count") or 0
        social_mentions = record.get("social_mentions") or (
            1 if record.get("note_id") else None
        )

        metric = {
            "metric_id": f"{brand_id}_{city or 'all'}_{site_id}_{int(time.time())}_{idx}",
            "brand_id": brand_id,
            "metric_date": today,
            "platform": site_id,
            "overall_score": record.get("score"),
            "review_count": comments or record.get("review_count"),
            "avg_price": record.get("avg_price"),
            "social_mentions": social_mentions,
            "sentiment_positive": likes,
            "sentiment_negative": collects,
            "city_count": 1 if city else None,
            "data_source": record.get("url", ""),
        }
        # 仅当至少有一个有效指标时才保存
        if any([metric["review_count"], metric["social_mentions"], likes, collects, shares]):
            if metrics_repo and metrics_repo.upsert_metric(metric):
                db_saved += 1
            if file_repo.upsert_metric(metric):
                file_saved += 1

    logger.info(
        f"[{site_id}] 原始表 {raw_saved} 条，热度聚合 {heat_saved} 行，"
        f"brand_metrics {db_saved} 条，JSON 缓存 {file_saved}/{len(records)} 条"
    )
    return {
        "saved": db_saved,
        "raw_saved": raw_saved,
        "heat_saved": heat_saved,
        "cached": file_saved,
        "records": records,
    }
