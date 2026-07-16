"""Tests for the JWT/OIDC auth middleware (E10-S06)."""

from __future__ import annotations

import pathlib
import time
from collections.abc import Callable, Iterator
from typing import cast

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

pytest.importorskip("jose")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jose import jwk, jwt  # noqa: E402

from api.dependencies import get_domain_config, get_session_store  # noqa: E402
from api.middleware.auth import (  # noqa: E402
    User,
    build_anonymous_user,
    get_current_user,
    set_jwks_fetcher,
)
from api.middleware.session_store import InMemorySessionStore, SessionRecord, SessionStoreProtocol  # noqa: E402
from config.loader import load_config  # noqa: E402
from config.schema import (  # noqa: E402
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
)

_DEFAULTS_DIR = pathlib.Path(__file__).parent.parent.parent / "config" / "defaults"
_MEDICARE_YAML = _DEFAULTS_DIR / "medicare_fraud.yaml"


@pytest.fixture(scope="module")
def rsa_pem() -> str:
    """Return a freshly generated RSA private key in PEM PKCS8 format."""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


@pytest.fixture(scope="module")
def rsa_pem_2() -> str:
    """Return a second, distinct RSA private key in PEM PKCS8 format.

    Used alongside ``rsa_pem`` to build the kid-rotation matrix (BL-022):
    two keypairs with distinct ``kid``s simulate an IdP JWKS rotation.
    """

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


def _build_minimal_config(*, auth: AuthConfig) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="d"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=auth,
        alerts=AlertsConfig(thresholds={}),
    )


def _build_app(config: DomainConfig) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_domain_config] = lambda: config

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": user.user_id, "roles": user.roles, "email": user.email}

    return app


@pytest.fixture(autouse=True)
def reset_jwks_cache() -> Iterator[None]:
    yield
    set_jwks_fetcher(lambda _uri: {"keys": []})


def _public_jwk_from_pem(pem: str, *, kid: str = "kid-1") -> dict[str, object]:
    key = jwk.construct(pem, algorithm="RS256")
    payload = cast(dict[str, object], key.public_key().to_dict())
    payload["kid"] = kid
    payload["alg"] = "RS256"
    payload["use"] = "sig"
    return payload


def _make_token(
    pem: str,
    *,
    issuer: str,
    audience: str,
    claims_extra: dict[str, object] | None = None,
    expires_in: int = 3600,
    kid: str | None = "kid-1",
) -> str:
    import time

    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "user-123",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    if claims_extra is not None:
        claims.update(claims_extra)
    headers = {"kid": kid} if kid is not None else None
    return jwt.encode(
        claims,
        pem,
        algorithm="RS256",
        headers=headers,
    )


def _kid_auth_config() -> AuthConfig:
    """AuthConfig shared by the kid-rotation matrix tests (BL-022)."""

    return AuthConfig(
        enabled=True,
        issuer_url="https://issuer.example",
        audience="chili",
        jwks_uri="https://issuer.example/.well-known/jwks.json",
        roles_claim="roles",
    )


class TestAuthDisabled:
    def test_returns_anonymous_when_disabled(self) -> None:
        config = _build_minimal_config(auth=AuthConfig(enabled=False))
        client = TestClient(_build_app(config))

        response = client.get("/whoami")
        assert response.status_code == 200
        body = response.json()
        anon = build_anonymous_user()
        assert body["user_id"] == anon.user_id
        assert body["roles"] == anon.roles


class TestAnonymousRoleOverride:
    def test_defaults_to_viewer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CHILI_DEV_ANONYMOUS_ROLE", raising=False)
        assert build_anonymous_user().roles == ["viewer"]

    def test_override_to_analyst_in_non_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_DEV_ANONYMOUS_ROLE", "analyst")
        monkeypatch.setenv("CHILI_ENV", "local")
        assert build_anonymous_user().roles == ["analyst"]

    def test_override_ignored_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_DEV_ANONYMOUS_ROLE", "analyst")
        monkeypatch.setenv("CHILI_ENV", "production")
        assert build_anonymous_user().roles == ["viewer"]

    def test_unknown_role_falls_back_to_viewer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_DEV_ANONYMOUS_ROLE", "superadmin")
        monkeypatch.setenv("CHILI_ENV", "local")
        assert build_anonymous_user().roles == ["viewer"]


