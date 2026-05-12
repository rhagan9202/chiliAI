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
        return RedisWorkflowRunStore(redis_url=redis_url)
    raise AgentConfigurationError(
        "Unsupported workflow run store backend "
        f"'{backend}'. Available backends: in_memory, redis."
    )
