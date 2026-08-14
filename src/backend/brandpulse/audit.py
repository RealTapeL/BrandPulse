"""请求级操作审计中间件。"""

import re
from time import perf_counter
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.storage.audit_repository import AuditRepository

logger = get_logger(__name__)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _request_id(request) -> str:
    supplied = (request.headers.get("x-request-id") or "").strip()
    if _SAFE_REQUEST_ID.fullmatch(supplied):
        return supplied
    return f"req_{uuid4().hex}"


def _should_audit(request) -> bool:
    if not request.url.path.startswith("/api/v1/"):
        return False
    if request.method in _MUTATING_METHODS:
        return True
    return request.method == "GET" and request.url.path.rstrip("/").endswith("/download")


async def operation_audit_middleware(request, call_next):
    request_id = _request_id(request)
    request.state.request_id = request_id
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if Config.AUDIT_ENABLED and _should_audit(request):
            auth = getattr(request.state, "auth", {}) or {}
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            event = {
                "event_id": f"audit_{uuid4().hex}",
                "request_id": request_id,
                "actor_id": str(auth.get("sub") or "anonymous")[:64],
                "actor_role": str(auth.get("role") or "")[:32],
                "action": f"{request.method} {route_path}"[:320],
                "method": request.method,
                "route": str(route_path)[:255],
                "request_path": request.url.path[:512],
                "status_code": status_code,
                "outcome": "success" if status_code < 400 else "failure",
                "client_ip": (request.client.host if request.client else "")[:64],
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "details": {
                    "query_keys": sorted(request.query_params.keys()),
                    "content_type": (request.headers.get("content-type") or "")[:128],
                    "content_length": (request.headers.get("content-length") or "")[:32],
                },
            }
            try:
                await run_in_threadpool(AuditRepository().record, event)
            except Exception:
                # 审计库故障必须可观测，但不能把已经完成的业务操作改造成 500。
                logger.exception("操作审计写入失败: request_id=%s", request_id)
