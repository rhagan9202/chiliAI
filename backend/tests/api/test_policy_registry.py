"""Tests for policy_registry.assert_complete — default-deny audit at startup."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI

from api.middleware.policy_registry import (
    PolicyMissingError,
    assert_complete,
)
from api.middleware.rbac import require_role


def test_assert_complete_passes_when_every_route_has_role_dependency() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/widgets", dependencies=[Depends(require_role("viewer"))])
    def list_widgets() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    @router.post("/widgets", dependencies=[Depends(require_role("analyst"))])
    def create_widget() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    app.include_router(router)

    assert_complete(app)  # no raise


def test_assert_complete_raises_when_route_missing_role() -> None:
    app = FastAPI()

    @app.get("/unprotected")
    def unprotected() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    with pytest.raises(PolicyMissingError) as excinfo:
        assert_complete(app)

    assert "/unprotected" in str(excinfo.value)


def test_assert_complete_skips_auth_health_and_docs_routes() -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    @app.get("/auth/me")
    def me() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    # /docs and /openapi.json are FastAPI built-ins; they exist in app.routes.
    assert_complete(app)  # no raise


def test_assert_complete_requires_metrics_policy() -> None:
    app = FastAPI()

    @app.get("/metrics")
    def metrics() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    with pytest.raises(PolicyMissingError, match="/metrics"):
        assert_complete(app)


def test_assert_complete_finds_role_dependency_through_nested_dependencies() -> None:
    """If require_role is wrapped in another dependency, the marker still bubbles up."""
    app = FastAPI()

    role_dep = require_role("analyst")

    def composite(user=Depends(role_dep)):  # type: ignore[no-untyped-def]
        return user

    @app.get("/composite", dependencies=[Depends(composite)])
    def composite_route() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    assert_complete(app)


def test_assert_complete_lists_all_missing_routes() -> None:
    app = FastAPI()

    @app.get("/un1")
    def un1() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    @app.get("/un2")
    def un2() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    with pytest.raises(PolicyMissingError) as excinfo:
        assert_complete(app)

    msg = str(excinfo.value)
    assert "/un1" in msg
    assert "/un2" in msg
