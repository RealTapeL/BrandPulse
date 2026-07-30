"""
Agent Tool 统一注册表。

把底层能力函数包装为 Tool 标准接口，供 LLM Agent、调试脚本、前端 /agent/console 调用。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from brandpulse.agent.tool import FunctionTool
from brandpulse.collectors.queue import enqueue_crawl
from brandpulse.db_clients.postgres_client import PostgresClient

from . import tools as legacy_tools


class QueryBrandInput(BaseModel):
    brand_id: str = Field(..., description="品牌 ID，如 LK001")


class StartCrawlInput(BaseModel):
    brand_id: str = Field(..., description="品牌 ID")
    mall: str = Field(..., description="商场名，如 苏州中心")
    category: str = Field(..., description="品类，如 咖啡")
    cities: Optional[List[str]] = Field(default=["苏州"], description="城市列表，默认 [苏州]")


class RunSqlInput(BaseModel):
    sql: str = Field(..., description="只读 SQL（SELECT/WITH），最多返回 100 行")
    limit: int = Field(default=100, description="最大返回行数")


class RunIndicatorsInput(BaseModel):
    stat_date: Optional[str] = Field(default=None, description="统计日期 YYYY-MM-DD，不传则取最新")


class ListTablesInput(BaseModel):
    pass


class CrawlInput(BaseModel):
    mall: str = Field(..., description="商场名")
    category: str = Field(..., description="品类")
    cities: str = Field(default="苏州", description="城市，逗号分隔")


def _query_brand(args: Dict[str, Any]) -> Dict[str, Any]:
    """根据 brand_id 查询品牌基础信息。"""
    sql = "SELECT brand_id, brand_name_cn, category_id, tier, avg_price_min, avg_price_max FROM brands WHERE brand_id = :id"
    try:
        client = PostgresClient()
        with client.engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text(sql), {"id": args["brand_id"]}).mappings().first()
        if not row:
            return {"success": True, "result": None, "error": None, "meta": {}}
        return {"success": True, "result": dict(row), "error": None, "meta": {}}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e), "meta": {}}


def _start_crawl(args: Dict[str, Any]) -> Dict[str, Any]:
    """把抓取任务入队，返回 job_id。"""
    try:
        job_id = enqueue_crawl({
            "brand_id": args["brand_id"],
            "mall": args["mall"],
            "category": args["category"],
            "cities": args.get("cities", ["苏州"]),
        })
        return {"success": True, "result": {"job_id": job_id}, "error": None, "meta": {}}
    except Exception as e:
        return {"success": False, "result": None, "error": f"入队失败: {e}", "meta": {}}


def _run_sql(args: Dict[str, Any]) -> Dict[str, Any]:
    """只读 SQL 工具的标准接口封装。"""
    import time

    start = time.perf_counter()
    output = legacy_tools.query_db(args["sql"])
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    # query_db 内部对非法 SQL / 执行失败返回解释性文本
    success = not output.startswith(("SQL 被拒绝", "查询执行失败"))
    return {
        "success": success,
        "result": output if success else None,
        "error": None if success else output,
        "meta": {"latency_ms": latency_ms, "limit": args.get("limit", 100)},
    }


def _list_tables(_args: Dict[str, Any]) -> Dict[str, Any]:
    output = legacy_tools.list_tables()
    return {"success": True, "result": output, "error": None, "meta": {}}


def _run_indicators(args: Dict[str, Any]) -> Dict[str, Any]:
    output = legacy_tools.run_indicators(args.get("stat_date"))
    return {"success": "失败" not in output, "result": output, "error": output if "失败" in output else None, "meta": {}}


def _crawl(args: Dict[str, Any]) -> Dict[str, Any]:
    cities = args.get("cities", "苏州")
    output = legacy_tools.crawl(args["mall"], args["category"], cities)
    return {"success": "失败" not in output, "result": output, "error": output if "失败" in output else None, "meta": {}}


# 统一注册表
REGISTRY: Dict[str, FunctionTool] = {
    "query_brand": FunctionTool("query_brand", "查询品牌基础信息", _query_brand, QueryBrandInput),
    "start_crawl": FunctionTool("start_crawl", "把商场×品类采集任务入队", _start_crawl, StartCrawlInput),
    "run_sql": FunctionTool("run_sql", "对 PostgreSQL 执行只读 SQL", _run_sql, RunSqlInput),
    "list_tables": FunctionTool("list_tables", "列出数据库主要业务表结构", _list_tables, ListTablesInput),
    "run_indicators": FunctionTool("run_indicators", "刷新口碑/热度/SOV/趋势指标", _run_indicators, RunIndicatorsInput),
    "crawl": FunctionTool("crawl", "同步驱动浏览器采集（耗时约 40 秒）", _crawl, CrawlInput),
}


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """通过名字调用注册表中的工具（用于 Agent Console / 测试）。"""
    tool = REGISTRY.get(name)
    if not tool:
        return {"success": False, "error": f"未知工具: {name}", "result": None, "meta": {}}
    return tool.execute(args)


def list_tools() -> List[Dict[str, Any]]:
    """返回所有工具的元信息，用于给 LLM 注册 function calling。"""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in REGISTRY.values()
    ]
