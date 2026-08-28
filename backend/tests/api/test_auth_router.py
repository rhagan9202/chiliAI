"""Tests for /auth router."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_audit_log_service, get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionNotFoundError, SessionRecord
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEvent, AuditEventQuery
from auditlog.service import AuditLogService
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


class _FailingAuditRepository(InMemoryAuditLogRepository):
    def append(self, event: AuditEvent) -> None:
        raise RuntimeError("audit sink unavailable")


def _install_audit_service(app: FastAPI, audit_service: AuditLogService) -> None:
    app.state.audit_log_service = audit_service
    app.dependency_overrides[get_audit_log_service] = lambda: audit_service


@pytest.fixture
def oidc_client() -> Iterator[tuple[TestClient, InMemorySessionStore]]:
    """Build a TestClient wired for the OIDC login/callback flow.

    A yield fixture (not a plain helper) specifically so the env vars can go
    through ``pytest.MonkeyPatch.context()`` rather than leaking into
    ``os.environ`` for the rest of the process: control stays paused at
    ``yield`` -- inside the ``with`` block -- for the whole test, including a
    real HTTP request the test makes after this fixture "returns", and only
    unwinds (reverting the env) at teardown. ``app_with_auth`` uses the
    ``monkeypatch`` fixture directly for the same two vars; this exists
    because these particular tests build their own app + overrides inline
    rather than taking `app_with_auth` and configuring it further.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OIDC_CLIENT_SECRET", "shh")
        # REDIS_URL is required by get_session_store's factory branch when
        # auth.enabled=True, but these tests override get_session_store
        # below, so its value never actually matters -- only its presence.
        mp.setenv("REDIS_URL", "redis://redis:6379/15")
        app = create_app()
        store = InMemorySessionStore()
        domain = _domain_with_auth()
        audit_service = AuditLogService(InMemoryAuditLogRepository())
        _install_audit_service(app, audit_service)
        app.dependency_overrides[get_session_store] = lambda: store
        app.dependency_overrides[get_domain_config] = lambda: domain
        client = TestClient(app, follow_redirects=False)
        yield client, store


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


