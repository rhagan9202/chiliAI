"""Tests for stage-level worker policy configuration."""

from __future__ import annotations

import pytest

from agent.exceptions import AgentConfigurationError
from agent.models import RetryPolicy
from agent.policy import load_stage_policy_registry_from_env


def test_stage_policy_loader_preserves_default_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_STAGE_POLICY_JSON", raising=False)

    registry = load_stage_policy_registry_from_env()
    policy = registry.get("documents.parsed")

    assert policy.retry_policy.max_retries == 3
    assert policy.retry_policy.base_delay_seconds == 1.0
    assert policy.timeout_seconds is None


def test_stage_policy_loader_preserves_supplied_default_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_STAGE_POLICY_JSON", raising=False)

    registry = load_stage_policy_registry_from_env(
        default_retry_policy=RetryPolicy(max_retries=7, base_delay_seconds=0.125)
    )
    policy = registry.get("documents.parsed")

    assert policy.retry_policy.max_retries == 7
    assert policy.retry_policy.base_delay_seconds == 0.125
    assert policy.timeout_seconds is None


def test_stage_policy_loader_parses_valid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHILI_STAGE_POLICY_JSON",
        """
        {
          "documents.parsed": {
            "max_retries": 1,
            "backoff_seconds": 0.25,
            "timeout_seconds": 2.5
          },
          "graph.updated": {
            "max_retries": 0,
            "base_delay_seconds": 0
          }
        }
        """,
    )

    registry = load_stage_policy_registry_from_env()

    parsed = registry.get("documents.parsed")
    assert parsed.retry_policy.max_retries == 1
    assert parsed.retry_policy.base_delay_seconds == 0.25
    assert parsed.timeout_seconds == 2.5

    graph = registry.get("graph.updated")
    assert graph.retry_policy.max_retries == 0
    assert graph.retry_policy.base_delay_seconds == 0.0
    assert graph.timeout_seconds is None


def test_stage_policy_loader_preserves_supplied_default_for_unspecified_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHILI_STAGE_POLICY_JSON",
        '{"documents.parsed": {"max_retries": 1, "timeout_seconds": 2.5}}',
    )

    registry = load_stage_policy_registry_from_env(
        default_retry_policy=RetryPolicy(max_retries=6, base_delay_seconds=0.2)
    )

    configured = registry.get("documents.parsed")
    assert configured.retry_policy.max_retries == 1
    assert configured.timeout_seconds == 2.5

    unspecified = registry.get("graph.updated")
    assert unspecified.retry_policy.max_retries == 6
    assert unspecified.retry_policy.base_delay_seconds == 0.2
    assert unspecified.timeout_seconds is None


def test_stage_policy_loader_rejects_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_STAGE_POLICY_JSON", "{not-json")

    with pytest.raises(AgentConfigurationError, match="CHILI_STAGE_POLICY_JSON"):
        load_stage_policy_registry_from_env()


def test_stage_policy_loader_rejects_unknown_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHILI_STAGE_POLICY_JSON",
        '{"documents.parsed": {"max_retries": 1, "jitter_seconds": 0.5}}',
    )

    with pytest.raises(AgentConfigurationError, match="jitter_seconds"):
        load_stage_policy_registry_from_env()


def test_stage_policy_loader_rejects_fatal_exception_types_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHILI_STAGE_POLICY_JSON",
        '{"documents.parsed": {"fatal_exception_types": ["RuntimeError"]}}',
    )

    with pytest.raises(AgentConfigurationError, match="fatal_exception_types"):
        load_stage_policy_registry_from_env()
