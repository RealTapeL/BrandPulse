"""
BrandPulse 主入口

# 测试数据库连接
python main.py test

# 商场×品类采集（大众点评 + 小红书同步跑）
python src/backend/main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州

# 只跑单个平台
python main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州 --site dianping_webbridge
python main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州 --site xiaohongshu_webbridge

# 品牌×城市采集
python main.py crawl --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州

# 高德门店采集（mock 模式，无需 API Key）
python main.py stage1 --cities 苏州 --use-mock

# 指标计算（口碑/热度/SOV/趋势，默认取库中最新的统计日）
python main.py indicators [--date 2026-07-29]

# Agent 对话（需先在 .env 配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）
python src/backend/main.py agent                                  # 交互式多轮对话，exit/quit 退出
python src/backend/main.py agent --question "苏州中心咖啡店口碑怎么样"  # 单轮问答

# 跑测试
cd /home/lsy/BrandPulse && python -m pytest tests/ -q
"""
import argparse
import hashlib
import sys
from pathlib import Path

# tests 目录位于项目根目录，运行入口在 src/backend/，需要把项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from brandpulse.config.config import Config
from brandpulse.collectors.stage import stage1_collect_coffee_stores
from brandpulse.db_clients.postgres_client import test_connection
from brandpulse.logger.logger import get_logger
from brandpulse.storage.stage import stage1_save_stores

logger = get_logger(__name__)


def _make_mall_search_id(mall: str, category: str, city: str) -> str:
    """为商场+品类搜索生成稳定的 brand_id 占位符"""
    digest = hashlib.md5(f"{city}|{mall}|{category}".encode("utf-8")).hexdigest()[:8]
    return f"MALL_{digest}"


def run_mall_crawl(
    mall: str,
    category: str,
    city: str = "",
    site_ids=None,
    brand_name=None,
    brand_id=None,
    place=None,
) -> dict:
    """
    商场×品类全平台采集（大众点评 + 小红书），CLI crawl 分支与 Agent 工具共用。

    Returns:
        {"sites": [...], "raw": 原始表条数, "heat": 热度聚合行数, "cached": JSON 缓存条数}
    """
    from brandpulse.collectors.crawler import (
        GenericWebCrawler,
        run_from_config,
    )

    # 商场 + 品类搜索模式：各平台 extractor 会自行拼接 mall / city 关键词
    mall_search_name = f"{mall} {category}"
    brand_name = brand_name or category
    brand_id = brand_id or _make_mall_search_id(mall, category, city)
    place = place or mall
    logger.info(f"商场级搜索: {mall_search_name}, brand_id={brand_id}")

    if site_ids is None:
        # 未指定站点时，自动执行所有已启用的平台（大众点评、小红书等）
        crawler = GenericWebCrawler()
        site_ids = crawler.list_sites()
        if not site_ids:
            raise RuntimeError("没有已启用的站点可执行，请检查 crawler_sites.yaml")
        logger.info(f"未指定 --site，自动执行 {len(site_ids)} 个已启用站点: {site_ids}")

    results = {}
    for site_id in site_ids:
        logger.info(f"[{site_id}] 开始采集")
        results[site_id] = run_from_config(
            site_id=site_id,
            brand_id=brand_id,
            brand_name=brand_name,
            city=city,
            place=place,
        )

    return {
        "sites": list(results.keys()),
        "raw": sum(r.get("raw_saved", 0) for r in results.values()),
        "heat": sum(r.get("heat_saved", 0) for r in results.values()),
        "cached": sum(r.get("cached", 0) for r in results.values()),
    }


