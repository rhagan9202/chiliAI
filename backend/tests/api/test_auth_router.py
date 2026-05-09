"""Tests for /auth router."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionNotFoundError, SessionRecord
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
    assert response.json()["detail"] == "Auth is disabled."


def _stub_jwks_decoder(claims: dict[str, object]):  # type: ignore[no-untyped-def]
    """Build a fake decode_token replacement that returns the given claims."""

    def _fake_decode(token, *, auth_config, jwks_cache):  # type: ignore[no-untyped-def]
        del token, auth_config, jwks_cache
        return claims

    return _fake_decode


def test_callback_exchanges_code_and_creates_session_cookie(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300)

    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "acc-tok",
                "refresh_token": "ref-tok",
                "id_token": "id-tok",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb", "roles": ["analyst"], "email": "cb@example.com"}),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=auth-code&state=state-1")

    assert response.status_code == 307
    assert response.headers["location"] == "/"
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    # Extract the session id from the cookie and verify the SessionRecord was saved.
    import re
    cookie_header = response.headers["set-cookie"]
    match = re.search(r"chiliai_session=([^;]+)", cookie_header)
    assert match is not None
    sid = match.group(1)

    saved = store.get(sid)
    assert saved.user_id == "user-cb"
    assert saved.roles == ["analyst"]
    assert saved.email == "cb@example.com"
    assert saved.access_token == "acc-tok"
    assert saved.refresh_token == "ref-tok"
    assert saved.id_token == "id-tok"


def test_callback_rejects_unknown_state(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()  # no PKCE state stored
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=c&state=unknown")

    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_callback_propagates_idp_token_error(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-err", verifier="ver", ttl_seconds=300)
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=bad&state=state-err")

    assert response.status_code == 400
    assert "IdP token endpoint rejected" in response.json()["detail"]


def test_callback_returns_400_when_id_token_validation_fails(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When decode_token raises 401 (bad signature/expired/etc.), callback returns 400."""
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-bad-tok", verifier="ver", ttl_seconds=300)
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "acc",
                "refresh_token": "ref",
                "id_token": "id",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )

    def _raise_401(token, *, auth_config, jwks_cache):  # type: ignore[no-untyped-def]
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad signature")

    monkeypatch.setattr(auth_module, "decode_token", _raise_401)

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=c&state=state-bad-tok")

    assert response.status_code == 400
    assert "IdP returned an invalid token" in response.json()["detail"]


def test_logout_clears_cookie_and_session(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-out",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id-tok-1",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_session", "sid-out")
        response = client.post("/auth/logout")

    # Cookie must be expired in the response
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)
    # Session must be gone
    with pytest.raises(SessionNotFoundError):
        store.get("sid-out")


def test_logout_redirects_to_idp_end_session_when_configured(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-rp",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id-tok-1",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = _domain_with_auth()  # has end_session_endpoint
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_session", "sid-rp")
        response = client.post(
            "/auth/logout?post_logout_redirect_uri=https%3A%2F%2Fapp.example.com%2F"
        )

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://idp.example.com/logout")
    assert "id_token_hint=id-tok-1" in location


def test_logout_no_session_cookie_is_idempotent(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.post("/auth/logout")

    # No cookie sent → either 204 (no end_session) or 307 (RP-initiated). Both acceptable.
    assert response.status_code in (204, 307)