class TestAuthEnabled:
    @pytest.fixture
    def auth_config(self) -> AuthConfig:
        return AuthConfig(
            enabled=True,
            issuer_url="https://issuer.example",
            audience="chili",
            jwks_uri="https://issuer.example/.well-known/jwks.json",
            roles_claim="roles",
        )

    @pytest.fixture
    def jwks_setter(self, rsa_pem: str) -> Callable[[], None]:
        def _setter() -> None:
            jwks: dict[str, object] = {"keys": [_public_jwk_from_pem(rsa_pem)]}
            set_jwks_fetcher(lambda _uri: jwks)

        return _setter

    def test_valid_token_returns_user_and_roles(
        self,
        rsa_pem: str,
        auth_config: AuthConfig,
        jwks_setter: Callable[[], None],
    ) -> None:
        jwks_setter()
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            claims_extra={"roles": ["analyst"], "email": "u@example.com"},
        )
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))

        response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "user-123"
        assert body["roles"] == ["analyst"]
        assert body["email"] == "u@example.com"

    def test_missing_authorization_header_returns_401(
        self, auth_config: AuthConfig, jwks_setter: Callable[[], None]
    ) -> None:
        jwks_setter()
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))
        response = client.get("/whoami")
        assert response.status_code == 401

    def test_malformed_authorization_header_returns_401(
        self, auth_config: AuthConfig, jwks_setter: Callable[[], None]
    ) -> None:
        jwks_setter()
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))
        response = client.get(
            "/whoami", headers={"Authorization": "Token abcdef"}
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(
        self,
        rsa_pem: str,
        auth_config: AuthConfig,
        jwks_setter: Callable[[], None],
    ) -> None:
        jwks_setter()
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            expires_in=-10,
        )
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))
        response = client.get(
            "/whoami", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_invalid_signature_returns_401(
        self,
        rsa_pem: str,
        auth_config: AuthConfig,
        jwks_setter: Callable[[], None],
    ) -> None:
        jwks_setter()
        token = _make_token(rsa_pem, issuer="https://issuer.example", audience="chili")
        head, body, _sig = token.split(".")
        bad_token = f"{head}.{body}.AAAAAAAAAA"
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))
        response = client.get(
            "/whoami", headers={"Authorization": f"Bearer {bad_token}"}
        )
        assert response.status_code == 401

    def test_wrong_audience_returns_401(
        self,
        rsa_pem: str,
        auth_config: AuthConfig,
        jwks_setter: Callable[[], None],
    ) -> None:
        jwks_setter()
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="other-audience",
        )
        client = TestClient(_build_app(_build_minimal_config(auth=auth_config)))
        response = client.get(
            "/whoami", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_missing_jwks_config_returns_401(self) -> None:
        partial_config = AuthConfig(
            enabled=True,
            issuer_url=None,
            audience=None,
            jwks_uri=None,
        )
        client = TestClient(_build_app(_build_minimal_config(auth=partial_config)))
        response = client.get("/whoami", headers={"Authorization": "Bearer xyz"})
        assert response.status_code == 401


def test_get_current_user_refreshes_when_access_token_near_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the access token is within 60s of expiry, the BFF triggers refresh."""
    import time

    import httpx
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.auth import get_current_user
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from api.routers import _oidc_client
    from config.schema import AuthConfig

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-refresh",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="old-acc",
            refresh_token="ref-tok",
            access_token_expires_at=time.time() + 30,  # within 60s leeway
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )

    refresh_calls: list[str] = []

    def fake_handler(request: httpx.Request) -> httpx.Response:
        refresh_calls.append(request.content.decode())
        return httpx.Response(
            200,
            json={
                "access_token": "new-acc",
                "refresh_token": "new-ref",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),  # type: ignore[reportUnknownLambdaType,reportUnknownArgumentType]
    )
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
    base = load_config(_MEDICARE_YAML)  # use the existing test-file constant
    domain = base.model_copy(update={"auth": auth_cfg})

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:  # type: ignore[reportUnusedFunction]
        return {"user_id": user.user_id}

    app.dependency_overrides[get_domain_config] = lambda: domain
    app.dependency_overrides[get_session_store] = lambda: store

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-refresh")
        response = client.get("/whoami")

    assert response.status_code == 200
    assert len(refresh_calls) == 1
    refreshed = store.get("sid-refresh")
    assert refreshed.access_token == "new-acc"
    assert refreshed.refresh_token == "new-ref"


def test_get_current_user_returns_401_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the IdP rejects the refresh token, the cookie path returns 401."""
    import time

    import httpx
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.auth import get_current_user
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from api.routers import _oidc_client
    from config.schema import AuthConfig

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-stale",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="old-acc",
            refresh_token="ref-bad",
            access_token_expires_at=time.time() + 30,
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(400, json={"error": "invalid_grant"})
            ),
            timeout=5.0,
        ),
    )
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
    base = load_config(_MEDICARE_YAML)
    domain = base.model_copy(update={"auth": auth_cfg})

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": user.user_id}

    app.dependency_overrides[get_domain_config] = lambda: domain
    app.dependency_overrides[get_session_store] = lambda: store

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-stale")
        response = client.get("/whoami")

    assert response.status_code == 401


