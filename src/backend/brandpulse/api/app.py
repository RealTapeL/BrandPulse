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
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi import Depends, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from brandpulse.api.agent import router as agent_router
from brandpulse.api.audit import router as audit_router
from brandpulse.api.alerts import router as alerts_router
from brandpulse.api.auth import router as auth_router
from brandpulse.api.auth import require_auth
from brandpulse.api.users import router as users_router
from brandpulse.api.brands import router as brands_router
from brandpulse.api.chat import router as chat_router
from brandpulse.api.cases import router as cases_router
from brandpulse.api.crawl_jobs import router as crawl_jobs_router
from brandpulse.api.data_governance import router as data_governance_router
from brandpulse.api.dashboard import router as dashboard_router
from brandpulse.api.formulas import router as formulas_router
from brandpulse.api.indicators import router as indicators_router
from brandpulse.api.ml_forecasting import router as ml_forecasting_router
from brandpulse.api.monitoring import router as monitoring_router
from brandpulse.api.metrics import router as metrics_router
from brandpulse.api.operations import router as operations_router
from brandpulse.api.opportunities import router as opportunities_router
from brandpulse.api.reports import router as reports_router
from brandpulse.api.snapshots import router as snapshots_router
from brandpulse.api.tables import router as tables_router
from brandpulse.api.system import protected_router as protected_system_router
from brandpulse.api.system import router as system_router
from brandpulse.logger.logger import get_logger
from brandpulse.config.config import Config
from brandpulse.observability import prometheus_http_middleware
from brandpulse.audit import operation_audit_middleware

logger = get_logger(__name__)

Config.validate_auth_configuration()

WEB_DIST = PROJECT_ROOT / "src" / "frontend" / "dist"

# 告警检查由独立的 brandpulse.alerts.runner 进程负责。
# 不把调度器绑定到 FastAPI 生命周期，避免 API 多副本导致重复检查和重复通知。
app = FastAPI(title="BrandPulse 招商品牌情报看板")
app.include_router(auth_router)
app.include_router(system_router)
protected = {"dependencies": [Depends(require_auth)]}
app.include_router(brands_router, **protected)
app.include_router(agent_router, **protected)
app.include_router(chat_router, **protected)
app.include_router(tables_router, **protected)
app.include_router(formulas_router, **protected)
app.include_router(alerts_router, **protected)
app.include_router(crawl_jobs_router, **protected)
app.include_router(data_governance_router, **protected)
app.include_router(indicators_router, **protected)
app.include_router(ml_forecasting_router, **protected)
app.include_router(monitoring_router, **protected)
app.include_router(metrics_router, **protected)
app.include_router(reports_router, **protected)
app.include_router(snapshots_router, **protected)
app.include_router(dashboard_router, **protected)
app.include_router(operations_router, **protected)
app.include_router(opportunities_router, **protected)
app.include_router(cases_router, **protected)
app.include_router(audit_router, **protected)
app.include_router(users_router, **protected)
app.include_router(protected_system_router, **protected)
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(prometheus_http_middleware)
app.middleware("http")(operation_audit_middleware)


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 静态托管 Vue 构建产物（不存在则只提供 API）；挂载在 / 之前必须先注册 API 路由
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
    logger.info(f"已挂载前端静态目录: {WEB_DIST}")
else:
    logger.warning(f"前端静态目录不存在（只提供 API）: {WEB_DIST}")