def main():
    parser = argparse.ArgumentParser(description="BrandPulse 品牌情报Agent系统")
    parser.add_argument(
        "command",
        choices=["test", "stage1", "crawl", "indicators", "agent"],
        help="执行的命令",
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        default=["北京", "上海", "广州"],
        help="采集城市列表，如：--cities 北京 上海",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="每个城市最大采集页数",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="使用 Mock 数据（无需高德 API Key）",
    )
    parser.add_argument(
        "--brand-ids",
        nargs="+",
        default=None,
        help="指定品牌 ID 列表，如：--brand-ids LK001 KD001",
    )
    parser.add_argument(
        "--site",
        type=str,
        default=None,
        help="通用爬虫：站点 ID（在 crawler_sites.yaml 中配置）",
    )
    parser.add_argument(
        "--brand-name",
        type=str,
        default=None,
        help="通用爬虫：品牌中文名",
    )
    parser.add_argument(
        "--brand-id",
        type=str,
        default=None,
        help="通用爬虫：品牌 ID",
    )
    parser.add_argument(
        "--place",
        type=str,
        default=None,
        help="通用爬虫：限定地点/商场名，如 --place 南开大悦城（与品牌名组合搜索）",
    )
    parser.add_argument(
        "--mall",
        type=str,
        default=None,
        help="商场级搜索：指定商场名，如 --mall 苏州中心（需配合 --category 使用）",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="商场级搜索：指定品类，如 --category 咖啡（需配合 --mall 使用）",
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="指标计算：统计日期 YYYY-MM-DD，默认取库中最新的采集日",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Agent 单轮问答问题；不传则进入交互式多轮对话",
    )

    args = parser.parse_args()

    if args.command == "test":
        if test_connection():
            print("postgres: ✓ 连接正常")
            print("数据库连接测试通过")
        else:
            print("postgres: ✗ 连接失败")
            sys.exit(1)

    elif args.command == "stage1":
        logger.info("执行阶段一：品牌门店采集（高德）")
        Config.ensure_dirs()

        # 1. 采集门店
        stores_by_brand = stage1_collect_coffee_stores.run(
            cities=args.cities,
            max_pages=args.max_pages,
            use_mock=args.use_mock,
            brand_ids=args.brand_ids,
        )

        # 2. 保存到 PostgreSQL
        stats = stage1_save_stores.run(stores_by_brand)
        logger.info(f"数据保存完成: {stats}")

    elif args.command == "crawl":
        city = args.cities[0] if args.cities else None

        if args.mall and args.category:
            # 商场 + 品类搜索模式：
            #   --mall 苏州中心 --category 咖啡
            stats = run_mall_crawl(
                mall=args.mall,
                category=args.category,
                city=city or "",
                site_ids=[args.site] if args.site else None,
                brand_name=args.brand_name,
                brand_id=args.brand_id,
                place=args.place,
            )
            logger.info(
                f"全平台采集完成: 原始表 {stats['raw']} 条, 热度聚合 {stats['heat']} 行, "
                f"JSON 缓存 {stats['cached']} 条"
            )
            print(f"执行站点: {stats['sites']}")
            print(f"原始表: {stats['raw']}, 热度聚合: {stats['heat']}, JSON 缓存: {stats['cached']}")
            print("下一步: python src/backend/main.py indicators  # 刷新指标后看板自动更新")
            print("看板入口: http://192.168.0.109:8000/  (Vue3 看板)")
        elif args.mall or args.category:
            print("--mall 和 --category 必须同时指定")
            sys.exit(1)
        else:
            from brandpulse.collectors.crawler import (
                GenericWebCrawler,
                run_from_config,
            )

            brand_name = args.brand_name or args.brand_id
            if not brand_name:
                print("请指定 --brand-id 或 --brand-name，或同时指定 --mall 和 --category")
                sys.exit(1)
            brand_id = args.brand_id or args.brand_name or brand_name
            place = args.place

            if args.site:
                site_ids = [args.site]
            else:
                # 未指定站点时，自动执行所有已启用的平台（大众点评、小红书等）
                crawler = GenericWebCrawler()
                site_ids = crawler.list_sites()
                if not site_ids:
                    print("没有已启用的站点可执行，请检查 crawler_sites.yaml")
                    sys.exit(1)
                logger.info(f"未指定 --site，自动执行 {len(site_ids)} 个已启用站点: {site_ids}")

            results = {}
            for site_id in site_ids:
                logger.info(f"[{site_id}] 开始采集")
                results[site_id] = run_from_config(
                    site_id=site_id,
                    brand_id=brand_id,
                    brand_name=brand_name,
                    city=city,
                    place=place,
                )

            total_raw = sum(r.get("raw_saved", 0) for r in results.values())
            total_heat = sum(r.get("heat_saved", 0) for r in results.values())
            total_cached = sum(r.get("cached", 0) for r in results.values())
            logger.info(
                f"全平台采集完成: 原始表 {total_raw} 条, 热度聚合 {total_heat} 行, "
                f"JSON 缓存 {total_cached} 条"
            )
            print(f"执行站点: {list(results.keys())}")
            print(f"原始表: {total_raw}, 热度聚合: {total_heat}, JSON 缓存: {total_cached}")
            print("下一步: python src/backend/main.py indicators  # 刷新指标后看板自动更新")
            print("看板入口: http://192.168.0.109:8000/  (Vue3 看板)")

    elif args.command == "indicators":
        from brandpulse.indicators.pipeline import run as indicators_run

        stats = indicators_run(stat_date=args.date)
        print("指标计算完成:")
        for step, count in stats.items():
            print(f"  {step}: {count}")
        print("看板入口: http://192.168.0.109:8000/  (Vue3 看板)")

    elif args.command == "agent":
        from brandpulse.agent.agent import ask, chat_interactive

        if args.question:
            try:
                answer, _ = ask(args.question)
                print(answer)
            except RuntimeError as e:
                print(f"Agent 启动失败: {e}")
                sys.exit(1)
        else:
            chat_interactive()


if __name__ == "__main__":
    main()
