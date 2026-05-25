"""Graph adapter runtime authentication helpers."""

from __future__ import annotations

import os

from config.schema import GraphDbConfig

__all__ = ["resolve_graph_auth"]


def resolve_graph_auth(config: GraphDbConfig) -> tuple[str, str] | None:
    """Resolve optional Neo4j credentials from environment variables.

    ``GraphDbConfig.auth_env_var`` remains the explicit override and accepts
    either ``username:password`` or Docker's ``username/password`` Neo4j auth
    format. When it is not configured, fall back to the standard
    ``NEO4J_USER``/``NEO4J_PASSWORD`` pair used by the Compose stacks. This
    keeps fresh deployments from starting Neo4j with auth enabled while the API
    and worker connect anonymously.
    """

    if config.auth_env_var is not None:
        return _parse_auth_value(os.environ.get(config.auth_env_var))
    return _auth_from_standard_env()


def _parse_auth_value(raw_value: str | None) -> tuple[str, str] | None:
    if raw_value is None or raw_value.strip() == "":
        return None
    normalized = raw_value.strip()
    if normalized.lower() == "none":
        return None
    if "/" in normalized:
        username, password = normalized.split("/", 1)
        return _validated_auth_parts(username, password)
    if ":" in raw_value:
        username, password = normalized.split(":", 1)
        return _validated_auth_parts(username, password)
    return _validated_auth_parts("neo4j", normalized)


def _auth_from_standard_env() -> tuple[str, str] | None:
    password = os.environ.get("NEO4J_PASSWORD")
    if password is None or password.strip() == "":
        return None
    username = os.environ.get("NEO4J_USER", "neo4j")
    return _validated_auth_parts(username, password)


def _validated_auth_parts(username: str, password: str) -> tuple[str, str] | None:
    clean_username = username.strip()
    clean_password = password.strip()
    if clean_username == "" or clean_password == "":
        return None
    return clean_username, clean_password
