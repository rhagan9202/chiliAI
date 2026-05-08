"""Backend-for-frontend authentication router.

Owns the OIDC handshake and the session cookie. Tokens never reach
JavaScript: every call from the SPA either sets or reads the
HttpOnly ``chiliai_session`` cookie. This first revision exposes only
GET /auth/me — the login/callback/logout/refresh endpoints land in
subsequent tasks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.middleware.auth import User, get_current_user

__all__ = ["router"]


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user (or 401)."""
    return user
