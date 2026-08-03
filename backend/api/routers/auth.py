"""Backend-for-frontend authentication router.

Owns the OIDC handshake and the session cookie. Tokens never reach
JavaScript: every call from the SPA either sets or reads the
HttpOnly ``chiliai_session`` cookie. Exposes /auth/login,
/auth/callback, /auth/logout, and /auth/me.
"""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

import api.middleware.auth as _auth_module
from api.dependencies import (
    get_audit_log_service,
    get_domain_config,
    get_session_store,
    record_auth_audit_event,
)
from api.middleware.auth import SESSION_COOKIE_NAME, User, coerce_roles, get_current_user
from api.middleware.session_store import SessionNotFoundError, SessionRecord, SessionStoreProtocol
from api.routers._oidc_client import (
    OidcClient,
    OidcConfigurationError,
    build_authorize_url,
    build_end_session_url,
    generate_pkce_pair,
)
from auditlog.service import AuditLogService
from config.schema import AuthConfig, DomainConfig
from shared.utils import generate_id

__all__ = ["router"]


PKCE_STATE_TTL_SECONDS = 300


router = APIRouter(prefix="/auth", tags=["auth"])


def _request_client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _client_secret(auth_config: AuthConfig) -> str:
    """Read the client secret from the env var named in ``auth_config``."""

    if auth_config.client_secret_env_var is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AuthConfig.client_secret_env_var is required when auth is enabled.",
        )
    secret = os.environ.get(auth_config.client_secret_env_var)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Env var '{auth_config.client_secret_env_var}' is not set.",
        )
    return secret


@router.get("/login")
def login(
    request: Request,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
) -> RedirectResponse:
    """Begin the OIDC authorization-code flow."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        record_auth_audit_event(
            audit_service,
            action="auth.login.failure",
            resource_type="auth_flow",
            resource_id="oidc",
            before=None,
            after={"pkce_state_created": False},
            outcome="failure",
            failure_reason="auth_disabled",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    state = generate_id()
    nonce = generate_id()
    verifier, challenge = generate_pkce_pair()

    try:
        url = build_authorize_url(
            auth_config, state=state, code_challenge=challenge, nonce=nonce
        )
    except OidcConfigurationError as exc:
        record_auth_audit_event(
            audit_service,
            action="auth.login.failure",
            resource_type="auth_flow",
            resource_id="oidc",
            before=None,
            after={"pkce_state_created": False},
            outcome="failure",
            failure_reason="oidc_config_invalid",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # Persist the verifier only after the URL was built successfully so a
    # misconfigured AuthConfig does not orphan PKCE state.
    session_store.save_pkce_state(
        state=state, verifier=verifier, ttl_seconds=PKCE_STATE_TTL_SECONDS, nonce=nonce
    )
    record_auth_audit_event(
        audit_service,
        action="auth.login.start",
        resource_type="auth_flow",
        resource_id="oidc",
        before=None,
        after={"pkce_state_created": True},
        client_ip=_request_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback")
def callback(
    request: Request,
    code: str,
    state: str,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
) -> RedirectResponse:
    """Exchange the authorization code for tokens and mint a session."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="auth_disabled",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    pkce = session_store.pop_pkce_state(state)
    if pkce is None:
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="unknown_state",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or expired state.",
        )
    verifier = pkce.verifier

    try:
        secret = _client_secret(auth_config)
    except HTTPException:
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="client_secret_missing",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise
    oidc = OidcClient(auth_config=auth_config, client_secret=secret)
    try:
        tokens = oidc.exchange_code(code=code, code_verifier=verifier)
    except httpx.HTTPStatusError as exc:
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="idp_token_rejected",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IdP token endpoint rejected the code: {exc.response.text}",
        ) from exc
    except ValidationError as exc:
        # The IdP responded 2xx but the body doesn't match OidcTokens (missing
        # access_token/expires_in, wrong types, etc.) — a client-observable
        # upstream fault, not a chiliAI bug, so 400 rather than 500.
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="invalid_idp_response",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IdP token endpoint returned an invalid response.",
        ) from exc

    # Decode id_token (or access_token if id_token is absent) to extract user identity.
    # Call via the module reference so that monkeypatch substitution works in tests.
    token_to_decode = tokens.id_token or tokens.access_token
    try:
        claims = _auth_module.decode_token(
            token_to_decode,
            auth_config=auth_config,
            jwks_cache=_auth_module.get_jwks_cache(),
        )
    except HTTPException as exc:
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="invalid_token",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IdP returned an invalid token: {exc.detail}",
        ) from exc

    # Nonce binds the id_token to this login attempt (BL-022). It is an
    # id_token claim by OIDC spec, so the access-token fallback path skips it —
    # see docs/auth/idp-templates.md.
    if tokens.id_token:
        if claims.get("nonce") != pkce.nonce:
            record_auth_audit_event(
                audit_service,
                action="auth.callback.failure",
                resource_type="auth_flow",
                resource_id="callback",
                before=None,
                after={"session_created": False},
                outcome="failure",
                failure_reason="nonce_mismatch",
                client_ip=_request_client_ip(request),
                user_agent=_request_user_agent(request),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="id_token nonce mismatch.",
            )

    user_id = str(claims.get("sub") or "unknown")
    raw_email = claims.get("email")
    email = raw_email if isinstance(raw_email, str) else None
    raw_roles = claims.get(auth_config.roles_claim)
    roles = coerce_roles(raw_roles)

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
    record_auth_audit_event(
        audit_service,
        action="auth.callback.success",
        actor_user_id=user_id,
        actor_email=email,
        actor_roles=roles,
        resource_type="auth_session",
        resource_id=user_id,
        before=None,
        after={"session_created": True, "role_count": len(roles)},
        metadata={"id_token_present": bool(tokens.id_token)},
        client_ip=_request_client_ip(request),
        user_agent=_request_user_agent(request),
    )

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


@router.post("/logout")
def logout(
    request: Request,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    post_logout_redirect_uri: str | None = None,
) -> Response:
    """Delete the server-side session, clear the cookie, and (optionally) bounce to IdP."""

    auth_config = domain_config.auth
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    id_token: str | None = None
    actor_user_id = "anonymous"
    actor_email: str | None = None
    actor_roles: list[str] = []
    session_found = False
    if sid is not None:
        try:
            record = session_store.get(sid)
            id_token = record.id_token
            actor_user_id = record.user_id
            actor_email = record.email
            actor_roles = list(record.roles)
            session_found = True
            session_store.delete(sid)
        except SessionNotFoundError:
            # Session already gone — proceed to clear the cookie regardless.
            pass

    rp_url: str | None = None
    if auth_config is not None and auth_config.enabled:
        target = post_logout_redirect_uri or "/"
        rp_url = build_end_session_url(
            auth_config,
            id_token=id_token,
            post_logout_redirect_uri=target,
        )

    if rp_url is not None:
        response: Response = RedirectResponse(
            url=rp_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    else:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        domain=auth_config.cookie_domain if auth_config is not None else None,
    )
    record_auth_audit_event(
        audit_service,
        action="auth.logout",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_roles=actor_roles,
        resource_type="auth_session",
        resource_id=actor_user_id,
        before={"session_present": session_found},
        after={"session_present": False},
        metadata={
            "cookie_present": sid is not None,
            "idp_redirect": rp_url is not None,
        },
        client_ip=_request_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    return response


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user (or 401)."""
    return user
