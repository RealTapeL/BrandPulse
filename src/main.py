"""
BrandPulse 主入口



# 品牌 × 城市
python main.py crawl --site dianping_webbridge --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州

# 商场 × 品类
python main.py crawl --site dianping_webbridge --brand-id LK001 --brand-name 咖啡 --cities 苏州 --place 苏州中心

# 商场 × 品牌
python main.py crawl --site dianping_webbridge --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州 --place 苏州中心
"""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description="BrandPulse 品牌情报Agent系统")
    parser.add_argument(
        "command",
        choices=["test", "stage1", "dianping", "crawl"],
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
        help="使用 Mock 数据（无需高德 API Key / 大众点评）",
    )
    parser.add_argument(
        "--brand-ids",
        nargs="+",
        default=None,
        help="指定品牌 ID 列表，如：--brand-ids LK001 KD001",
    )
    parser.add_argument(
        "--login-mode",
        action="store_true",
        help="登录模式：弹出可视化浏览器窗口，登录后保存 cookies（配合 --site 使用）",
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

    elif args.command == "dianping":
        from brandpulse.collectors.stage import stage1_collect_dianping

        if args.login_mode:
            logger.info("执行大众点评登录模式")
            ok = stage1_collect_dianping.run_login_mode()
            if ok:
                logger.info("Cookies 保存成功，可以运行正常采集命令")
            else:
                logger.warning("未保存到 cookies，请重试")
                sys.exit(1)
        else:
            logger.info("执行大众点评品牌指标采集")
            stats = stage1_collect_dianping.run(
                cities=args.cities,
                brand_ids=args.brand_ids,
                use_mock=args.use_mock,
            )
            logger.info(f"大众点评指标采集完成: {stats}")

    elif args.command == "crawl":
        from brandpulse.collectors.modules.generic_web_crawler import (
            GenericWebCrawler,
            run_from_config,
        )

        if not args.site:
            print("请指定 --site，已配置站点:")
            crawler = GenericWebCrawler()
            for sid, site in crawler.sites.items():
                status = "启用" if site.enabled else "禁用"
                print(f"  {sid:20s} [{status}] {site.name}")
            sys.exit(1)

        # 登录模式：动态调用 extractor 的 run_login_mode 函数
        if args.login_mode:
            crawler = GenericWebCrawler()
            site = crawler.sites.get(args.site)
            if not site or not site.extractor:
                print(f"站点 {args.site} 未配置 extractor，暂不支持登录模式")
                sys.exit(1)

            module_path, func_name = site.extractor.rsplit(":", 1)
            if func_name != "extract_search":
                print(f"站点 {args.site} 的 extractor 不是标准 extract_search，无法自动推断登录函数")
                sys.exit(1)

            login_func_name = "run_login_mode"
            module = __import__(module_path, fromlist=[login_func_name])
            login_func = getattr(module, login_func_name, None)
            if not login_func:
                print(f"站点 {args.site} 未实现 {login_func_name}")
                sys.exit(1)

            logger.info(f"[{args.site}] 执行登录模式")
            ok = login_func()
            if ok:
                logger.info("Cookies 保存成功")
            else:
                logger.warning("未保存到 cookies")
                sys.exit(1)
            return

        brand_name = args.brand_name or args.brand_id
        if not brand_name:
            print("请指定 --brand-id 或 --brand-name")
            sys.exit(1)

        city = args.cities[0] if args.cities else None
        result = run_from_config(
            site_id=args.site,
            brand_id=args.brand_id or args.brand_name,
            brand_name=brand_name,
            city=city,
            place=args.place,
        )
        logger.info(f"通用爬虫采集完成: {result}")


if __name__ == "__main__":
    main()