def _build_app_with_session_store(
    config: DomainConfig, store: SessionStoreProtocol
) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_domain_config] = lambda: config
    app.dependency_overrides[get_session_store] = lambda: store

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": user.user_id, "roles": user.roles, "email": user.email}

    return app


def _build_auth_enabled_config() -> DomainConfig:
    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    base = load_config(_MEDICARE_YAML)
    return base.model_copy(update={"auth": auth_cfg})


class TestCookiePath:
    def test_get_current_user_resolves_session_from_cookie(self) -> None:
        """When auth is enabled and a valid session cookie is present, the user is returned."""
        domain = _build_auth_enabled_config()
        store = InMemorySessionStore()
        store.save(
            SessionRecord(
                session_id="sid-cookie",
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

        client = TestClient(_build_app_with_session_store(domain, store))
        client.cookies.set("chiliai_session", "sid-cookie")
        response = client.get("/whoami")

        assert response.status_code == 200
        assert response.json() == {
            "user_id": "user-1",
            "roles": ["analyst"],
            "email": "user@example.com",
        }

    def test_get_current_user_returns_401_when_cookie_session_is_unknown(self) -> None:
        """A cookie pointing at a missing session id results in 401."""
        domain = _build_auth_enabled_config()
        store = InMemorySessionStore()
        # Store is empty — "sid-missing" does not exist.

        client = TestClient(_build_app_with_session_store(domain, store))
        client.cookies.set("chiliai_session", "sid-missing")
        response = client.get("/whoami")

        assert response.status_code == 401

    def test_get_current_user_falls_back_to_bearer_when_no_cookie(
        self, rsa_pem: str
    ) -> None:
        """With auth enabled, no cookie, valid Bearer token -> existing JWT path is used."""
        auth_cfg = AuthConfig(
            enabled=True,
            issuer_url="https://issuer.example",
            audience="chili",
            jwks_uri="https://issuer.example/.well-known/jwks.json",
            roles_claim="roles",
        )
        domain = _build_minimal_config(auth=auth_cfg)
        store = InMemorySessionStore()

        jwks: dict[str, object] = {"keys": [_public_jwk_from_pem(rsa_pem)]}
        set_jwks_fetcher(lambda _uri: jwks)

        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            claims_extra={"roles": ["analyst"], "email": "u@example.com"},
        )

        client = TestClient(_build_app_with_session_store(domain, store))
        response = client.get(
            "/whoami", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "user-123"
        assert body["roles"] == ["analyst"]


def test_invalidate_uri_clears_single_entry() -> None:
    from api.middleware.auth import JwksCache

    calls: list[str] = []

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
    cache.get("https://idp/a")
    cache.get("https://idp/b")
    cache.invalidate_uri("https://idp/a")
    cache.get("https://idp/a")  # refetches
    cache.get("https://idp/b")  # still cached
    assert calls == ["https://idp/a", "https://idp/b", "https://idp/a"]


def test_force_refresh_is_throttled_per_uri() -> None:
    from api.middleware.auth import JwksCache

    calls: list[str] = []
    now = {"t": 1000.0}

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
    first = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    # Inside the 30s window: no refetch, cached doc returned.
    now["t"] += 10
    second = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    assert second == first
    # Past the window: refetches.
    now["t"] += 30
    third = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks", "https://idp/jwks"]
    assert third != first


def test_force_refresh_throttled_with_empty_cache_still_fetches() -> None:
    from api.middleware.auth import JwksCache

    calls: list[str] = []
    now = {"t": 1000.0}

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
    # First force_refresh fetches.
    doc1 = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    assert doc1 is not None
    # Invalidate the URI, clearing the cache entry.
    cache.invalidate_uri("https://idp/jwks")
    # Advance clock 10s (inside the 30s throttle window).
    now["t"] += 10
    # force_refresh again: throttle map still has the entry, so throttle applies,
    # falling through to get(), which refetches because cache is empty.
    doc2 = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks", "https://idp/jwks"]
    assert doc2 is not None


def test_invalidate_clears_forced_refresh_throttle() -> None:
    from api.middleware.auth import JwksCache

    calls: list[str] = []
    now = {"t": 1000.0}

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
    # First force_refresh fetches and records throttle timestamp at t=1000.
    cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    # Advance clock 10s (to t=1010).
    now["t"] += 10
    # Invalidate the entire cache (clears throttle map).
    cache.invalidate()
    # force_refresh again at t=1010: throttle map is empty, so it fetches immediately
    # and stamps the throttle map at t=1010.
    cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks", "https://idp/jwks"]
    # Advance clock 25s more (to t=1035, within the 30s window from the new stamp at t=1010).
    now["t"] += 25
    # force_refresh again at t=1035: throttle applies (stamp at t=1010 + 25s < 30s window),
    # so it returns get() without refetching.
    cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks", "https://idp/jwks"]  # no third fetch


class TestKidAwareResolution:
    """Rotation matrix for kid-aware resolution in decode_token (BL-022)."""

    def test_unknown_kid_forces_one_refetch_and_validates(
        self, rsa_pem: str, rsa_pem_2: str
    ) -> None:
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        jwks_old: dict[str, object] = {
            "keys": [_public_jwk_from_pem(rsa_pem, kid="kid-old")]
        }
        jwks_new: dict[str, object] = {
            "keys": [_public_jwk_from_pem(rsa_pem_2, kid="kid-new")]
        }
        rotated = {"done": False}
        calls: list[str] = []

        def fetcher(uri: str) -> dict[str, object]:
            calls.append(uri)
            return jwks_new if rotated["done"] else jwks_old

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)

        token_old = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-old",
        )
        # 1. token signed by OLD key, kid=old -> validates, fetch_count == 1
        claims_old = decode_token(token_old, auth_config=auth_config, jwks_cache=cache)
        assert claims_old["sub"] == "user-123"
        assert len(calls) == 1

        # 2. rotate: fetcher now returns JWKS_NEW only
        rotated["done"] = True

        token_new = _make_token(
            rsa_pem_2,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-new",
        )
        # 3. token signed by NEW key, kid=new -> decode_token succeeds,
        #    fetch_count == 2 (exactly one forced refetch)
        claims_new = decode_token(token_new, auth_config=auth_config, jwks_cache=cache)
        assert claims_new["sub"] == "user-123"
        assert len(calls) == 2

        # 4. token signed by OLD key -> 401, fetch_count == 2 (old kid known-missing,
        #    but: unknown kid inside the throttle window -> no refetch)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token_old, auth_config=auth_config, jwks_cache=cache)
        assert exc_info.value.status_code == 401
        assert len(calls) == 2

    def test_unknown_kid_still_missing_after_refetch_is_401(self, rsa_pem: str) -> None:
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        # fetcher always returns a JWKS without the token's kid
        jwks_without_kid: dict[str, object] = {
            "keys": [_public_jwk_from_pem(rsa_pem, kid="kid-other")]
        }
        calls: list[str] = []

        def fetcher(uri: str) -> dict[str, object]:
            calls.append(uri)
            return jwks_without_kid

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-missing",
        )

        # decode_token -> HTTPException 401 "Token signing key is unknown."
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token signing key is unknown."
        # fetch_count == 2 (initial get + one forced refresh)
        assert len(calls) == 2

    def test_unknown_kid_inside_throttle_window_does_not_refetch(
        self, rsa_pem: str
    ) -> None:
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        jwks_without_kid: dict[str, object] = {
            "keys": [_public_jwk_from_pem(rsa_pem, kid="kid-other")]
        }
        calls: list[str] = []
        now = {"t": 1000.0}

        def fetcher(uri: str) -> dict[str, object]:
            calls.append(uri)
            return jwks_without_kid

        # injected clock
        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-missing",
        )

        # first unknown kid consumes the forced refresh (fetch_count 2)
        with pytest.raises(HTTPException):
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert len(calls) == 2

        # second unknown-kid token within 30s -> 401 with fetch_count still 2
        now["t"] += 10
        with pytest.raises(HTTPException):
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert len(calls) == 2

        # advance clock past 30s -> third unknown-kid token -> fetch_count 3
        now["t"] += 30
        with pytest.raises(HTTPException):
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert len(calls) == 3

    def test_token_without_kid_header_keeps_legacy_path(self, rsa_pem: str) -> None:
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        jwks: dict[str, object] = {"keys": [_public_jwk_from_pem(rsa_pem, kid="kid-1")]}
        calls: list[str] = []

        def fetcher(uri: str) -> dict[str, object]:
            calls.append(uri)
            return jwks

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
        # token minted without a kid header, key present in JWKS
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid=None,
        )

        # validates, no forced refresh
        claims = decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert claims["sub"] == "user-123"
        assert len(calls) == 1

    def test_refetch_failure_maps_to_401(self, rsa_pem: str) -> None:
        """Token with unknown kid; fetcher succeeds initially but raises on force_refresh.

        This exercises lines 251-252: the exception handler in the force_refresh path
        that raises HTTPException 401 with "Unable to refresh JWKS for token validation."
        """
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        # Initial JWKS without the token's kid
        jwks_initial: dict[str, object] = {
            "keys": [_public_jwk_from_pem(rsa_pem, kid="kid-other")]
        }
        call_count = {"n": 0}

        def fetcher(uri: str) -> dict[str, object]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call (initial cache.get) succeeds
                return jwks_initial
            # Second call (force_refresh) raises
            raise RuntimeError("Simulated JWKS fetch failure on refresh")

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-missing",
        )

        # Token kid is not in initial JWKS, triggering force_refresh, which raises
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unable to refresh JWKS for token validation."

    def test_malformed_token_header_falls_through_to_canonical_401(
        self, rsa_pem: str
    ) -> None:
        """Garbage non-JWT string falls through to jwt.decode's canonical 401.

        This exercises the code path where a malformed token header is handled by
        jwt.decode (not by _token_kid), resulting in a canonical JWTError that maps
        to HTTPException 401, not a 500/unhandled exception.
        """
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        jwks: dict[str, object] = {"keys": [_public_jwk_from_pem(rsa_pem)]}

        def fetcher(uri: str) -> dict[str, object]:
            return jwks

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)

        # Not a JWT at all
        garbage_token = "not-a-jwt"

        # jwt.decode raises JWTError, which gets caught and converted to 401
        with pytest.raises(HTTPException) as exc_info:
            decode_token(garbage_token, auth_config=auth_config, jwks_cache=cache)
        assert exc_info.value.status_code == 401

    def test_jwks_without_keys_list_treated_as_kid_missing(
        self, rsa_pem: str
    ) -> None:
        """Fetcher returns malformed JWKS (no "keys" key); kid-miss path runs.

        This exercises lines 196-197: the defensive check in _jwks_has_kid where
        `keys` is not a list. The initial cache.get returns {"malformed": true},
        _jwks_has_kid returns False (non-list branch), forcing a refresh, which
        returns the same malformed doc, triggering the 401 "Token signing key is unknown."
        """
        from api.middleware.auth import JwksCache, decode_token

        auth_config = _kid_auth_config()
        # Malformed JWKS: missing "keys" field
        malformed_jwks: dict[str, object] = {"malformed": True}
        calls: list[str] = []

        def fetcher(uri: str) -> dict[str, object]:
            calls.append(uri)
            return malformed_jwks

        cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
        token = _make_token(
            rsa_pem,
            issuer="https://issuer.example",
            audience="chili",
            kid="kid-1",
        )

        # Token has a kid, but malformed JWKS has no "keys" key.
        # Initial check: _jwks_has_kid sees no list -> False (line 196 branch)
        # Forced refresh: same malformed doc -> _jwks_has_kid still False
        # Result: 401 "Token signing key is unknown."
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, auth_config=auth_config, jwks_cache=cache)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token signing key is unknown."
        # Verify we fetched twice: once for cache.get, once for force_refresh
        assert len(calls) == 2


