"""In-memory workflow run store for tests and local development."""

from __future__ import annotations

from agent.exceptions import WorkflowRunNotFoundError
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowRunUpdate

__all__ = ["InMemoryWorkflowRunStore"]


class InMemoryWorkflowRunStore:
    """A seeded workflow run store keyed by workflow id."""

    def __init__(self, runs: list[WorkflowRun] | None = None) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._idempotency_index: dict[tuple[str, str], str] = {}
        for run in runs or []:
            self.save_run(run)

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        previous = self._runs.get(run.workflow_id)
        if previous is not None and previous.idempotency_key is not None:
            self._idempotency_index.pop(
                (previous.knowledge_base_id, previous.idempotency_key), None
            )
        self._runs[run.workflow_id] = run
        if run.idempotency_key is not None:
            self._idempotency_index[(run.knowledge_base_id, run.idempotency_key)] = run.workflow_id
        return run

    def get_run(self, workflow_id: str) -> WorkflowRun:
        run = self._runs.get(workflow_id)
        if run is None:
            raise WorkflowRunNotFoundError(workflow_id)
        return run

    def list_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        runs = [
            run
            for run in self._runs.values()
            if (knowledge_base_id is None or run.knowledge_base_id == knowledge_base_id)
            and (status is None or run.status == status)
        ]
        runs.sort(key=lambda run: run.created_at, reverse=True)
        return runs[offset : offset + limit]

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun:
        existing = self.get_run(workflow_id)
        patch = update.model_dump(exclude_none=True)
        if not patch:
            return existing
        merged = existing.model_dump()
        merged.update(patch)
        updated = WorkflowRun.model_validate(merged)
        self._runs[workflow_id] = updated
        return updated

    def delete_run(self, workflow_id: str) -> None:
        removed = self._runs.pop(workflow_id, None)
        if removed is not None and removed.idempotency_key is not None:
            self._idempotency_index.pop(
                (removed.knowledge_base_id, removed.idempotency_key), None
            )

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> WorkflowRun | None:
        workflow_id = self._idempotency_index.get((knowledge_base_id, idempotency_key))
        if workflow_id is None:
            return None
        return self._runs.get(workflow_id)
