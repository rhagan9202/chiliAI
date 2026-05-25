"""Tests for the workflow run store runtime factory."""

from __future__ import annotations

import pytest

from agent.adapters.runtime import create_workflow_run_store_from_env
from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.adapters.redis_store import RedisWorkflowRunStore
from agent.exceptions import AgentConfigurationError


def test_default_backend_returns_in_memory_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", raising=False)

    store = create_workflow_run_store_from_env()

    assert isinstance(store, InMemoryWorkflowRunStore)


@pytest.mark.parametrize("alias", ["in_memory", "memory", "IN_MEMORY", "MEMORY"])
def test_explicit_in_memory_aliases_return_in_memory_store(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", alias)

    store = create_workflow_run_store_from_env()

    assert isinstance(store, InMemoryWorkflowRunStore)


def test_redis_backend_with_redis_url_returns_redis_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    store = create_workflow_run_store_from_env()

    assert isinstance(store, RedisWorkflowRunStore)


def test_redis_backend_without_redis_url_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "redis")
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(AgentConfigurationError, match="REDIS_URL"):
        create_workflow_run_store_from_env()


def test_redis_backend_with_blank_redis_url_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "   ")

    with pytest.raises(AgentConfigurationError, match="REDIS_URL"):
        create_workflow_run_store_from_env()


def test_unknown_backend_raises_agent_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "dynamodb")

    with pytest.raises(AgentConfigurationError, match="dynamodb"):
        create_workflow_run_store_from_env()


def test_unknown_backend_message_lists_available_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "sqlite")

    with pytest.raises(AgentConfigurationError, match="in_memory"):
        create_workflow_run_store_from_env()
