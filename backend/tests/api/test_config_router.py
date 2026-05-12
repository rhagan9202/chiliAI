"""Tests for the config API router."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config
from config.loader import load_config
from config.schema import DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
MEDICARE_DEV_YAML = DEFAULTS_DIR / "medicare_fraud_dev.yaml"


def _skip_policy_audit(app: FastAPI) -> None:
    del app


@pytest.fixture()
def config() -> DomainConfig:
    return load_config(MEDICARE_YAML)


@pytest.fixture()
def client(config: DomainConfig) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: config
    return TestClient(app)


@pytest.fixture()
def custom_origin_client(
    config: DomainConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://review.example, https://ops.example")
    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: config
    with TestClient(app) as test_client:
        yield test_client


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

    def test_response_contains_ui_config(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        assert data["ui"]["default_entity_type"] == "provider"
        assert data["ui"]["navigation"]["pages"][0]["id"] == "dashboard"

    def test_get_features_returns_enabled_pages(self, client: TestClient) -> None:
        data = client.get("/config/features").json()
        assert data["capabilities"]["gnn"] is True
        assert "investigation" in data["enabled_pages"]
        assert data["default_entity_type"] == "provider"
        assert data["default_role"] == "analyst"

    def test_dev_config_returns_ui_features(self) -> None:
        app = create_app()
        config = load_config(MEDICARE_DEV_YAML)
        app.dependency_overrides[get_domain_config] = lambda: config

        with TestClient(app) as dev_client:
            data = dev_client.get("/config/features").json()

        assert data["default_entity_type"] == "provider"
        assert data["default_role"] == "analyst"
        assert "knowledge_bases" in data["enabled_pages"]
        assert "rag_chat" in data["enabled_pages"]
        assert set(data["roles"]) == {"analyst", "supervisor"}

    def test_get_domain_schema_returns_json_schema(self, client: TestClient) -> None:
        data = client.get("/config/domain/schema").json()
        assert data["title"] == "DomainConfig"
        assert "ui" in data["properties"]

    def test_health_still_works(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_default_cors_allows_local_vite_origin(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_custom_cors_origins_respect_environment(self, custom_origin_client: TestClient) -> None:
        allowed = custom_origin_client.get(
            "/health",
            headers={"Origin": "https://review.example"},
        )
        blocked = custom_origin_client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://review.example"
        assert blocked.status_code == 200
        assert "access-control-allow-origin" not in blocked.headers


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

    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)
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
