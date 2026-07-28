"""
BrandPulse 主入口



# 品牌 × 城市（自动跑大众点评 + 小红书）
python main.py crawl --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州

# 商场 × 品类（自动跑大众点评 + 小红书）
python main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州

# 仅大众点评，限定商场
python main.py crawl --site dianping_webbridge --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州 --place 苏州中心
"""
import argparse
import hashlib
import sys
from pathlib import Path

# tests 目录位于项目根目录，运行入口在 src/，需要把项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brandpulse.config.modules.config import Config
from brandpulse.collectors.stage import stage1_collect_coffee_stores
from brandpulse.db_clients.modules.db_clients import test_all_connections
from brandpulse.logger.modules.logger import get_logger
from brandpulse.storage.stage import stage1_build_graph, stage1_save_stores

logger = get_logger(__name__)


def _make_mall_search_id(mall: str, category: str, city: str) -> str:
    """为商场+品类搜索生成稳定的 brand_id 占位符"""
    digest = hashlib.md5(f"{city}|{mall}|{category}".encode("utf-8")).hexdigest()[:8]
    return f"MALL_{digest}"


def main():
    parser = argparse.ArgumentParser(description="BrandPulse 品牌情报Agent系统")
    parser.add_argument(
        "command",
        choices=["test", "stage1", "crawl"],
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

    args = parser.parse_args()

    if args.command == "test":
        results = test_all_connections()

        for name, status in results.items():
            if name == "neo4j" and status != "✓ 连接正常":
                print("neo4j: ✗ 跳过（未安装）")
            else:
                print(f"{name}: {status}")

        if (
            results.get("postgres") == "✓ 连接正常"
            and results.get("qdrant") == "✓ 连接正常"
        ):
            print("数据库连接测试通过")
        else:
            print("数据库连接测试失败")
            sys.exit(1)

    elif args.command == "stage1":
        logger.info("执行阶段一：品牌知识库建设")
        Config.ensure_dirs()

        # 1. 采集门店
        stores_by_brand = stage1_collect_coffee_stores.run(
            cities=args.cities,
            max_pages=args.max_pages,
            use_mock=args.use_mock,
            brand_ids=args.brand_ids,
        )

        # 2. 保存到数据库
        stats = stage1_save_stores.run(stores_by_brand)
        logger.info(f"数据保存完成: {stats}")

        # 3. 构建竞品关系图
        rel_count = stage1_build_graph.run()
        logger.info(f"关系图构建完成: {rel_count} 条关系")

    elif args.command == "crawl":
        from brandpulse.collectors.modules.generic_web_crawler import (
            GenericWebCrawler,
            run_from_config,
        )

        city = args.cities[0] if args.cities else None

        # 商场 + 品类搜索模式：
        #   --mall 苏州中心 --category 咖啡
        # 各平台 extractor 会自行拼接 mall / city 关键词
        if args.mall and args.category:
            mall_search_name = f"{args.mall} {args.category}"
            brand_name = args.brand_name or args.category
            brand_id = args.brand_id or _make_mall_search_id(
                args.mall, args.category, city or ""
            )
            place = args.place or args.mall
            logger.info(f"商场级搜索: {mall_search_name}, brand_id={brand_id}")
        elif args.mall or args.category:
            print("--mall 和 --category 必须同时指定")
            sys.exit(1)
        else:
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


if __name__ == "__main__":
    main()
