"""Runtime factory for workflow run store adapters."""

from __future__ import annotations

import os

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.adapters.redis_store import RedisWorkflowRunStore
from agent.exceptions import AgentConfigurationError

__all__ = ["create_workflow_run_store_from_env"]


def create_workflow_run_store_from_env() -> WorkflowRunStoreProtocol:
    """Create the workflow run store selected by environment variables."""

    backend = os.environ.get("CHILI_WORKFLOW_RUN_STORE_BACKEND", "in_memory")
    backend = backend.strip().lower()
    if backend in {"in_memory", "memory"}:
        return InMemoryWorkflowRunStore()
    if backend == "redis":
        redis_url = os.environ.get("REDIS_URL")
        if redis_url is None or redis_url.strip() == "":
            raise AgentConfigurationError(
                "CHILI_WORKFLOW_RUN_STORE_BACKEND=redis requires REDIS_URL."
            )
        socket_timeout = _optional_float_env(
            "CHILI_WORKFLOW_REDIS_SOCKET_TIMEOUT_SECONDS"
        )
        socket_connect_timeout = _optional_float_env(
            "CHILI_WORKFLOW_REDIS_CONNECT_TIMEOUT_SECONDS"
        )
        return RedisWorkflowRunStore(
            redis_url=redis_url,
            socket_timeout=socket_timeout if socket_timeout is not None else 2.0,
            socket_connect_timeout=(
                socket_connect_timeout if socket_connect_timeout is not None else 2.0
            ),
        )
    raise AgentConfigurationError(
        "Unsupported workflow run store backend "
        f"'{backend}'. Available backends: in_memory, redis."
    )


def _optional_float_env(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise AgentConfigurationError(f"{name} must be a number.") from exc