def test_configure_jwks_cache_applies_config_ttl() -> None:
    """configure_jwks_cache wires AuthConfig.jwks_cache_seconds into the process cache (BL-022 tail)."""
    from api.middleware.auth import configure_jwks_cache, get_jwks_cache

    configure_jwks_cache(
        AuthConfig(
            enabled=True,
            issuer_url="https://issuer.example",
            audience="chili",
            jwks_uri="https://issuer.example/.well-known/jwks.json",
            jwks_cache_seconds=120,
        )
    )
    assert get_jwks_cache().ttl_seconds == 120

    # None (auth disabled / no config) resets to the 3600s default.
    configure_jwks_cache(None)
    assert get_jwks_cache().ttl_seconds == 3600


def test_forced_refresh_counter_outcomes(rsa_pem: str) -> None:
    """chili_jwks_forced_refresh_total tracks refreshed/throttled/failed outcomes."""
    from prometheus_client import REGISTRY

    from api.middleware.auth import JwksCache, decode_token

    def _sample(outcome: str) -> float:
        value = REGISTRY.get_sample_value(
            "chili_jwks_forced_refresh_total", {"outcome": outcome}
        )
        return value if value is not None else 0.0

    before_refreshed = _sample("refreshed")
    before_throttled = _sample("throttled")
    before_failed = _sample("failed")

    calls: list[str] = []
    now = {"t": 1000.0}

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
    cache.force_refresh("https://idp/jwks")  # refreshed: first call, no throttle yet
    cache.force_refresh("https://idp/jwks")  # throttled: within the 30s window

    assert _sample("refreshed") == before_refreshed + 1.0
    assert _sample("throttled") == before_throttled + 1.0

    # failed: decode_token's refetch-exception handler around force_refresh.
    auth_config = _kid_auth_config()
    jwks_initial: dict[str, object] = {
        "keys": [_public_jwk_from_pem(rsa_pem, kid="kid-other")]
    }
    call_count = {"n": 0}

    def failing_fetcher(uri: str) -> dict[str, object]:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return jwks_initial
        raise RuntimeError("Simulated JWKS fetch failure on refresh")

    fail_cache = JwksCache(fetcher=failing_fetcher, ttl_seconds=3600)
    token = _make_token(
        rsa_pem,
        issuer="https://issuer.example",
        audience="chili",
        kid="kid-missing",
    )

    with pytest.raises(HTTPException):
        decode_token(token, auth_config=auth_config, jwks_cache=fail_cache)

    assert _sample("failed") == before_failed + 1.0
