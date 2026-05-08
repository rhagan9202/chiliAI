"""Tests for the OIDC client helpers used by the auth router."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from api.routers._oidc_client import (
    OidcClient,
    OidcConfigurationError,
    build_authorize_url,
    build_end_session_url,
    generate_pkce_pair,
)
from config.schema import AuthConfig


@pytest.fixture
def auth_config() -> AuthConfig:
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
        scopes=["openid", "email", "profile"],
    )


def test_generate_pkce_pair_produces_s256_challenge() -> None:
    import base64
    import hashlib

    verifier, challenge = generate_pkce_pair()

    # RFC 7636: verifier is 43-128 chars, url-safe base64 with no padding
    assert 43 <= len(verifier) <= 128
    assert "=" not in verifier
    assert "+" not in verifier
    assert "/" not in verifier

    # Challenge MUST equal BASE64URL(SHA256(ASCII(verifier))) per RFC 7636 §4.2
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected


def test_build_authorize_url_includes_required_query_params(auth_config: AuthConfig) -> None:
    url = build_authorize_url(
        auth_config,
        state="state-123",
        code_challenge="chal-xyz",
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "idp.example.com"
    assert parsed.path == "/authorize"
    assert qs["client_id"] == ["chili-spa"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["https://app.example.com/auth/callback"]
    assert qs["scope"] == ["openid email profile"]
    assert qs["state"] == ["state-123"]
    assert qs["code_challenge"] == ["chal-xyz"]
    assert qs["code_challenge_method"] == ["S256"]


def test_build_end_session_url_includes_id_token_hint(auth_config: AuthConfig) -> None:
    url = build_end_session_url(
        auth_config,
        id_token="id-tok-1",
        post_logout_redirect_uri="https://app.example.com/",
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["id_token_hint"] == ["id-tok-1"]
    assert qs["post_logout_redirect_uri"] == ["https://app.example.com/"]


def test_build_end_session_url_returns_none_when_endpoint_unset(
    auth_config: AuthConfig,
) -> None:
    cfg = auth_config.model_copy(update={"end_session_endpoint": None})
    url = build_end_session_url(
        cfg, id_token="id-tok-1", post_logout_redirect_uri="https://app.example.com/"
    )
    assert url is None


def test_oidc_client_exchange_code_posts_token_request(auth_config: AuthConfig) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content.decode()
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

    transport = httpx.MockTransport(handler)
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    tokens = client.exchange_code(code="code-1", code_verifier="ver-1")

    assert tokens.access_token == "acc-tok"
    assert tokens.refresh_token == "ref-tok"
    assert tokens.id_token == "id-tok"
    assert tokens.expires_in == 3600
    assert captured["url"] == "https://idp.example.com/oauth/token"
    assert captured["method"] == "POST"
    body_qs = parse_qs(str(captured["body"]))
    assert body_qs["grant_type"] == ["authorization_code"]
    assert body_qs["code"] == ["code-1"]
    assert body_qs["redirect_uri"] == ["https://app.example.com/auth/callback"]
    assert body_qs["code_verifier"] == ["ver-1"]
    assert body_qs["client_id"] == ["chili-spa"]


def test_oidc_client_refresh_token_grant(auth_config: AuthConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body_qs = parse_qs(request.content.decode())
        assert body_qs["grant_type"] == ["refresh_token"]
        assert body_qs["refresh_token"] == ["ref-old"]
        assert body_qs["client_id"] == ["chili-spa"]
        assert body_qs["client_secret"] == ["shh"]
        return httpx.Response(
            200,
            json={
                "access_token": "acc-new",
                "refresh_token": "ref-new",
                "expires_in": 1800,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    tokens = client.refresh(refresh_token="ref-old")

    assert tokens.access_token == "acc-new"
    assert tokens.refresh_token == "ref-new"
    assert tokens.expires_in == 1800


def test_oidc_client_exchange_code_raises_on_idp_error(auth_config: AuthConfig) -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    with pytest.raises(httpx.HTTPStatusError):
        client.exchange_code(code="bad", code_verifier="ver")


def test_build_end_session_url_omits_id_token_hint_when_none(
    auth_config: AuthConfig,
) -> None:
    url = build_end_session_url(
        auth_config,
        id_token=None,
        post_logout_redirect_uri="https://app.example.com/",
    )
    assert url is not None
    qs = parse_qs(urlparse(url).query)
    assert "id_token_hint" not in qs
    assert qs["post_logout_redirect_uri"] == ["https://app.example.com/"]


def test_build_authorize_url_raises_when_endpoint_missing(auth_config: AuthConfig) -> None:
    cfg = auth_config.model_copy(update={"authorize_endpoint": None})
    with pytest.raises(OidcConfigurationError, match="authorize_endpoint"):
        build_authorize_url(cfg, state="s", code_challenge="c")
