"""Repository protocols for durable score-all run tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from analytics.score_runs.models import ScoreBatch, ScoreBatchStatus, ScoreRun, ScoreRunStatus


@dataclass(frozen=True)
class ScoreRunPage:
    """Offset-based page of score runs."""

    items: list[ScoreRun]
    total: int


@runtime_checkable
class ScoreRunRepositoryProtocol(Protocol):
    """Persist and query score-all run state."""

    def save_run(self, run: ScoreRun) -> ScoreRun: ...

    def get_run(self, run_id: str) -> ScoreRun | None: ...

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> ScoreRun | None: ...

    def list_runs(
        self,
        *,
        knowledge_base_id: str,
        status: ScoreRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScoreRunPage: ...

    def update_run(
        self,
        run_id: str,
        *,
        status: ScoreRunStatus | None = None,
        total_entities: int | None = None,
        scored_entities: int | None = None,
        failed_entities: int | None = None,
        skipped_entities: int | None = None,
        error_summary: str | None | object = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ScoreRun: ...

    def upsert_batch(self, batch: ScoreBatch) -> ScoreBatch: ...

    def get_batch(self, *, run_id: str, batch_number: int) -> ScoreBatch | None: ...

    def claim_batch(
        self,
        *,
        run_id: str,
        batch_number: int,
        now: datetime,
        stale_running_before: datetime | None = None,
    ) -> ScoreBatch | None:
        """Transition a ``queued`` batch to ``running`` and count the attempt.

        Returns ``None`` when the batch is absent or is not ``queued``. The
        caller must treat that as "another worker owns this unit" and stop,
        not as an error: Redis Streams redelivers, and ``reclaim_stale_pending``
        can hand the same event to a second worker, so this is the guard that
        stops two workers scoring one batch.

        ``stale_running_before`` additionally reclaims a batch left ``running``
        by a worker that died mid-batch: its event sits in the Redis pending
        list until ``reclaim_stale_pending`` hands it to another worker, and
        without a reclaim window that worker could never take it, so the batch
        would stall and the whole run would be failed by the reconciler instead
        of resuming. Pass ``None`` (the default) for queued-only claiming.

        Reclaiming is safe to race: scoring is keyed on a deterministic request
        id, so two workers scoring one batch converge on the same rows rather
        than duplicating them.

        Keyed on ``(run_id, batch_number)`` rather than the batch id because
        that is the natural key both storage layers already index on, and it is
        what ``ScoreBatchQueuedEvent`` carries.
        """
        ...

    def list_batches(
        self,
        *,
        run_id: str,
        status: ScoreBatchStatus | None = None,
    ) -> list[ScoreBatch]: ...

    def list_stale_runs(
        self,
        *,
        statuses: tuple[ScoreRunStatus, ...],
        updated_before: datetime,
        limit: int = 1000,
    ) -> list[ScoreRun]:
        """Runs in ``statuses`` not updated since ``updated_before``, any KB.

        Deliberately not `list_runs` with an optional knowledge_base_id: this is
        a maintenance scan across every KB, and conflating the two would make it
        easy to accidentally run an unscoped query on the analyst-facing path.
        """
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int: ...


__all__ = ["ScoreRunPage", "ScoreRunRepositoryProtocol"]
