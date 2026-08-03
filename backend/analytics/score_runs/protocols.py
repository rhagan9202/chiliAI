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
        error_summary: str | None | object = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ScoreRun: ...

    def upsert_batch(self, batch: ScoreBatch) -> ScoreBatch: ...

    def list_batches(
        self,
        *,
        run_id: str,
        status: ScoreBatchStatus | None = None,
    ) -> list[ScoreBatch]: ...

    def delete_by_kb(self, knowledge_base_id: str) -> int: ...


__all__ = ["ScoreRunPage", "ScoreRunRepositoryProtocol"]
