"""Authentication middleware for the chiliAI API.

Resolves the current user from one of three sources, in order: an
HttpOnly ``chiliai_session`` cookie backed by ``SessionStoreProtocol``,
an ``Authorization: Bearer <jwt>`` header validated against the
OIDC issuer's JWKS, or — when ``AuthConfig.enabled`` is ``False`` —
an anonymous viewer for dev and tests.

The JWKS document is fetched once per ``jwks_cache_seconds`` window via
the injected fetcher to keep the middleware test-friendly and free of
real network dependencies during tests.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from fastapi import (
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketException,
    status,
)
from pydantic import BaseModel, Field

from api.dependencies import get_domain_config, get_session_store
from api.middleware.exceptions import SessionNotFoundError
from api.middleware.session_store import SessionRecord, SessionStoreProtocol
from config.schema import AuthConfig, DomainConfig

__all__ = [
    "JwksCache",
    "JwksFetcher",
    "SESSION_COOKIE_NAME",
    "User",
    "build_anonymous_user",
    "decode_token",
    "get_jwks_cache",
    "get_current_user",
    "get_current_websocket_user",
    "set_jwks_fetcher",
]


class User(BaseModel):
    """Authenticated principal extracted from a validated JWT."""

    user_id: str
    roles: list[str] = Field(default_factory=list)
    email: str | None = None


JwksFetcher = Callable[[str], dict[str, object]]


def _default_jwks_fetcher(uri: str) -> dict[str, object]:
    """Fetch a JWKS document via httpx with a short timeout."""

    response = httpx.get(uri, timeout=5.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("JWKS endpoint returned a non-object payload")
    return cast(dict[str, object], payload)


@dataclass(slots=True)
class _CachedJwks:
    document: dict[str, object]
    fetched_at: float


@dataclass(slots=True)
class JwksCache:
    """TTL cache for JWKS documents keyed by URI."""

    fetcher: JwksFetcher = _default_jwks_fetcher
    ttl_seconds: int = 3600
    _entries: dict[str, _CachedJwks] = field(
        default_factory=lambda: cast(dict[str, _CachedJwks], {})
    )
    _clock: Callable[[], float] = field(default=time.monotonic)

    def get(self, uri: str) -> dict[str, object]:
        cached = self._entries.get(uri)
        now = self._clock()
        if cached is not None and (now - cached.fetched_at) < self.ttl_seconds:
            return cached.document
        document = self.fetcher(uri)
        self._entries[uri] = _CachedJwks(document=document, fetched_at=now)
        return document

    def invalidate(self) -> None:
        self._entries.clear()


_jwks_cache: JwksCache = JwksCache()

SESSION_COOKIE_NAME = "chiliai_session"
REFRESH_LEEWAY_SECONDS = 60


def _user_from_session(record: SessionRecord) -> User:
    return User(user_id=record.user_id, roles=record.roles, email=record.email)


def set_jwks_fetcher(fetcher: JwksFetcher, *, ttl_seconds: int | None = None) -> None:
    """Replace the global JWKS fetcher (used by tests)."""

    global _jwks_cache
    _jwks_cache = JwksCache(
        fetcher=fetcher,
        ttl_seconds=ttl_seconds if ttl_seconds is not None else 3600,
    )


def get_jwks_cache() -> JwksCache:
    """Return the process-wide JWKS cache."""

    return _jwks_cache


def build_anonymous_user() -> User:
    """Return the default user surfaced when authentication is disabled."""

    return User(user_id="anonymous", roles=["viewer"])


def decode_token(
    token: str,
    *,
    auth_config: AuthConfig,
    jwks_cache: JwksCache,
) -> dict[str, object]:
    """Validate ``token`` against ``auth_config`` and return the claims dict.

    Raises :class:`HTTPException` 401 for any validation failure.
    """

    try:
        from jose import jwt
        from jose.exceptions import (
            ExpiredSignatureError,
            JWKError,
            JWTClaimsError,
            JWTError,
        )
    except ImportError as exc:  # pragma: no cover - guarded by [auth] extra
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT library is unavailable; install the [auth] extra.",
        ) from exc

    if (
        auth_config.jwks_uri is None
        or auth_config.audience is None
        or auth_config.issuer_url is None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth is enabled but issuer/audience/jwks_uri is not configured.",
        )

    try:
        jwks = jwks_cache.get(auth_config.jwks_uri)
    except Exception as exc:  # noqa: BLE001 - JWKS fetch failures map to 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to retrieve JWKS for token validation.",
        ) from exc

    try:
        claims = cast(
            object,
            jwt.decode(
                token,
                cast(Mapping[str, Any], jwks),
                algorithms=["RS256"],
                audience=auth_config.audience,
                issuer=auth_config.issuer_url,
            ),
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        ) from exc
    except (JWTClaimsError, JWTError, JWKError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    if not isinstance(claims, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token claims payload is malformed.",
        )
    return cast(dict[str, object], claims)


def _coerce_roles(claim_value: object) -> list[str]:
    if isinstance(claim_value, list):
        roles_list = cast(list[object], claim_value)
        return [str(item) for item in roles_list if isinstance(item, (str, int))]
    if isinstance(claim_value, str):
        return [claim_value]
    return []


def _extract_user(
    claims: dict[str, object],
    *,
    roles_claim: str,
) -> User:
    raw_user_id = claims.get("sub") or claims.get("user_id") or "unknown"
    user_id = str(raw_user_id)
    roles = _coerce_roles(claims.get(roles_claim))
    raw_email = claims.get("email")
    email = str(raw_email) if isinstance(raw_email, str) else None
    return User(user_id=user_id, roles=roles, email=email)


def _resolve_auth_config(domain_config: DomainConfig) -> AuthConfig:
    auth = domain_config.auth
    return auth if auth is not None else AuthConfig()


def _extract_bearer_token_from_headers(headers: Mapping[str, str]) -> str | None:
    header = headers.get("Authorization")
    if header is None:
        return None
    parts = header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _extract_bearer_token(request: Request) -> str | None:
    return _extract_bearer_token_from_headers(request.headers)


def _maybe_refresh_session(
    record: SessionRecord,
    *,
    auth_config: AuthConfig,
    session_store: SessionStoreProtocol,
) -> SessionRecord:
    """If the access token is near expiry and a refresh token exists, refresh in-band.

    Returns the (possibly updated) SessionRecord. Raises HTTPException(401) when
    refresh fails so callers can surface session expiry to the SPA.
    """

    if record.refresh_token is None:
        return record
    if record.access_token_expires_at - time.time() > REFRESH_LEEWAY_SECONDS:
        return record

    secret_env = auth_config.client_secret_env_var
    if secret_env is None:
        return record
    secret = os.environ.get(secret_env)
    if secret is None:
        return record

    # Local import to avoid a circular dependency: api.routers imports from
    # api.middleware.auth (via the auth router), so a top-level import would
    # create a cycle.
    from api.routers._oidc_client import OidcClient  # noqa: PLC0415

    client = OidcClient(auth_config=auth_config, client_secret=secret)
    try:
        tokens = client.refresh(refresh_token=record.refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session refresh failed; please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    updated = record.model_copy(
        update={
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or record.refresh_token,
            "access_token_expires_at": time.time() + tokens.expires_in,
        }
    )
    session_store.save(updated)
    return updated


def _resolve_user_from_session_id(
    sid: str,
    *,
    auth_config: AuthConfig,
    session_store: SessionStoreProtocol,
    websocket: bool = False,
) -> User:
    try:
        record = session_store.get(sid)
    except SessionNotFoundError as exc:
        if websocket:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Session is unknown or has expired.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is unknown or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        record = _maybe_refresh_session(
            record, auth_config=auth_config, session_store=session_store
        )
    except HTTPException as exc:
        if websocket:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=str(exc.detail),
            ) from exc
        raise
    session_store.touch(sid, ttl_seconds=auth_config.session_ttl_seconds)
    return _user_from_session(record)


def get_current_user(
    request: Request,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> User:
    """Resolve the current ``User`` from the request.

    Resolution order:
      1. AuthConfig.enabled=False           -> anonymous viewer
      2. Cookie chiliai_session present     -> SessionStore.get(sid) -> User
      3. Authorization: Bearer present      -> existing JWT/JWKS path
      4. Otherwise                          -> 401
    """

    auth_config = _resolve_auth_config(domain_config)
    if not auth_config.enabled:
        return build_anonymous_user()

    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid is not None:
        return _resolve_user_from_session_id(
            sid,
            auth_config=auth_config,
            session_store=session_store,
        )

    token = _extract_bearer_token(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing authentication: send {SESSION_COOKIE_NAME} cookie or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(token, auth_config=auth_config, jwks_cache=_jwks_cache)
    return _extract_user(claims, roles_claim=auth_config.roles_claim)


def get_current_websocket_user(
    websocket: WebSocket,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> User:
    """Resolve the current ``User`` for WebSocket dependencies."""

    auth_config = _resolve_auth_config(domain_config)
    if not auth_config.enabled:
        return build_anonymous_user()

    sid = websocket.cookies.get(SESSION_COOKIE_NAME)
    if sid is not None:
        return _resolve_user_from_session_id(
            sid,
            auth_config=auth_config,
            session_store=session_store,
            websocket=True,
        )

    token = _extract_bearer_token_from_headers(websocket.headers)
    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=(
                f"Missing authentication: send {SESSION_COOKIE_NAME} cookie "
                "or Bearer token."
            ),
        )

    try:
        claims = decode_token(token, auth_config=auth_config, jwks_cache=_jwks_cache)
    except HTTPException as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc.detail),
        ) from exc
    return _extract_user(claims, roles_claim=auth_config.roles_claim)
