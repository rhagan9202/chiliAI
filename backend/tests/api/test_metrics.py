"""Tests for the Prometheus ``/metrics`` endpoint and HTTP middleware (E10-S09)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from api.middleware.metrics import (
    MetricsMiddleware,
    build_metrics_router,
    http_requests_total,
    register_metrics,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_metrics(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


class TestMetricsEndpoint:
    def test_returns_200_with_prometheus_content_type(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            CONTENT_TYPE_LATEST.split(";", 1)[0]
        )

    def test_payload_contains_expected_metric_names(self) -> None:
        client = TestClient(_build_app())
        # Drive at least one request through the middleware first.
        client.get("/ping")
        body = client.get("/metrics").text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body


class TestMetricsMiddlewareRecordsCounts:
    def test_request_increments_counter(self) -> None:
        client = TestClient(_build_app())
        before = http_requests_total.labels(
            method="GET", path="/ping", status="200"
        )._value.get()  # pyright: ignore[reportPrivateUsage]
        client.get("/ping")
        client.get("/ping")
        after = http_requests_total.labels(
            method="GET", path="/ping", status="200"
        )._value.get()  # pyright: ignore[reportPrivateUsage]
        assert after - before >= 2

    def test_router_factory_returns_router_with_metrics_route(self) -> None:
        router = build_metrics_router()
        paths = [getattr(route, "path", None) for route in router.routes]
        assert "/metrics" in paths

    def test_non_http_scope_passes_through(self) -> None:
        called: list[str] = []

        async def upstream(_scope: object, _receive: object, _send: object) -> None:
            called.append("ok")

        middleware = MetricsMiddleware(upstream)  # type: ignore[arg-type]

        async def _receive() -> dict[str, object]:
            return {}

        async def _send(_message: dict[str, object]) -> None:
            return None

        import asyncio

        asyncio.run(middleware({"type": "lifespan"}, _receive, _send))
        assert called == ["ok"]
