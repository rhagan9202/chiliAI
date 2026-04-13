"""Adapter-level protocols for workflow run persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.models import WorkflowRun


@runtime_checkable
class WorkflowRunStoreProtocol(Protocol):
    """Persist and retrieve workflow runs."""

    def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    def get_run(self, workflow_id: str) -> WorkflowRun: ...


__all__ = [
    "WorkflowRunStoreProtocol",
]