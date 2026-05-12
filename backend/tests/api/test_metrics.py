"""Tests for the Prometheus ``/metrics`` endpoint and HTTP middleware (E10-S09)."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from api.dependencies import get_domain_config
from api.middleware.metrics import (
    MetricsMiddleware,
    build_metrics_router,
    http_requests_total,
    register_metrics,
)
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig


def _build_app() -> FastAPI:
    app = FastAPI()
    register_metrics(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
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

    def test_viewer_is_rejected_when_auth_enabled(self) -> None:
        app = _build_app()
        domain = load_config().model_copy(
            update={"auth": AuthConfig(enabled=True)}
        )
        app.dependency_overrides[get_domain_config] = lambda: domain
        app.dependency_overrides[get_current_user] = lambda: User(
            user_id="viewer-1",
            roles=["viewer"],
        )

        response = TestClient(app).get("/metrics")

        assert response.status_code == 403

    def test_service_role_can_read_metrics_when_auth_enabled(self) -> None:
        app = _build_app()
        domain = load_config().model_copy(
            update={"auth": AuthConfig(enabled=True)}
        )
        app.dependency_overrides[get_domain_config] = lambda: domain
        app.dependency_overrides[get_current_user] = lambda: User(
            user_id="service-1",
            roles=["service"],
        )

        response = TestClient(app).get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            CONTENT_TYPE_LATEST.split(";", 1)[0]
        )


class TestMetricsMiddlewareRecordsCounts:
    def test_request_increments_counter(self) -> None:
        client = TestClient(_build_app())
        before: float = cast(float, http_requests_total.labels(
            method="GET", path="/ping", status="200"
        )._value.get())  # pyright: ignore[reportPrivateUsage]
        client.get("/ping")
        client.get("/ping")
        after: float = cast(float, http_requests_total.labels(
            method="GET", path="/ping", status="200"
        )._value.get())  # pyright: ignore[reportPrivateUsage]
        assert after - before >= 2

    def test_router_factory_returns_router_with_metrics_route(self) -> None:
        router = build_metrics_router()
        paths = [getattr(route, "path", None) for route in router.routes]
        assert "/metrics" in paths

    def test_router_factory_marks_metrics_with_role_policy(self) -> None:
        router = build_metrics_router()
        route = next(route for route in router.routes if getattr(route, "path", None) == "/metrics")
        dependant = getattr(route, "dependant")
        required_roles = [
            getattr(dependency.call, "_chiliai_required_role", None)
            for dependency in dependant.dependencies
        ]
        assert "service" in required_roles

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
