"""从指标和点评原始表计算启用中的自定义公式。"""
from typing import Any, Dict, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.indicators.formula_engine import FormulaEvaluationError, evaluate_formula
from brandpulse.logger.logger import get_logger
from brandpulse.storage.formula_repository import FormulaRepository

logger = get_logger(__name__)


def _contexts(stat_date: str) -> Dict[str, Dict[str, float]]:
    client = PostgresClient()
    contexts: Dict[str, Dict[str, float]] = {}
    with client.engine.connect() as conn:
        indicator_rows = conn.execute(text("""
            SELECT brand_id,
                   AVG(weighted_score) AS weighted_score,
                   AVG(heat_index) AS heat_index,
                   AVG(wow_momentum) AS wow_momentum,
                   AVG(volatility) AS volatility,
                   AVG(sov) AS sov
            FROM brand_indicators_daily
            WHERE stat_date = :stat_date AND entity_type = 'shop' AND brand_id IS NOT NULL
            GROUP BY brand_id
        """), {"stat_date": stat_date}).mappings().all()
        for row in indicator_rows:
            values = {key: float(row[key]) for key in (
                "weighted_score", "heat_index", "wow_momentum", "volatility", "sov"
            ) if row[key] is not None}
            aliases = {
                "reputation": "weighted_score",
                "heat": "heat_index",
                "momentum": "wow_momentum",
            }
            for alias, source in aliases.items():
                if source in values:
                    values[alias] = values[source]
            contexts[str(row["brand_id"])] = values

        raw_rows = conn.execute(text("""
                SELECT brand_id,
                       SUM(review_count)::numeric AS review_count,
                       AVG(avg_price)::numeric AS avg_price,
                       AVG(score)::numeric AS score
                FROM dp_shop_metrics
                WHERE crawl_date = :stat_date
                GROUP BY brand_id
            """), {"stat_date": stat_date}).mappings().all()
        for row in raw_rows:
            values = contexts.setdefault(str(row["brand_id"]), {})
            for key in ("review_count", "avg_price", "score"):
                if row[key] is not None:
                    values[key] = float(row[key])
    return contexts


def compute_custom_formulas(stat_date: Optional[str] = None, formula_id: Optional[str] = None) -> int:
    """计算并持久化公式值；缺少真实输入时跳过并记录原因。"""
    client = PostgresClient()
    if not stat_date:
        with client.engine.connect() as conn:
            latest = conn.execute(text("SELECT MAX(stat_date) FROM brand_indicators_daily")).scalar()
        if not latest:
            return 0
        stat_date = str(latest)

    repo = FormulaRepository()
    formulas = repo.list_enabled()
    if formula_id:
        formulas = [formula for formula in formulas if formula["id"] == formula_id]
    if not formulas:
        return 0

    contexts = _contexts(stat_date)
    values = []
    for formula in formulas:
        params: Dict[str, Any] = {}
        for item in formula.get("params") or []:
            try:
                params[item["key"]] = float(item["value"])
            except (KeyError, TypeError, ValueError):
                logger.error("[公式] %s 参数 %r 不是数字，跳过", formula["name"], item)
                params = {}
                break
        if not params and formula.get("params"):
            continue
        for brand_id, context in contexts.items():
            try:
                # 真实数据变量优先于同名参数，避免 review_count=0 之类的
                # 表单默认值覆盖数据库中的真实评价数。
                value = evaluate_formula(formula["expression"], {**params, **context})
            except FormulaEvaluationError as exc:
                logger.warning("[公式] %s/%s 无法计算: %s", formula["name"], brand_id, exc)
                continue
            values.append({
                "formula_id": formula["id"],
                "brand_id": brand_id,
                "stat_date": stat_date,
                "value": value,
                "detail": {
                    "expression": formula["expression"],
                    "input_fields": sorted(context.keys()),
                    "source_stat_date": stat_date,
                },
            })
    saved = repo.upsert_values(values)
    logger.info("[公式] %s 计算并写入 %s 条真实结果", stat_date, saved)
    return saved
