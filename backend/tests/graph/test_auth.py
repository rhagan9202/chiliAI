"""Tests for graph adapter auth resolution."""

from __future__ import annotations

import pytest

from config.schema import GraphDbConfig
from graph.auth import resolve_graph_auth


def _neo4j_config() -> GraphDbConfig:
    return GraphDbConfig(
        backend="neo4j",
        uri="bolt://neo4j:7687",
        auth_env_var="NEO4J_AUTH",
    )


def test_resolve_graph_auth_returns_none_when_env_missing_or_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing or blank credential values disable explicit auth."""

    config = _neo4j_config()

    monkeypatch.delenv("NEO4J_AUTH", raising=False)
    assert resolve_graph_auth(config) is None

    monkeypatch.setenv("NEO4J_AUTH", " ")
    assert resolve_graph_auth(config) is None


def test_resolve_graph_auth_accepts_user_password_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Colon-separated env values provide explicit username and password."""

    monkeypatch.setenv("NEO4J_AUTH", "alice:secret")

    assert resolve_graph_auth(_neo4j_config()) == ("alice", "secret")


def test_resolve_graph_auth_defaults_user_for_password_only_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Password-only env values default to Neo4j's standard username."""

    monkeypatch.setenv("NEO4J_AUTH", "secret")

    assert resolve_graph_auth(_neo4j_config()) == ("neo4j", "secret")
