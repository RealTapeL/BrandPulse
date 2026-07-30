"""
BrandPulse Agent 工具集

每个工具函数带清晰 docstring，注册到 Pydantic AI Agent 后供 LLM 决策调用。
所有工具返回 str，方便 LLM 直接阅读。
"""
import re
from typing import Optional

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

# query_db 单次最大返回行数（超出截断并说明）
MAX_ROWS = 100

# 只读 SQL 校验：拒绝的写操作/高危关键字
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE"
    r"|COPY|EXECUTE|CALL|LOCK|VACUUM)\b",
    re.IGNORECASE,
)

# 主要业务表说明（配合 information_schema 的列信息返回给 LLM，帮助其写 SQL）
TABLE_COMMENTS = {
    "dp_shop_metrics": (
        "大众点评门店指标表（爬虫直接写入）。主键 (shop_name, city, crawl_date)。"
        "关键列：brand_id、place（商场/地点）、score（星级评分）、review_count（评论数）、"
        "avg_price（人均消费）、business_area（商圈）"
    ),
    "xhs_notes": (
        "小红书笔记表（爬虫直接写入）。主键 note_id。"
        "关键列：brand_id、mall_name、title、author_name、likes（点赞数）、"
        "publish_time、crawl_date"
    ),
    "brand_heat_daily": (
        "品牌热度日聚合表，每 品牌×城市×商场×日期×平台 一行。"
        "关键列：stat_date、brand_id、mall_name、platform、mentions（提及量）、"
        "total_likes、avg_likes、dp_review_count、dp_shop_count、dp_avg_price"
    ),
    "brand_indicators_daily": (
        "品牌指标日表（口碑/热度/SOV/趋势计算结果，由 run_indicators 工具刷新）。"
        "指标口径以 indicators 模块为准"
    ),
}


def _validate_readonly_sql(sql: str) -> str:
    """
    校验 SQL 为只读单语句：仅允许 SELECT/WITH 开头，拒绝多语句与写操作关键字。

    Returns:
        去掉首尾空白与结尾分号的 SQL

    Raises:
        ValueError: SQL 不符合只读约束
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("SQL 不能为空")
    if ";" in cleaned:
        raise ValueError("只允许单条 SQL 语句，拒绝分号多语句")
    first_word = cleaned.split(None, 1)[0].upper()
    if first_word not in ("SELECT", "WITH"):
        raise ValueError(f"只允许 SELECT/WITH 只读查询，拒绝: {first_word}")
    match = _FORBIDDEN_KEYWORDS.search(cleaned)
    if match:
        raise ValueError(f"SQL 包含被禁止的关键字: {match.group(0).upper()}")
    return cleaned


def query_db(sql: str) -> str:
    """
    对 BrandPulse PostgreSQL 数据库执行只读 SQL 查询（仅限 SELECT/WITH 单语句，
    最多返回 100 行）。先用 list_tables 了解表结构再写 SQL。

    Args:
        sql: 只读 SQL，如 SELECT shop_name, score FROM dp_shop_metrics LIMIT 10

    Returns:
        表头 + 各行内容的文本表格；被拦截或出错时返回原因说明
    """
    try:
        cleaned = _validate_readonly_sql(sql)
    except ValueError as e:
        return f"SQL 被拒绝: {e}"

    try:
        client = PostgresClient()
        with client.engine.connect() as conn:
            from sqlalchemy import text

            result = conn.execute(text(cleaned))
            columns = list(result.keys())
            rows = result.fetchmany(MAX_ROWS + 1)
    except Exception as e:
        return f"查询执行失败: {e}"

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    lines = [" | ".join(columns)]
    lines.extend(" | ".join(str(v) for v in row) for row in rows)
    output = "\n".join(lines) if rows else "（查询结果为空）"
    if truncated:
        output += f"\n... 结果超过 {MAX_ROWS} 行，已截断，请加 LIMIT 或聚合条件"
    return output


def run_indicators(stat_date: Optional[str] = None) -> str:
    """
    运行指标计算管道（口碑/热度/SOV/趋势），结果写入 brand_indicators_daily。
    采集新数据后应调用本工具刷新指标。

    Args:
        stat_date: 统计日期 YYYY-MM-DD；不传则取库中最新的采集日

    Returns:
        各指标写入行数的统计
    """
    from brandpulse.indicators.pipeline import run as pipeline_run

    try:
        stats = pipeline_run(stat_date=stat_date)
    except Exception as e:
        return f"指标计算失败: {e}"
    detail = ", ".join(f"{k}: {v} 行" for k, v in stats.items())
    return f"指标计算完成（统计日: {stat_date or '库中最新采集日'}）: {detail}"


def crawl(mall: str, category: str, cities: str = "苏州") -> str:
    """
    驱动真实浏览器采集指定商场×品类的数据（大众点评 + 小红书同步跑），
    耗时约 40 秒。采集完成后建议调用 run_indicators 刷新指标。

    Args:
        mall: 商场名，如 苏州中心
        category: 品类，如 咖啡
        cities: 城市名，默认 苏州

    Returns:
        各站点采集条数统计
    """
    import sys
    from pathlib import Path

    # main.py 不在包内，把 src/backend 目录加入 sys.path 再导入
    src_dir = str(Path(__file__).resolve().parents[2])
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from main import run_mall_crawl

    try:
        stats = run_mall_crawl(mall=mall, category=category, city=cities)
    except Exception as e:
        return f"采集失败: {e}"
    return (
        f"采集完成: 站点 {stats['sites']}，原始表 {stats['raw']} 条，"
        f"热度聚合 {stats['heat']} 行，JSON 缓存 {stats['cached']} 条"
    )


def list_tables() -> str:
    """
    列出 BrandPulse 数据库主要业务表及其列说明，写 SQL 前应先调用本工具。

    Returns:
        每个表的用途说明 + 列名/类型/是否可空
    """
    sql = """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(:tables)
        ORDER BY table_name, ordinal_position
    """
    try:
        client = PostgresClient()
        with client.engine.connect() as conn:
            from sqlalchemy import text

            rows = conn.execute(
                text(sql), {"tables": list(TABLE_COMMENTS.keys())}
            ).fetchall()
    except Exception as e:
        return f"查询表结构失败: {e}"

    if not rows:
        return "未找到主要业务表（数据库可能尚未初始化）"

    lines = []
    current_table = None
    for table_name, column_name, data_type, is_nullable in rows:
        if table_name != current_table:
            current_table = table_name
            comment = TABLE_COMMENTS.get(table_name, "")
            lines.append(f"\n## {table_name}\n{comment}")
        nullable = "可空" if is_nullable == "YES" else "非空"
        lines.append(f"  - {column_name} ({data_type}, {nullable})")
    return "\n".join(lines).strip()
