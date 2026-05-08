"""JWT/OIDC authentication middleware (E10-S06).

Provides a FastAPI dependency that validates ``Authorization: Bearer <jwt>``
headers against an OIDC provider's JWKS. When :class:`AuthConfig.enabled` is
``False`` the dependency returns an anonymous user with the ``viewer`` role
so existing endpoints continue to work in development and tests.

The JWKS document is fetched once per ``jwks_cache_seconds`` window via the
injected fetcher to keep the middleware test-friendly and free of real
network dependencies during tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpx
from fastapi import Depends, HTTPException, Request, status
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
    "get_current_user",
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
    _entries: dict[str, _CachedJwks] = field(default_factory=dict)
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


_JWKS_CACHE: JwksCache = JwksCache()

SESSION_COOKIE_NAME = "chiliai_session"


def _user_from_session(record: SessionRecord) -> User:
    return User(user_id=record.user_id, roles=record.roles, email=record.email)


def set_jwks_fetcher(
    fetcher: JwksFetcher, *, ttl_seconds: int | None = None
) -> None:
    """Replace the global JWKS fetcher (used by tests)."""

    global _JWKS_CACHE
    _JWKS_CACHE = JwksCache(
        fetcher=fetcher,
        ttl_seconds=ttl_seconds if ttl_seconds is not None else 3600,
    )


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

    if auth_config.jwks_uri is None or auth_config.audience is None or auth_config.issuer_url is None:
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
        claims = jwt.decode(
            token,
            cast(object, jwks),
            algorithms=["RS256"],
            audience=auth_config.audience,
            issuer=auth_config.issuer_url,
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


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if header is None:
        return None
    parts = header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


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
        try:
            record = session_store.get(sid)
        except SessionNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is unknown or has expired.",
            ) from exc
        return _user_from_session(record)

    token = _extract_bearer_token(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication: send chiliai_session cookie or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(token, auth_config=auth_config, jwks_cache=_JWKS_CACHE)
    return _extract_user(claims, roles_claim=auth_config.roles_claim)
