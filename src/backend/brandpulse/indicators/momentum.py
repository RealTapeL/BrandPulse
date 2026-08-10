"""
趋势指标：周环比动量 + 波动率

- 动量 wow = (本期热度 - 上期热度) / 上期热度
- 波动率 = 近 N 期热度标准差 / 均值（变异系数）

招商筛选用法：高动量 + 低波动 = 正在起势且非网红泡沫的品牌。

注意：依赖 heat.py 产出的固定基准热度指数（跨天可比）。
数据积累不足 2 期时动量为 NULL，属于正常状态。
"""
import statistics
from typing import Dict, List, Optional, Tuple

from brandpulse.indicators.repository import IndicatorRepository
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

WINDOW = 4  # 波动率窗口期数


def momentum_and_volatility(series: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """
    由热度序列计算动量与波动率（纯函数，便于单测）。

    Args:
        series: 按日期升序的热度值（至少 1 个）

    Returns:
        (wow_momentum, volatility)，数据不足时为 None
    """
    if not series:
        return None, None

    wow = None
    if len(series) >= 2 and series[-2] > 0:
        wow = (series[-1] - series[-2]) / series[-2]

    vol = None
    window = series[-WINDOW:]
    if len(window) >= 2:
        mean = statistics.fmean(window)
        if mean > 0:
            vol = statistics.pstdev(window) / mean

    return wow, vol


def compute_momentum(stat_date: Optional[str] = None) -> List[Dict]:
    """
    为指标表中最新一期的所有实体计算动量与波动率。

    Returns:
        指标行列表（只填 wow_momentum / volatility 字段，按主键合并）
    """
    repo = IndicatorRepository()
    if not stat_date:
        stat_date = repo.latest_stat_date()
    if not stat_date:
        logger.warning("指标表无数据，跳过动量指标")
        return []

    latest = repo.list_indicators(stat_date=stat_date)
    indicators = []
    for row in latest:
        series_rows = repo.get_heat_series(
            entity_type=row["entity_type"],
            entity_name=row["entity_name"],
            city=row["city"],
            mall_name=row["mall_name"],
            limit=WINDOW,
        )
        series = [float(r["heat_index"]) for r in series_rows if r["heat_index"] is not None]
        wow, vol = momentum_and_volatility(series)
        if wow is None and vol is None:
            continue
        indicators.append({
            "stat_date": stat_date,
            "city": row["city"],
            "mall_name": row["mall_name"],
            "entity_type": row["entity_type"],
            "entity_name": row["entity_name"],
            "brand_id": row["brand_id"],
            "wow_momentum": round(wow, 4) if wow is not None else None,
            "volatility": round(vol, 4) if vol is not None else None,
            "detail": {
                "metric": "momentum_volatility",
                "heat_series": [round(s, 2) for s in series],
                "window": WINDOW,
            },
        })

    logger.info(f"[趋势] {stat_date} 计算 {len(indicators)} 个实体（数据不足 2 期的已跳过）")
    return indicators
