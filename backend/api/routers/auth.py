"""Backend-for-frontend authentication router.

Owns the OIDC handshake and the session cookie. Tokens never reach
JavaScript: every call from the SPA either sets or reads the
HttpOnly ``chiliai_session`` cookie. Exposes /auth/login,
/auth/callback, and /auth/me; logout/refresh land in subsequent tasks.
"""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

import api.middleware.auth as _auth_module
from api.dependencies import get_domain_config, get_session_store
from api.middleware.auth import SESSION_COOKIE_NAME, User, get_current_user
from api.middleware.session_store import SessionRecord, SessionStoreProtocol
from api.routers._oidc_client import (
    OidcClient,
    OidcConfigurationError,
    build_authorize_url,
    generate_pkce_pair,
)
from config.schema import DomainConfig
from shared.utils import generate_id

__all__ = ["router"]


PKCE_STATE_TTL_SECONDS = 300


router = APIRouter(prefix="/auth", tags=["auth"])


def _client_secret(auth_config: object) -> str:
    """Read the client secret from the env var named in ``auth_config``."""

    from config.schema import AuthConfig as _AuthConfig  # local to avoid circular

    cfg: _AuthConfig = auth_config  # type: ignore[assignment]
    if cfg.client_secret_env_var is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AuthConfig.client_secret_env_var is required when auth is enabled.",
        )
    secret = os.environ.get(cfg.client_secret_env_var)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Env var '{cfg.client_secret_env_var}' is not set.",
        )
    return secret


@router.get("/login")
def login(
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> RedirectResponse:
    """Begin the OIDC authorization-code flow."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    state = generate_id()
    verifier, challenge = generate_pkce_pair()

    try:
        url = build_authorize_url(
            auth_config, state=state, code_challenge=challenge
        )
    except OidcConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # Persist the verifier only after the URL was built successfully so a
    # misconfigured AuthConfig does not orphan PKCE state.
    session_store.save_pkce_state(
        state=state, verifier=verifier, ttl_seconds=PKCE_STATE_TTL_SECONDS
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback")
def callback(
    code: str,
    state: str,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> RedirectResponse:
    """Exchange the authorization code for tokens and mint a session."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    verifier = session_store.pop_pkce_state(state)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or expired state.",
        )

    secret = _client_secret(auth_config)
    oidc = OidcClient(auth_config=auth_config, client_secret=secret)
    try:
        tokens = oidc.exchange_code(code=code, code_verifier=verifier)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IdP token endpoint rejected the code: {exc.response.text}",
        ) from exc

    # Decode id_token (or access_token if id_token is absent) to extract user identity.
    # Call via the module reference so that monkeypatch substitution works in tests.
    token_to_decode = tokens.id_token or tokens.access_token
    claims = _auth_module.decode_token(
        token_to_decode,
        auth_config=auth_config,
        jwks_cache=_auth_module._JWKS_CACHE,  # noqa: SLF001
    )
    user_id = str(claims.get("sub") or "unknown")
    raw_email = claims.get("email")
    email = raw_email if isinstance(raw_email, str) else None
    raw_roles = claims.get(auth_config.roles_claim)
    if isinstance(raw_roles, list):
        roles = [str(item) for item in raw_roles]
    elif isinstance(raw_roles, str):
        roles = [raw_roles]
    else:
        roles = []

    sid = generate_id()
    now = time.time()
    record = SessionRecord(
        session_id=sid,
        user_id=user_id,
        roles=roles,
        email=email,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_token_expires_at=now + tokens.expires_in,
        id_token=tokens.id_token,
        created_at=now,
        ttl_seconds=auth_config.session_ttl_seconds,
    )
    session_store.save(record)

    response = RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        max_age=auth_config.session_ttl_seconds,
        secure=auth_config.cookie_secure,
        httponly=True,
        samesite="lax",
        domain=auth_config.cookie_domain,
        path="/",
    )
    return response


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user (or 401)."""
    return user
