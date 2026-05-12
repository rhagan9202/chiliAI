"""Graph adapter runtime authentication helpers."""

from __future__ import annotations

import os

from config.schema import GraphDbConfig

__all__ = ["resolve_graph_auth"]


def resolve_graph_auth(config: GraphDbConfig) -> tuple[str, str] | None:
    """Resolve optional Neo4j credentials from ``GraphDbConfig.auth_env_var``."""

    if config.auth_env_var is None:
        return None
    raw_value = os.environ.get(config.auth_env_var)
    if raw_value is None or raw_value.strip() == "":
        return None
    if ":" in raw_value:
        username, password = raw_value.split(":", 1)
        return username, password
    return "neo4j", raw_value
