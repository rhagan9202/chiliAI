"""Tests for the JWT/OIDC auth middleware (E10-S06)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import cast

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("jose")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jose import jwk, jwt  # noqa: E402

from api.dependencies import get_domain_config  # noqa: E402
from api.middleware.auth import (  # noqa: E402
    User,
    build_anonymous_user,
    get_current_user,
    set_jwks_fetcher,
)
from config.schema import (  # noqa: E402
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
)


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
    return jwt.encode(
        claims,
        pem,
        algorithm="RS256",
        headers={"kid": "kid-1"},
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
            jwks = {"keys": [_public_jwk_from_pem(rsa_pem)]}
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
