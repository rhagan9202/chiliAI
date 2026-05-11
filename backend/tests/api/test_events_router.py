"""Tests for the /events SSE router — verifies require_role enforcement."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


def test_events_stream_returns_snapshot_when_auth_disabled() -> None:
    """In dev (auth disabled), an unauthenticated GET to /events/stream succeeds."""
    from api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.content.decode()
        assert "workspace-update" in body


def test_events_stream_rejects_anonymous_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled, /events/stream 401s without a session cookie."""
    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore
    from config.loader import load_config
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

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
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()
    store = InMemorySessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401 BEFORE the SSE generator runs.
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 401


def test_events_stream_accepts_viewer_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled, a viewer session cookie passes the role guard."""
    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

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
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-viewer",
            user_id="u-viewer",
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
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 200
