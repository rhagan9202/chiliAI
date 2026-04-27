"""HTTP middleware components for the FastAPI gateway."""

from __future__ import annotations

__all__ = [
    "User",
    "get_current_user",
    "require_role",
]

from api.middleware.auth import User, get_current_user
from api.middleware.rbac import require_role
