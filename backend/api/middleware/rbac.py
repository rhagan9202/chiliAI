"""Role-based access control middleware (E10-S07).

Defines a small role hierarchy (admin > analyst > viewer) and a
``require_role`` factory that returns a FastAPI dependency. RBAC composes
on top of :func:`get_current_user`. When auth is disabled the anonymous
user resolves to admin-equivalent access via the ``"_authdisabled"`` role.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, WebSocketException, status

from api.dependencies import get_domain_config
from api.middleware.auth import User, get_current_user, get_current_websocket_user
from config.schema import DomainConfig

__all__ = [
    "ROLE_HIERARCHY",
    "RoleNotPermittedError",
    "is_role_sufficient",
    "require_role",
    "require_ws_role",
]


ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "analyst": 2,
    "service": 2,
    "admin": 3,
}


class RoleNotPermittedError(Exception):
    """Raised when a user's roles do not satisfy the required role."""


def is_role_sufficient(user_roles: list[str], required: str) -> bool:
    """Return True when at least one user role meets ``required`` in the hierarchy."""

    required_level = ROLE_HIERARCHY.get(required)
    if required_level is None:
        return False
    for role in user_roles:
        level = ROLE_HIERARCHY.get(role)
        if level is not None and level >= required_level:
            return True
    return False


def require_role(role: str) -> Callable[..., User]:
    """Return a FastAPI dependency that enforces ``role`` against ``get_current_user``."""

    if role not in ROLE_HIERARCHY:
        raise ValueError(
            f"Unknown role '{role}'. Valid roles: {sorted(ROLE_HIERARCHY)}."
        )

    def _dependency(
        user: User = Depends(get_current_user),
        domain_config: DomainConfig = Depends(get_domain_config),
    ) -> User:
        auth_config = domain_config.auth
        if auth_config is None or not auth_config.enabled:
            return user
        if not is_role_sufficient(user.roles, role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"User '{user.user_id}' lacks required role '{role}'. "
                    f"Roles: {user.roles}."
                ),
            )
        return user

    _dependency._chiliai_required_role = role  # pyright: ignore[reportFunctionMemberAccess]
    return _dependency


def require_ws_role(role: str) -> Callable[..., User]:
    """Return a WebSocket dependency that enforces ``role``."""

    if role not in ROLE_HIERARCHY:
        raise ValueError(
            f"Unknown role '{role}'. Valid roles: {sorted(ROLE_HIERARCHY)}."
        )

    def _dependency(
        user: User = Depends(get_current_websocket_user),
        domain_config: DomainConfig = Depends(get_domain_config),
    ) -> User:
        auth_config = domain_config.auth
        if auth_config is None or not auth_config.enabled:
            return user
        if not is_role_sufficient(user.roles, role):
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=(
                    f"User '{user.user_id}' lacks required role '{role}'. "
                    f"Roles: {user.roles}."
                ),
            )
        return user

    _dependency._chiliai_required_role = role  # pyright: ignore[reportFunctionMemberAccess]
    return _dependency
