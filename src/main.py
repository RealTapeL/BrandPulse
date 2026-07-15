"""
BrandPulse 主入口
"""
import argparse

from brandpulse.utils.config.modules.config import Config
from brandpulse.utils.data_collection.stage import stage1_collect_coffee_stores
from brandpulse.utils.db_clients.stage import test_connections
from brandpulse.utils.logger.modules.logger import get_logger
from brandpulse.utils.storage.stage import stage1_build_graph, stage1_save_stores

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="BrandPulse 品牌情报Agent系统")
    parser.add_argument(
        "command",
        choices=["test", "stage1"],
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

    args = parser.parse_args()

    if args.command == "test":
        test_connections.run()

    elif args.command == "stage1":
        logger.info("执行阶段一：品牌知识库建设")
        Config.ensure_dirs()

        # 1. 采集门店
        stores_by_brand = stage1_collect_coffee_stores.run(
            cities=args.cities,
            max_pages=args.max_pages,
            use_mock=args.use_mock,
        )

        # 2. 保存到数据库
        stats = stage1_save_stores.run(stores_by_brand)
        logger.info(f"数据保存完成: {stats}")

        # 3. 构建竞品关系图
        rel_count = stage1_build_graph.run()
        logger.info(f"关系图构建完成: {rel_count} 条关系")


if __name__ == "__main__":
    main()
