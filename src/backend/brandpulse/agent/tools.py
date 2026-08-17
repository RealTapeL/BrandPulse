"""
BrandPulse Agent 工具集

每个工具函数带清晰 docstring，注册到 Pydantic AI Agent 后供 LLM 决策调用。
所有工具返回 str，方便 LLM 直接阅读。
"""
import json
import re
from typing import Any, Literal, Optional

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


def _json_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def list_monitoring_scopes() -> str:
    """列出可查询的监测范围及其最新可信快照状态。"""
    from brandpulse.storage.trusted_data_repository import TrustedScopeRepository

    scopes = TrustedScopeRepository().list()
    return _json_output({
        "evidence_type": "monitoring_scope_registry",
        "items": [{
            "scope_id": scope["scope_id"], "city": scope["city"], "mall_name": scope["mall_name"],
            "category": scope["category"], "latest_snapshot_id": scope.get("latest_snapshot_id"),
            "latest_snapshot_at": scope.get("latest_snapshot_at"),
            "latest_snapshot_status": scope.get("latest_snapshot_status"),
            "quality_grade": scope.get("latest_snapshot_quality_grade"),
            "data_mode": scope.get("latest_snapshot_data_mode"),
        } for scope in scopes],
        "notice": "范围按城市×商场×品类隔离；旧 dataset key 不是品牌实体。",
    })


def get_scope_snapshot_evidence(scope_id: str, snapshot_id: Optional[str] = None) -> str:
    """读取一个 ready/published 快照的范围、来源、指标口径和质量证据。"""
    from brandpulse.api.dashboard import build_dashboard
    from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository

    scope = TrustedScopeRepository().get(scope_id)
    if not scope:
        return "未找到监测范围，不能生成数据结论。"
    snapshots = SnapshotRepository()
    snapshot = snapshots.get(snapshot_id) if snapshot_id else snapshots.latest_released(scope_id)
    if not snapshot or snapshot["scope_id"] != scope_id:
        return "当前范围没有指定的 ready/published 可信快照。"
    if snapshot["status"] not in {"ready", "published"}:
        return "快照尚未发布，不能用于正式业务结论。"
    dashboard = build_dashboard(scope_id=scope_id, snapshot_id=snapshot["snapshot_id"])
    return _json_output({
        "evidence_type": "trusted_snapshot",
        "scope": {key: scope[key] for key in ("scope_id", "city", "mall_name", "category")},
        "snapshot": {
            "snapshot_id": snapshot["snapshot_id"], "observed_at": snapshot.get("observed_at"),
            "status": snapshot["status"], "quality_grade": snapshot.get("quality_grade"),
            "freshness_status": snapshot.get("freshness_status"), "data_mode": snapshot.get("data_mode"),
            "source_coverage": snapshot.get("source_coverage") or {},
            "source_results": snapshot.get("source_results") or [],
        },
        "metric_version": "snapshot-v2",
        "scope_metrics": dashboard.get("metric_summary") or [],
        "notice": "公开来源仅用于公开口碑、内容和竞争线索；不代表销售、坪效、租户健康度或自动招商结论。",
    })


