"""Adapter-level protocols for workflow run persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowRunUpdate


@runtime_checkable
class WorkflowRunStoreProtocol(Protocol):
    """Persist and retrieve workflow runs.

    Implementations must return detached ``WorkflowRun`` objects so callers
    cannot mutate persisted state except through ``save_run`` or
    ``update_run``. ``save_run`` acts as an upsert keyed by ``workflow_id`` and
    must enforce uniqueness for ``(knowledge_base_id, idempotency_key)`` when
    an idempotency key is present. ``list_runs`` returns newest-first results
    ordered by ``created_at``. ``delete_run`` is idempotent for missing IDs.
    In-process stores must protect reads and writes that touch shared indexes.
    """

    # TODO(production): Implement durable adapters behind this protocol —
    # PostgresWorkflowRunStore, RedisWorkflowRunStore — for production deployments.

    def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    def get_run(self, workflow_id: str) -> WorkflowRun: ...

    def list_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]: ...

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun: ...

    def delete_run(self, workflow_id: str) -> None: ...

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> WorkflowRun | None: ...


__all__ = [
    "WorkflowRunStoreProtocol",
]
