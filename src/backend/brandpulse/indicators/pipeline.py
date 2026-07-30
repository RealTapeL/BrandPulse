"""
指标计算编排入口

run() 按顺序执行全部指标计算并写入 brand_indicators_daily。
单个指标失败不影响其它指标（优雅降级）。

用法：
    python main.py indicators            # 按最新采集日重算
    python main.py indicators --date 2026-07-29
"""
from typing import Dict, Optional

from brandpulse.indicators import heat, momentum, reputation, share
from brandpulse.indicators.repository import IndicatorRepository
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

# (名称, 计算函数)，按依赖顺序排列：动量依赖热度，必须最后算
STEPS = [
    ("口碑", reputation.compute_weighted_scores),
    ("热度", heat.compute_heat),
    ("SOV", share.compute_sov),
    ("趋势", momentum.compute_momentum),
]


def run(stat_date: Optional[str] = None) -> Dict[str, int]:
    """
    执行全量指标计算（幂等，可反复重跑）。

    Returns:
        {指标名: 写入行数}
    """
    repo = IndicatorRepository()
    stats: Dict[str, int] = {}

    for name, func in STEPS:
        try:
            rows = func(stat_date)
            saved = repo.upsert_indicators(rows) if rows else 0
            stats[name] = saved
        except Exception as e:
            logger.error(f"[指标] {name} 计算失败（已跳过，不影响其它指标）: {e}")
            stats[name] = 0

    total = sum(stats.values())
    logger.info(f"[指标] 全部完成: {stats}, 共写入 {total} 行")
    return stats


if __name__ == "__main__":
    run()
