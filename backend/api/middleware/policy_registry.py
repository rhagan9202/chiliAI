"""Default-deny audit: every route must carry a require_role dependency."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute

__all__ = ["PolicyMissingError", "assert_complete"]


SKIP_PREFIXES = (
    "/auth/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class PolicyMissingError(RuntimeError):
    """Raised when one or more routes do not declare a required role."""


def _has_role_dependency(dependant: Dependant) -> bool:
    pending: list[Dependant] = list(dependant.dependencies)
    while pending:
        current = pending.pop()
        call = current.call
        if call is not None and getattr(call, "_chiliai_required_role", None) is not None:
            return True
        pending.extend(current.dependencies)
    return False


def _route_path(route: object) -> str:
    return getattr(route, "path", "")


def assert_complete(app: FastAPI) -> None:
    """Walk ``app.routes`` and raise if any non-skipped route is missing a role policy."""

    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        path = _route_path(route)
        if any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in SKIP_PREFIXES):
            continue
        if not _has_role_dependency(route.dependant):
            missing.append(path)

    if missing:
        raise PolicyMissingError(
            "Routes missing role policy (add Depends(require_role(...)) to each): "
            + ", ".join(sorted(set(missing)))
        )