def test_login_records_audit_event(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()
    domain = _domain_with_auth()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    _install_audit_service(app_with_auth, audit_service)
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 307
    page = audit_service.list_events(
        AuditEventQuery(action_prefix="auth.login")
    )
    assert [event.action for event in page.items] == ["auth.login.start"]
    event = page.items[0]
    assert event.actor_user_id == "anonymous"
    assert event.resource_type == "auth_flow"
    assert event.resource_id == "oidc"
    assert event.before is None
    assert event.after == {"pkce_state_created": True}
    assert event.metadata["source"] == "api.auth"


def test_auth_login_still_redirects_when_audit_sink_fails(
    app_with_auth: FastAPI,
) -> None:
    store = InMemorySessionStore()
    domain = _domain_with_auth()
    audit_service = AuditLogService(_FailingAuditRepository())
    _install_audit_service(app_with_auth, audit_service)
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 307
    assert audit_service.failed_write_count == 1


def test_login_includes_nonce_in_authorize_url(app_with_auth: FastAPI) -> None:
    from urllib.parse import parse_qs, urlparse

    store = InMemorySessionStore()
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 307
    location = response.headers["location"]
    qs = parse_qs(urlparse(location).query)
    assert "nonce" in qs
    nonce = qs["nonce"][0]
    assert nonce
    assert nonce != qs["state"][0]


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


def test_a_callback_without_the_login_cookie_is_rejected(
    oidc_client: tuple[TestClient, InMemorySessionStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login CSRF / session fixation.

    login() stores the PKCE state server-side and redirects with no cookie, and
    callback() looks the state up in the process-wide store with no reference
    to the requesting browser. An attacker who starts a login, captures their
    own `code`+`state`, and induces a victim's browser to hit the callback logs
    that victim into the ATTACKER's account -- the nonce binds the id_token to
    the authorization request, not to the user agent, so it validates fine.

    This drives the *entire* callback (mocked IdP token exchange + decode, as
    in test_callback_exchanges_code_and_creates_session_cookie) so a failure
    here means the attack fully succeeded end-to-end: a 307 with a minted
    session cookie for the attacker's own identity, handed to a browser that
    never touched /auth/login.
    """
    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    client, session_store = oidc_client
    session_store.save_pkce_state(state="s-1", verifier="v-1", ttl_seconds=300, nonce="n-1")

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token="id-tok")), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "attacker", "nonce": "n-1"}),
    )

    response = client.get(
        "/auth/callback?code=abc&state=s-1", follow_redirects=False
    )

    assert response.status_code == 400
    assert "login" in response.json()["detail"].lower()
    # No login ever happened in this browser, so there is no login-state
    # cookie to clear on the wire -- but the rejection must still not mint a
    # session, and must still actively expire the cookie name so any stale
    # chiliai_login_state a client happens to hold (e.g. reused from a prior,
    # different login attempt) doesn't linger.
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" not in set_cookie
    assert "chiliai_login_state=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)


def test_a_callback_whose_cookie_disagrees_with_the_state_is_rejected(
    oidc_client: tuple[TestClient, InMemorySessionStore],
) -> None:
    client, session_store = oidc_client
    session_store.save_pkce_state(state="s-1", verifier="v-1", ttl_seconds=300, nonce="n-1")
    client.cookies.set("chiliai_login_state", "s-other")

    response = client.get(
        "/auth/callback?code=abc&state=s-1", follow_redirects=False
    )

    assert response.status_code == 400
    # The mismatched cookie itself must be cleared on rejection, not just
    # not-honored -- an attacker-supplied login-state cookie must not
    # survive the failed attempt.
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" not in set_cookie
    assert "chiliai_login_state=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)


def test_the_login_redirect_sets_the_binding_cookie(
    oidc_client: tuple[TestClient, InMemorySessionStore],
) -> None:
    client, _ = oidc_client

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    cookie = response.headers["set-cookie"]
    assert "chiliai_login_state=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    # Starlette renders the attribute name capitalized but the value as
    # passed ("samesite=lax" -> "SameSite=lax"); cookie attribute values are
    # case-insensitive per RFC 6265bis, so compare case-insensitively --
    # matching how test_callback_exchanges_code_and_creates_session_cookie
    # checks the session cookie's SameSite in this same file.
    assert "samesite=lax" in cookie.lower()


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
    store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300, nonce="nonce-1")

    domain = _domain_with_auth()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    _install_audit_service(app_with_auth, audit_service)
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
        _stub_jwks_decoder(
            {"sub": "user-cb", "roles": ["analyst"], "email": "cb@example.com", "nonce": "nonce-1"}
        ),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-1")
        response = client.get("/auth/callback?code=auth-code&state=state-1")

    assert response.status_code == 307
    assert response.headers["location"] == "/"
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    # The login-state cookie set by /auth/login must be cleared on success
    # too -- its job (binding this one authorization request to this
    # browser) is done, and it should not linger past a successful login.
    assert "chiliai_login_state=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)

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
    page = audit_service.list_events(
        AuditEventQuery(action_prefix="auth.callback")
    )
    assert [event.action for event in page.items] == ["auth.callback.success"]
    event = page.items[0]
    assert event.actor_user_id == "user-cb"
    assert event.actor_email == "cb@example.com"
    assert event.actor_roles == ["analyst"]
    assert event.resource_type == "auth_session"
    assert event.resource_id == "user-cb"
    assert event.after == {"session_created": True, "role_count": 1}
    assert "auth-code" not in str(event.metadata)
    assert "state-1" not in str(event.metadata)


def test_callback_idp_response_missing_access_token_is_400(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed IdP token-endpoint response (fails OidcTokens validation) is a 400, not a 500."""
    import httpx

    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-malformed", verifier="ver", ttl_seconds=300, nonce="nonce-malformed"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    def fake_handler(request: httpx.Request) -> httpx.Response:
        # Missing required fields (access_token, expires_in) -> OidcTokens.model_validate
        # raises pydantic.ValidationError inside exchange_code.
        return httpx.Response(200, json={"token_type": "Bearer"})

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-malformed")
        response = client.get("/auth/callback?code=c&state=state-malformed")

    assert response.status_code == 400
    assert response.json()["detail"] == "IdP token endpoint returned an invalid response."
    # No session is minted on failure, but the login-state cookie set by
    # /auth/login must still be cleared -- it should not outlive the flow.
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" not in set_cookie
    assert "chiliai_login_state=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)


def test_callback_rejects_unknown_state(app_with_auth: FastAPI) -> None:
    store = InMemorySessionStore()  # no PKCE state stored
    domain = _domain_with_auth()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    _install_audit_service(app_with_auth, audit_service)
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        # Bound so the request clears the browser-binding gate and reaches
        # pop_pkce_state -- this test is exercising the unknown_state branch
        # specifically, not the login-CSRF guard.
        client.cookies.set("chiliai_login_state", "unknown")
        response = client.get("/auth/callback?code=c&state=unknown")

    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()
    page = audit_service.list_events(
        AuditEventQuery(action_prefix="auth.callback")
    )
    assert [event.action for event in page.items] == ["auth.callback.failure"]
    event = page.items[0]
    assert event.outcome == "failure"
    assert event.failure_reason == "unknown_state"
    assert event.actor_user_id == "anonymous"
    assert event.resource_type == "auth_flow"
    assert event.resource_id == "callback"
    assert "unknown" not in str(event.metadata)


def test_callback_propagates_idp_token_error(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-err", verifier="ver", ttl_seconds=300, nonce="nonce-err")
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
        client.cookies.set("chiliai_login_state", "state-err")
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
    store.save_pkce_state(
        state="state-bad-tok", verifier="ver", ttl_seconds=300, nonce="nonce-bad-tok"
    )
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
        client.cookies.set("chiliai_login_state", "state-bad-tok")
        response = client.get("/auth/callback?code=c&state=state-bad-tok")

    assert response.status_code == 400
    assert "IdP returned an invalid token" in response.json()["detail"]


def _fake_token_handler(*, id_token: str | None) -> Callable[[httpx.Request], httpx.Response]:
    import httpx

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "acc-tok",
                "refresh_token": "ref-tok",
                "id_token": id_token,
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    return fake_handler


def test_callback_rejects_nonce_mismatch(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-nonce-mismatch", verifier="ver", ttl_seconds=300, nonce="expected"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token="id-tok")), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb", "nonce": "wrong"}),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-nonce-mismatch")
        response = client.get("/auth/callback?code=c&state=state-nonce-mismatch")

    assert response.status_code == 400
    assert "nonce" in response.json()["detail"].lower()
    # No session is minted on failure, but the login-state cookie must still
    # be cleared.
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" not in set_cookie
    assert "chiliai_login_state=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)


def test_callback_rejects_missing_nonce_claim(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-nonce-missing", verifier="ver", ttl_seconds=300, nonce="expected"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token="id-tok")), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb"}),  # no "nonce" key
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-nonce-missing")
        response = client.get("/auth/callback?code=c&state=state-nonce-missing")

    assert response.status_code == 400
    assert "nonce" in response.json()["detail"].lower()


def test_callback_accepts_matching_nonce(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-nonce-match", verifier="ver", ttl_seconds=300, nonce="expected"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token="id-tok")), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb", "nonce": "expected"}),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-nonce-match")
        response = client.get("/auth/callback?code=c&state=state-nonce-match")

    assert response.status_code == 307
    assert "chiliai_session=" in response.headers.get("set-cookie", "")


def test_callback_access_token_fallback_skips_nonce(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the IdP omits id_token, we decode the access_token; nonce is an
    id_token-only claim per OIDC, so its absence must not block the fallback."""
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-nonce-fallback", verifier="ver", ttl_seconds=300, nonce="expected"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token=None)), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb"}),  # no nonce claim at all
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-nonce-fallback")
        response = client.get("/auth/callback?code=c&state=state-nonce-fallback")

    assert response.status_code == 307
    assert "chiliai_session=" in response.headers.get("set-cookie", "")


def test_callback_empty_string_id_token_uses_fallback_and_skips_nonce(
    app_with_auth: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the IdP returns empty-string id_token (falsy), the gate and decode
    both use truthiness, so they agree on the fallback (access_token). Nonce
    check is skipped, and the callback succeeds."""
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(
        state="state-empty-id-token", verifier="ver", ttl_seconds=300, nonce="expected"
    )
    domain = _domain_with_auth()
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(_fake_token_handler(id_token="")), timeout=5.0
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb"}),  # no nonce claim at all
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        client.cookies.set("chiliai_login_state", "state-empty-id-token")
        response = client.get("/auth/callback?code=c&state=state-empty-id-token")

    assert response.status_code == 307
    assert "chiliai_session=" in response.headers.get("set-cookie", "")


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
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    _install_audit_service(app_with_auth, audit_service)
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
    page = audit_service.list_events(
        AuditEventQuery(action_prefix="auth.logout")
    )
    assert [event.action for event in page.items] == ["auth.logout"]
    event = page.items[0]
    assert event.actor_user_id == "user-1"
    assert event.actor_email == "u@e.com"
    assert event.actor_roles == ["analyst"]
    assert event.resource_type == "auth_session"
    assert event.resource_id == "user-1"
    assert event.before == {"session_present": True}
    assert event.after == {"session_present": False}


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
