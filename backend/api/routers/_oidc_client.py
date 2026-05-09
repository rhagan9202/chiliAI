"""Provider-agnostic OIDC client used by the BFF auth router.

Encapsulates the OAuth 2.0 authorization-code-with-PKCE flow against any
OIDC provider configured via ``AuthConfig``. No vendor SDK; only httpx +
the existing python-jose dependency for JWT decoding (which lives in
``api.middleware.auth`` and is not duplicated here).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from config.schema import AuthConfig

__all__ = [
    "OidcClient",
    "OidcConfigurationError",
    "OidcTokens",
    "build_authorize_url",
    "build_end_session_url",
    "generate_pkce_pair",
]


class OidcConfigurationError(Exception):
    """Raised when AuthConfig is missing required OIDC fields."""


class OidcTokens(BaseModel):
    """Token bundle returned by the IdP."""

    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int
    token_type: str = "Bearer"


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` per RFC 7636 S256."""

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _require(value: str | None, *, field: str) -> str:
    if value is None:
        raise OidcConfigurationError(f"AuthConfig.{field} is required when auth is enabled.")
    return value


def build_authorize_url(
    auth_config: AuthConfig,
    *,
    state: str,
    code_challenge: str,
) -> str:
    endpoint = _require(auth_config.authorize_endpoint, field="authorize_endpoint")
    redirect_uri = _require(auth_config.redirect_uri, field="redirect_uri")
    client_id = _require(auth_config.client_id, field="client_id")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(auth_config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{endpoint}?{urlencode(params)}"


def build_end_session_url(
    auth_config: AuthConfig,
    *,
    id_token: str | None,
    post_logout_redirect_uri: str,
) -> str | None:
    if auth_config.end_session_endpoint is None:
        return None
    params: dict[str, str] = {
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    if id_token is not None:
        params["id_token_hint"] = id_token
    return f"{auth_config.end_session_endpoint}?{urlencode(params)}"


@dataclass(slots=True, frozen=True)
class OidcClient:
    """OIDC token-endpoint client."""

    auth_config: AuthConfig
    client_secret: str
    http_transport: httpx.BaseTransport | None = None

    def _http(self) -> httpx.Client:
        return httpx.Client(transport=self.http_transport, timeout=10.0)

    def _token_endpoint(self) -> str:
        return _require(self.auth_config.token_endpoint, field="token_endpoint")

    def _client_id(self) -> str:
        return _require(self.auth_config.client_id, field="client_id")

    def exchange_code(self, *, code: str, code_verifier: str) -> OidcTokens:
        redirect_uri = _require(self.auth_config.redirect_uri, field="redirect_uri")
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self._client_id(),
            "client_secret": self.client_secret,
        }
        with self._http() as client:
            response = client.post(self._token_endpoint(), data=body)
        response.raise_for_status()
        return OidcTokens.model_validate(response.json())

    def refresh(self, *, refresh_token: str) -> OidcTokens:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id(),
            "client_secret": self.client_secret,
        }
        with self._http() as client:
            response = client.post(self._token_endpoint(), data=body)
        response.raise_for_status()
        return OidcTokens.model_validate(response.json())
