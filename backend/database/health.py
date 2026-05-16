"""Database readiness probe."""

from __future__ import annotations

from database.protocols import ConnectionProvider


def check_database_health(provider: ConnectionProvider) -> bool:
    """Return ``True`` when the database answers a trivial query."""

    try:
        with provider.connection() as conn:
            row = conn.execute("SELECT 1").fetchone()
            return row is not None and row[0] == 1
    except Exception:
        return False


__all__ = [
    "check_database_health",
]
