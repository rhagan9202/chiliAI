"""Config-driven construction of a database connection provider."""

from __future__ import annotations

import os

from config.schema import DatabaseConfig
from database.engine import PsycopgConnectionProvider, create_connection_pool
from database.exceptions import DatabaseConnectionError
from database.protocols import ConnectionProvider


def create_connection_provider(config: DatabaseConfig) -> ConnectionProvider | None:
    """Build a connection provider for the configured backend.

    Returns ``None`` when ``backend == "in_memory"`` — callers fall back to
    their in-memory adapters. Raises ``DatabaseConnectionError`` when the
    ``postgres`` backend is selected but no DSN is available.
    """

    if config.backend == "in_memory":
        return None

    dsn = os.environ.get(config.dsn_env_var)
    if not dsn:
        raise DatabaseConnectionError(
            f"Database backend is 'postgres' but environment variable "
            f"'{config.dsn_env_var}' is not set."
        )

    pool = create_connection_pool(dsn, config)
    return PsycopgConnectionProvider(pool)


__all__ = [
    "create_connection_provider",
]