def get_brand_evidence(brand_id: str, scope_id: str, snapshot_id: Optional[str] = None) -> str:
    """读取已人工确认映射到真实品牌的公开观测及其快照证据。"""
    from sqlalchemy import text

    from brandpulse.storage.trusted_data_repository import SnapshotRepository, TrustedScopeRepository

    scope = TrustedScopeRepository().get(scope_id)
    if not scope:
        return "未找到监测范围。"
    snapshots = SnapshotRepository()
    snapshot = snapshots.get(snapshot_id) if snapshot_id else snapshots.latest_released(scope_id)
    if not snapshot or snapshot["scope_id"] != scope_id or snapshot["status"] not in {"ready", "published"}:
        return "没有可用于品牌洞察的 ready/published 可信快照。"
    client = PostgresClient()
    with client.engine.connect() as conn:
        brand = conn.execute(
            text("SELECT brand_id, brand_name_cn, brand_name_en FROM brands WHERE brand_id = :brand_id"),
            {"brand_id": brand_id},
        ).mappings().first()
        rows = conn.execute(text("""
            SELECT observation.observation_id, observation.source_record_key, observation.source_url,
                   observation.observed_date, store.store_name, store.city, store.mall_name,
                   NULLIF(observation.payload ->> 'score', '')::numeric AS score,
                   NULLIF(observation.payload ->> 'review_count', '')::int AS review_count,
                   MAX(metric.value) FILTER (WHERE metric.metric_key = 'bayesian_reputation') AS bayesian_reputation,
                   MAX(metric.value) FILTER (WHERE metric.metric_key = 'dianping_review_share') AS dianping_review_share,
                   (ARRAY_AGG(metric.evidence) FILTER (WHERE metric.metric_key = 'bayesian_reputation'))[1] AS reputation_evidence
            FROM raw_observations AS observation
            LEFT JOIN stores AS store ON store.store_id = observation.store_id
            LEFT JOIN metric_observations AS metric
              ON metric.snapshot_id = :snapshot_id AND metric.entity_type = 'shop'
             AND metric.entity_key = observation.source_record_key
            WHERE observation.scope_id = :scope_id
              AND observation.collection_run_id = :collection_run_id
              AND observation.brand_id = :brand_id
              AND observation.entity_mapping_status = 'confirmed'
              AND observation.quality_status = 'accepted'
            GROUP BY observation.observation_id, store.store_name, store.city, store.mall_name
            ORDER BY review_count DESC NULLS LAST, observation.source_record_key
            LIMIT 100
        """), {
            "scope_id": scope_id, "snapshot_id": snapshot["snapshot_id"],
            "collection_run_id": snapshot["collection_run_id"], "brand_id": brand_id,
        }).mappings().all()
    return _json_output({
        "evidence_type": "confirmed_brand_public_observations",
        "scope": {key: scope[key] for key in ("scope_id", "city", "mall_name", "category")},
        "snapshot_id": snapshot["snapshot_id"], "data_cutoff_at": snapshot.get("observed_at"),
        "quality_grade": snapshot.get("quality_grade"), "brand": dict(brand) if brand else None,
        "confirmed_observations": [dict(row) for row in rows],
        "exclusion_notice": "未确认映射的原始记录不会被归因到该品牌；没有记录不等于品牌不存在。",
    })


def list_opportunity_evidence(scope_id: str, snapshot_id: Optional[str] = None) -> str:
    """列出当前快照生成的机会、风险和数据质量信号及其规则证据。"""
    from brandpulse.opportunities.service import OpportunityService

    try:
        return _json_output({"evidence_type": "opportunity_signals", **OpportunityService().list(
            scope_id=scope_id, snapshot_id=snapshot_id, limit=100,
        )})
    except ValueError as exc:
        return f"机会证据不可用：{exc}"


def list_data_quality_evidence(scope_id: Optional[str] = None) -> str:
    """查询开放的数据质量问题；可按范围筛选，返回的是治理证据而非品牌判断。"""
    from brandpulse.storage.data_governance_repository import DataGovernanceRepository

    result = DataGovernanceRepository().list_issues(status="open", severity=None, limit=200, offset=0)
    items = result["items"]
    if scope_id:
        items = [item for item in items if (item.get("details") or {}).get("scope_id") == scope_id]
    return _json_output({
        "evidence_type": "data_quality_issues", "scope_id": scope_id,
        "items": items, "notice": "数据问题必须先治理，不能被解释为品牌机会或经营风险。",
    })


def list_business_case_evidence(scope_id: Optional[str] = None) -> str:
    """查询待处理事项的来源、状态、负责人和反馈，支持行动闭环而非自动结案。"""
    from brandpulse.cases.service import BusinessCaseService

    return _json_output({"evidence_type": "business_cases", **BusinessCaseService().list(
        scope_id=scope_id, limit=100,
    )})


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


def external_research(
    mode: Literal["status", "read_url", "search"] = "status",
    url: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 5,
) -> str:
    """读取公开外部信息，不写入 BrandPulse 指标表。

    Agent-Reach 未启用或上游依赖不可用时返回明确原因；Cookie、Token 和
    账号登录态不由本工具接收或保存。
    """
    from brandpulse.agent.agent_reach import get_status, read_public_url, search_public_web

    if mode == "status":
        import json

        return json.dumps(get_status(), ensure_ascii=False, indent=2)
    if mode == "read_url":
        if not url:
            return "外部网页读取失败：url 不能为空"
        return read_public_url(url)
    if mode == "search":
        if not query:
            return "外部搜索失败：query 不能为空"
        return search_public_web(query, limit)
    return f"外部研究失败：不支持的 mode={mode}"
