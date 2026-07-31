"""
BrandPulse 自研数据看板后端（替代 Superset 看板）

聚合接口 GET /api/v1/dashboard 一次返回全部看板数据（数据量小，无需分页）。
保留 GET /api/dashboard 作为既有看板地址的兼容别名。
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
from brandpulse.api.agent import router as agent_router
from brandpulse.api.alerts import router as alerts_router
from brandpulse.api.auth import router as auth_router
from brandpulse.api.brands import router as brands_router
from brandpulse.api.chat import router as chat_router
from brandpulse.api.crawl_jobs import router as crawl_jobs_router
from brandpulse.api.dashboard import router as dashboard_router
from brandpulse.api.formulas import router as formulas_router
from brandpulse.api.indicators import router as indicators_router
from brandpulse.api.tables import router as tables_router
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

WEB_DIST = PROJECT_ROOT / "src" / "frontend" / "dist"

app = FastAPI(title="BrandPulse 招商品牌情报看板")
app.include_router(auth_router)
app.include_router(brands_router)
app.include_router(agent_router)
app.include_router(chat_router)
app.include_router(tables_router)
app.include_router(formulas_router)
app.include_router(alerts_router)
app.include_router(crawl_jobs_router)
app.include_router(indicators_router)
app.include_router(dashboard_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 静态托管 Vue 构建产物（不存在则只提供 API）；挂载在 / 之前必须先注册 API 路由
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
    logger.info(f"已挂载前端静态目录: {WEB_DIST}")
else:
    logger.warning(f"前端静态目录不存在（只提供 API）: {WEB_DIST}")
