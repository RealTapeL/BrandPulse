"""
BrandPulse 自研数据看板后端（替代 Superset 看板）

聚合接口 GET /api/dashboard 一次返回全部看板数据（数据量小，无需分页）。
同时静态托管 src/frontend/dist（Vue 构建产物，存在才挂载）。

启动：.venv/bin/python -m uvicorn brandpulse.api.app:app --host 0.0.0.0 --port 8000
"""
import sys
from pathlib import Path

# 工作目录是项目根，src/backend/ 不在 sys.path，参照 src/backend/main.py 的做法
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "backend"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from brandpulse.api.alerts import router as alerts_router
from brandpulse.api.crawl_jobs import router as crawl_jobs_router
from brandpulse.api.indicators import router as indicators_router
from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

WEB_DIST = PROJECT_ROOT / "src" / "frontend" / "dist"

app = FastAPI(title="BrandPulse 招商品牌情报看板")
app.include_router(alerts_router)
app.include_router(crawl_jobs_router)
app.include_router(indicators_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_jsonable(rows):
    """把 numeric/date 等类型转成 float/str，保证可 JSON 序列化"""
    out = []
    for r in rows:
        item = {}
        for k, v in r.items():
            if v is None or isinstance(v, (str, int, float, bool)):
                item[k] = v
            else:
                item[k] = float(v) if isinstance(v, (int, float)) or hasattr(v, "as_tuple") else str(v)
        out.append(item)
    return out


def _query(client: PostgresClient, sql: str, params: dict = None):
    with client.engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params or {}).mappings().all()]


@app.get("/api/dashboard")
def dashboard():
    client = PostgresClient()

    # 最新统计日的 shop 级指标（口碑分 / 热度 / SOV）
    stat_row = _query(client, """
        SELECT MAX(stat_date) AS d FROM brand_indicators_daily WHERE entity_type = 'shop'
    """)
    stat_date = stat_row[0]["d"] if stat_row else None
    indicators = []
    if stat_date:
        indicators = _query(client, """
            SELECT entity_name, weighted_score, heat_index, sov
            FROM brand_indicators_daily
            WHERE stat_date = :d AND entity_type = 'shop'
            ORDER BY weighted_score DESC
        """, {"d": stat_date})

    # 最新采集日的点评门店行
    crawl_row = _query(client, "SELECT MAX(crawl_date) AS d FROM dp_shop_metrics")
    crawl_date = crawl_row[0]["d"] if crawl_row else None
    dp_shops = []
    if crawl_date:
        dp_shops = _query(client, """
            SELECT shop_name, score, review_count, avg_price, business_area, place
            FROM dp_shop_metrics
            WHERE crawl_date = :d
            ORDER BY score DESC NULLS LAST, review_count DESC
        """, {"d": crawl_date})

    # 小红书笔记（按点赞降序）
    xhs_notes = _query(client, """
        SELECT title, author_name, likes, publish_time
        FROM xhs_notes
        ORDER BY likes DESC NULLS LAST
        LIMIT 100
    """)

    logger.info(f"[看板] stat_date={stat_date} crawl_date={crawl_date} "
                f"indicators={len(indicators)} dp_shops={len(dp_shops)} xhs_notes={len(xhs_notes)}")
    return {
        "stat_date": str(stat_date) if stat_date else None,
        "crawl_date": str(crawl_date) if crawl_date else None,
        "indicators": _to_jsonable(indicators),
        "dp_shops": _to_jsonable(dp_shops),
        "xhs_notes": _to_jsonable(xhs_notes),
    }


# 静态托管 Vue 构建产物（不存在则只提供 API）；挂载在 / 之前必须先注册 API 路由
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
    logger.info(f"已挂载前端静态目录: {WEB_DIST}")
else:
    logger.warning(f"前端静态目录不存在（只提供 API）: {WEB_DIST}")
