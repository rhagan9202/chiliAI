"""Tests for /auth router."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionRecord
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


def _auth_config() -> AuthConfig:
    return AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        end_session_endpoint="https://idp.example.com/logout",
        redirect_uri="https://app.example.com/auth/callback",
    )


def _domain_with_auth() -> DomainConfig:
    base = load_config(MEDICARE_YAML)
    return base.model_copy(update={"auth": _auth_config()})


@pytest.fixture
def app_with_auth(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    # REDIS_URL is required by get_session_store's factory branch when auth.enabled=True,
    # but auth-enabled tests immediately override get_session_store via dependency_overrides.
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/15")
    return create_app()


def test_me_returns_401_when_unauthenticated(app_with_auth) -> None:
    store = InMemorySessionStore()
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_user_when_session_cookie_is_valid(app_with_auth) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-me",
            user_id="user-1",
            roles=["analyst"],
            email="user@example.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        client.cookies.set("chiliai_session", "sid-me")
        response = client.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-1"
    assert body["roles"] == ["analyst"]
    assert body["email"] == "user@example.com"


def test_me_returns_anonymous_when_auth_disabled(app_with_auth) -> None:
    base = load_config(MEDICARE_YAML)
    domain = base.model_copy(update={"auth": AuthConfig()})  # enabled=False
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user_id"] == "anonymous"


def test_login_redirects_to_authorize_endpoint_with_pkce_and_state(app_with_auth: FastAPI) -> None:
    from urllib.parse import parse_qs, urlparse

    store = InMemorySessionStore()
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert parsed.netloc == "idp.example.com"
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    state = qs["state"][0]
    # PKCE state must be persisted so the callback can recover the verifier
    assert store.pop_pkce_state(state) is not None


def test_login_returns_500_when_oidc_config_incomplete(app_with_auth: FastAPI) -> None:
    base = load_config(MEDICARE_YAML)
    incomplete = base.model_copy(
        update={
            "auth": AuthConfig(
                enabled=True,
                issuer_url="https://idp.example.com",
                audience="chili-api",
                jwks_uri="https://idp.example.com/jwks",
                # NB: no authorize_endpoint, redirect_uri, or client_id
            )
        }
    )
    app_with_auth.dependency_overrides[get_domain_config] = lambda: incomplete
    app_with_auth.dependency_overrides[get_session_store] = lambda: InMemorySessionStore()

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 500
    detail = response.json()["detail"]
    # Whichever endpoint/field is checked first by _require should appear in the message
    assert "authorize_endpoint" in detail or "redirect_uri" in detail or "client_id" in detail


def test_login_returns_404_when_auth_disabled(app_with_auth: FastAPI) -> None:
    base = load_config(MEDICARE_YAML)
    domain = base.model_copy(update={"auth": AuthConfig()})  # enabled=False
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain
    app_with_auth.dependency_overrides[get_session_store] = lambda: InMemorySessionStore()

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 404
