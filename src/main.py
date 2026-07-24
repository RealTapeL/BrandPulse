"""
BrandPulse 主入口
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
        choices=["test", "stage1", "dianping"],
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
        help="大众点评登录模式：弹出可视化浏览器窗口，登录后保存 cookies",
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


if __name__ == "__main__":
    main()
