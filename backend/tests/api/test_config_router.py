"""Tests for the config API router."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config
from config.loader import load_config
from config.schema import DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


@pytest.fixture()
def config() -> DomainConfig:
    return load_config(MEDICARE_YAML)


@pytest.fixture()
def client(config: DomainConfig) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: config
    return TestClient(app)


class TestConfigRouter:
    def test_get_domain_returns_200(self, client: TestClient) -> None:
        resp = client.get("/config/domain")
        assert resp.status_code == 200

    def test_response_contains_domain_info(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        assert data["domain"]["name"] == "medicare_fraud"
        assert data["domain"]["display_name"] == "Medicare Fraud Detection"

    def test_response_contains_entities(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        names = {e["name"] for e in data["entities"]}
        assert "provider" in names
        assert "claim" in names

    def test_response_contains_relationships(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        names = {r["name"] for r in data["relationships"]}
        assert "submitted_by" in names

    def test_response_contains_capabilities(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        assert data["capabilities"]["timeseries"] is True
        assert data["capabilities"]["gnn"] is True

    def test_health_still_works(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_config_get_requires_viewer_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    base = load_config(MEDICARE_YAML)
    domain = base.model_copy(update={"auth": auth_cfg})

    monkeypatch.setattr("api.app.assert_complete", lambda app: None)
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-cfg",
            user_id="u",
            roles=["viewer"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401 (auth enabled rejects missing cookie)
        no_cookie = client.get("/config/domain")
        assert no_cookie.status_code == 401

        client.cookies.set("chiliai_session", "sid-cfg")
        with_cookie = client.get("/config/domain")
        assert with_cookie.status_code == 200
