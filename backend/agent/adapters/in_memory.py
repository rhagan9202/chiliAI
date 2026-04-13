"""In-memory workflow run store for tests and local development."""

from __future__ import annotations

from agent.models import WorkflowRun

__all__ = ["InMemoryWorkflowRunStore"]


class InMemoryWorkflowRunStore:
    """A seeded workflow run store keyed by workflow id."""

    def __init__(self, runs: list[WorkflowRun] | None = None) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        for run in runs or []:
            self.save_run(run)

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.workflow_id] = run
        return run

    def get_run(self, workflow_id: str) -> WorkflowRun:
        run = self._runs.get(workflow_id)
        if run is None:
            raise ValueError(f"No workflow run registered for workflow_id='{workflow_id}'.")
        return run