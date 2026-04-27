"""Tests for the RBAC ``require_role`` factory (E10-S07)."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_domain_config
from api.middleware.auth import User, get_current_user
from api.middleware.rbac import (
    ROLE_HIERARCHY,
    is_role_sufficient,
    require_role,
)
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
)


def _build_config(*, enabled: bool = True) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="t", display_name="T", description="d"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=enabled),
        alerts=AlertsConfig(thresholds={}),
    )


def _build_app_with_user(user: User, *, enabled: bool = True) -> FastAPI:
    app = FastAPI()
    config = _build_config(enabled=enabled)
    app.dependency_overrides[get_domain_config] = lambda: config
    app.dependency_overrides[get_current_user] = lambda: user

    @app.get("/admin")
    def admin_only(_user: User = Depends(require_role("admin"))) -> dict[str, str]:
        return {"ok": "admin"}

    @app.get("/analyst")
    def analyst_or_above(
        _user: User = Depends(require_role("analyst")),
    ) -> dict[str, str]:
        return {"ok": "analyst"}

    @app.get("/viewer")
    def viewer_or_above(
        _user: User = Depends(require_role("viewer")),
    ) -> dict[str, str]:
        return {"ok": "viewer"}

    return app


class TestRoleHierarchy:
    def test_admin_implies_analyst_and_viewer(self) -> None:
        admin = ["admin"]
        assert is_role_sufficient(admin, "viewer")
        assert is_role_sufficient(admin, "analyst")
        assert is_role_sufficient(admin, "admin")

    def test_analyst_implies_viewer_only(self) -> None:
        analyst = ["analyst"]
        assert is_role_sufficient(analyst, "viewer")
        assert is_role_sufficient(analyst, "analyst")
        assert not is_role_sufficient(analyst, "admin")

    def test_viewer_only_grants_viewer(self) -> None:
        viewer = ["viewer"]
        assert is_role_sufficient(viewer, "viewer")
        assert not is_role_sufficient(viewer, "analyst")
        assert not is_role_sufficient(viewer, "admin")

    def test_unknown_role_never_sufficient(self) -> None:
        assert not is_role_sufficient(["robot"], "viewer")

    def test_unknown_required_role_returns_false(self) -> None:
        assert not is_role_sufficient(["admin"], "doesnotexist")

    def test_role_hierarchy_levels_are_strictly_increasing(self) -> None:
        levels = sorted(ROLE_HIERARCHY.values())
        assert levels == sorted(set(levels))


class TestRequireRoleFactory:
    def test_unknown_role_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="Unknown role"):
            require_role("supervillain")

    def test_admin_can_access_all_routes(self) -> None:
        app = _build_app_with_user(User(user_id="u", roles=["admin"]))
        client = TestClient(app)
        for path in ("/admin", "/analyst", "/viewer"):
            response = client.get(path)
            assert response.status_code == 200, path

    def test_analyst_cannot_access_admin_only(self) -> None:
        app = _build_app_with_user(User(user_id="u", roles=["analyst"]))
        client = TestClient(app)
        assert client.get("/admin").status_code == 403
        assert client.get("/analyst").status_code == 200
        assert client.get("/viewer").status_code == 200

    def test_viewer_cannot_access_write_routes(self) -> None:
        app = _build_app_with_user(User(user_id="u", roles=["viewer"]))
        client = TestClient(app)
        assert client.get("/admin").status_code == 403
        assert client.get("/analyst").status_code == 403
        assert client.get("/viewer").status_code == 200

    def test_no_roles_yields_403(self) -> None:
        app = _build_app_with_user(User(user_id="u", roles=[]))
        client = TestClient(app)
        assert client.get("/viewer").status_code == 403

    def test_disabled_auth_short_circuits_role_check(self) -> None:
        app = _build_app_with_user(
            User(user_id="anon", roles=[]), enabled=False
        )
        client = TestClient(app)
        # Auth disabled -> all routes allowed regardless of roles.
        for path in ("/admin", "/analyst", "/viewer"):
            response = client.get(path)
            assert response.status_code == 200, path
