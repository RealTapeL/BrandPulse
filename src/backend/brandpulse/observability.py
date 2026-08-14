"""Prometheus HTTP 指标。"""

from time import perf_counter

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "brandpulse_http_requests_total",
    "BrandPulse HTTP requests",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "brandpulse_http_request_duration_seconds",
    "BrandPulse HTTP request duration",
    ("method", "route"),
)


async def prometheus_http_middleware(request, call_next):
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, route_path, str(status)).inc()
        HTTP_DURATION.labels(request.method, route_path).observe(perf_counter() - started)
