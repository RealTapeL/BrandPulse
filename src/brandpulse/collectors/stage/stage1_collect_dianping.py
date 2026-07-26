"""
阶段一：大众点评品牌指标采集

采集咖啡品牌（或指定品牌）在目标城市的点评评分/评论数/人均消费，
写入 brand_metrics 表。
"""
from typing import List

from brandpulse.collectors.modules.dianping_crawler import (
    DianpingCrawler,
    generate_mock_metrics,
)
from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger
from brandpulse.storage.modules.file_repository import FileMetricsRepository, is_db_disabled
from brandpulse.storage.modules.pg_repository import BrandRepository, MetricsRepository

logger = get_logger(__name__)


def run_login_mode() -> bool:
    """交互式登录模式：弹出浏览器窗口，登录后保存 cookies"""
    Config.ensure_dirs()
    crawler = DianpingCrawler()
    return crawler.run_login_mode()


def run(
    cities: List[str] = None,
    brand_ids: List[str] = None,
    use_mock: bool = False,
) -> dict:
    """
    采集大众点评品牌指标

    Args:
        cities: 目标城市列表
        brand_ids: 指定品牌 ID 列表；None 则读取所有 is_active 品牌
        use_mock: 是否使用 Mock 数据（无需访问点评）

    Returns:
        dict: 统计信息
    """
    Config.ensure_dirs()

    if cities is None:
        cities = ["北京", "上海", "广州"]

    brand_repo = BrandRepository()
    brands = brand_repo.list_brands(is_active=True)
    if brand_ids:
        brands = [b for b in brands if b["brand_id"] in brand_ids]

    if not brands:
        logger.warning("brands 表中未找到可用品牌，跳过点评采集")
        return {"metrics": 0, "brands": 0}

    logger.info(f"从 brands 表读取到 {len(brands)} 个品牌，开始大众点评采集")

    db_disabled = is_db_disabled()
    metrics_repo = None if db_disabled else MetricsRepository()
    file_repo = FileMetricsRepository()
    crawler = DianpingCrawler()
    total_db = 0
    total_file = 0

    for brand in brands:
        brand_id = brand["brand_id"]
        brand_name = brand["brand_name_cn"]

        if use_mock:
            metrics = generate_mock_metrics(brand_id, brand_name, cities=cities)
        else:
            keywords = brand.get("search_keywords") or brand_name
            metrics = crawler.collect_brand_metrics(
                brand_id=brand_id,
                brand_name=keywords,
                cities=cities,
            )

        db_saved = 0
        file_saved = 0
        for metric in metrics:
            if metrics_repo and metrics_repo.upsert_metric(metric):
                db_saved += 1
            if file_repo.upsert_metric(metric):
                file_saved += 1
        total_db += db_saved
        total_file += file_saved

        logger.info(f"{brand_id} 点评指标保存: PG {db_saved}/{len(metrics)}, JSONL {file_saved}/{len(metrics)}")

    return {"metrics": total_db, "cached": total_file, "brands": len(brands)}
