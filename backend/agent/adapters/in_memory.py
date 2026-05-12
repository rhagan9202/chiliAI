"""In-memory workflow run store for tests and local development."""

from __future__ import annotations

from threading import RLock

from agent.exceptions import WorkflowRunNotFoundError
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowRunUpdate

__all__ = ["InMemoryWorkflowRunStore"]


class InMemoryWorkflowRunStore:
    """A seeded workflow run store keyed by workflow id."""

    def __init__(self, runs: list[WorkflowRun] | None = None) -> None:
        self._lock = RLock()
        self._runs: dict[str, WorkflowRun] = {}
        self._idempotency_index: dict[tuple[str, str], str] = {}
        for run in runs or []:
            self.save_run(run)

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        with self._lock:
            previous = self._runs.get(run.workflow_id)
            if previous is not None and previous.idempotency_key is not None:
                self._idempotency_index.pop(
                    (previous.knowledge_base_id, previous.idempotency_key), None
                )
            if run.idempotency_key is not None:
                idempotency_key = (run.knowledge_base_id, run.idempotency_key)
                indexed_workflow_id = self._idempotency_index.get(idempotency_key)
                if (
                    indexed_workflow_id is not None
                    and indexed_workflow_id != run.workflow_id
                ):
                    raise ValueError(
                        "Workflow idempotency key already exists for this "
                        "knowledge base."
                    )
            stored = self._copy_run(run)
            self._runs[stored.workflow_id] = stored
            if stored.idempotency_key is not None:
                self._idempotency_index[
                    (stored.knowledge_base_id, stored.idempotency_key)
                ] = stored.workflow_id
            return self._copy_run(stored)

    def get_run(self, workflow_id: str) -> WorkflowRun:
        with self._lock:
            run = self._runs.get(workflow_id)
            if run is None:
                raise WorkflowRunNotFoundError(workflow_id)
            return self._copy_run(run)

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
        with self._lock:
            runs = [
                run
                for run in self._runs.values()
                if (knowledge_base_id is None or run.knowledge_base_id == knowledge_base_id)
                and (status is None or run.status == status)
            ]
            runs.sort(key=lambda run: run.created_at, reverse=True)
            return [self._copy_run(run) for run in runs[offset : offset + limit]]

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun:
        with self._lock:
            existing = self._runs.get(workflow_id)
            if existing is None:
                raise WorkflowRunNotFoundError(workflow_id)
            patch = update.model_dump(exclude_none=True)
            if not patch:
                return self._copy_run(existing)
            merged = existing.model_dump()
            merged.update(patch)
            updated = WorkflowRun.model_validate(merged)
            self._runs[workflow_id] = self._copy_run(updated)
            return self._copy_run(updated)

    def delete_run(self, workflow_id: str) -> None:
        with self._lock:
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
        with self._lock:
            workflow_id = self._idempotency_index.get(
                (knowledge_base_id, idempotency_key)
            )
            if workflow_id is None:
                return None
            run = self._runs.get(workflow_id)
            if run is None:
                return None
            return self._copy_run(run)

    @staticmethod
    def _copy_run(run: WorkflowRun) -> WorkflowRun:
        """Return a detached copy of a workflow run."""

        return run.model_copy(deep=True)
