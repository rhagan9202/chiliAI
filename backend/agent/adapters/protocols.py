"""Adapter-level protocols for workflow run persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.models import WorkflowRun


@runtime_checkable
class WorkflowRunStoreProtocol(Protocol):
    """Persist and retrieve workflow runs."""

    # TODO(production): Extend with list, delete, and query methods:
    # - list_runs(kb_id, limit, offset) -> list[WorkflowRun]
    # - delete_run(workflow_id) -> None
    # - update_run(workflow_id, updates) -> WorkflowRun
    # Implement production adapters: PostgresWorkflowRunStore, RedisWorkflowRunStore.

    def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    def get_run(self, workflow_id: str) -> WorkflowRun: ...


__all__ = [
    "WorkflowRunStoreProtocol",
]