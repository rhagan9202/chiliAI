"""Regression tests for Docker agent runtime backend selectors."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yaml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

REDIS_URL_ENTRY = "REDIS_URL=${REDIS_URL:-redis://redis:6379}"
EVENT_BUS_SELECTOR_ENTRY = (
    "CHILI_EVENT_BUS_BACKEND=${CHILI_EVENT_BUS_BACKEND:-redis}"
)
RUN_STORE_SELECTOR_ENTRY = (
    "CHILI_WORKFLOW_RUN_STORE_BACKEND=${CHILI_WORKFLOW_RUN_STORE_BACKEND:-redis}"
)


def test_api_and_worker_default_agent_runtime_to_redis() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    for service_name in ("api", "worker"):
        environment = compose["services"][service_name]["environment"]

        assert REDIS_URL_ENTRY in environment
        assert EVENT_BUS_SELECTOR_ENTRY in environment
        assert RUN_STORE_SELECTOR_ENTRY in environment


def test_env_example_documents_redis_agent_runtime_selectors() -> None:
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "REDIS_URL=redis://redis:6379" in env_example
    assert "CHILI_EVENT_BUS_BACKEND=redis" in env_example
    assert "CHILI_WORKFLOW_RUN_STORE_BACKEND=redis" in env_example
