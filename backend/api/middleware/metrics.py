"""Prometheus HTTP metrics middleware and ``/metrics`` route (E10-S09)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import APIRouter, Depends, FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from api.middleware.rbac import require_role

__all__ = [
    "MetricsMiddleware",
    "build_metrics_router",
    "http_request_duration_seconds",
    "http_requests_total",
    "register_metrics",
]


http_requests_total: Counter = Counter(
    "http_requests_total",
    "Total HTTP requests received by the API gateway.",
    ["method", "path", "status"],
)

http_request_duration_seconds: Histogram = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration distribution in seconds.",
    ["method", "path"],
)


class MetricsMiddleware:
    """ASGI middleware that records request count and duration."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        method = str(scope.get("method", "GET"))
        path = _resolve_path(scope)
        start = perf_counter()
        status_code = 500

        async def _send_wrapper(message: dict[str, object]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                raw_status = message.get("status", 500)
                if isinstance(raw_status, int):
                    status_code = raw_status
            await send(message)

        try:
            await self._app(scope, receive, _send_wrapper)
        finally:
            elapsed = perf_counter() - start
            http_request_duration_seconds.labels(method=method, path=path).observe(elapsed)
            http_requests_total.labels(
                method=method, path=path, status=str(status_code)
            ).inc()


def _resolve_path(scope: dict[str, object]) -> str:
    route = scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            return path
    raw_path = scope.get("path", "/")
    return raw_path if isinstance(raw_path, str) else "/"


def build_metrics_router(
    registry: CollectorRegistry | None = None,
) -> APIRouter:
    """Return a router exposing ``GET /metrics`` in Prometheus text format."""

    target_registry = registry if registry is not None else REGISTRY
    router = APIRouter(tags=["observability"])

    @router.get("/metrics", dependencies=[Depends(require_role("service"))])
    async def metrics_endpoint() -> Response:  # pyright: ignore[reportUnusedFunction]
        payload = generate_latest(target_registry)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    return router


def register_metrics(app: FastAPI) -> None:
    """Attach the metrics middleware and ``/metrics`` route to ``app``."""

    app.add_middleware(MetricsMiddleware)
    app.include_router(build_metrics_router())
