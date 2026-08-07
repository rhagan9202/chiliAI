"""In-memory score-run repository for tests and local development."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from analytics.score_runs.models import ScoreBatch, ScoreBatchStatus, ScoreRun, ScoreRunStatus
from analytics.score_runs.protocols import ScoreRunPage
from shared.utils import utc_now

__all__ = ["InMemoryScoreRunRepository"]

_UNSET = object()


class InMemoryScoreRunRepository:
    """A dict-backed score-run repository with KB-scoped idempotency indexes."""

    def __init__(self) -> None:
        self._runs: dict[str, ScoreRun] = {}
        self._idempotency_index: dict[tuple[str, str], str] = {}
        self._batches: dict[tuple[str, int], ScoreBatch] = {}

    def save_run(self, run: ScoreRun) -> ScoreRun:
        if run.idempotency_key is not None:
            key = (run.knowledge_base_id, run.idempotency_key)
            existing_id = self._idempotency_index.get(key)
            if existing_id is not None and existing_id != run.id:
                raise ValueError("ScoreRun idempotency_key already exists for this knowledge base.")
        stored = _copy_run(run)
        existing = self._runs.get(stored.id)
        if existing is not None and existing.idempotency_key is not None:
            self._idempotency_index.pop(
                (existing.knowledge_base_id, existing.idempotency_key),
                None,
            )
        self._runs[stored.id] = stored
        if stored.idempotency_key is not None:
            self._idempotency_index[(stored.knowledge_base_id, stored.idempotency_key)] = stored.id
        return _copy_run(stored)

    def get_run(self, run_id: str) -> ScoreRun | None:
        run = self._runs.get(run_id)
        return _copy_run(run) if run is not None else None

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> ScoreRun | None:
        run_id = self._idempotency_index.get((knowledge_base_id, idempotency_key))
        if run_id is None:
            return None
        return self.get_run(run_id)

    def list_runs(
        self,
        *,
        knowledge_base_id: str,
        status: ScoreRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScoreRunPage:
        matches = [
            run
            for run in self._runs.values()
            if run.knowledge_base_id == knowledge_base_id
            and (status is None or run.status == status)
        ]
        matches.sort(key=lambda run: (run.created_at, run.id), reverse=True)
        total = len(matches)
        if limit <= 0 or offset < 0:
            return ScoreRunPage(items=[], total=total)
        return ScoreRunPage(
            items=[_copy_run(run) for run in matches[offset : offset + limit]],
            total=total,
        )

    def update_run(
        self,
        run_id: str,
        *,
        status: ScoreRunStatus | None = None,
        total_entities: int | None = None,
        scored_entities: int | None = None,
        failed_entities: int | None = None,
        error_summary: str | None | object = _UNSET,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ScoreRun:
        existing = self._runs.get(run_id)
        if existing is None:
            raise KeyError(run_id)
        update: dict[str, Any] = {"updated_at": updated_at or utc_now()}
        if status is not None:
            update["status"] = status
        if total_entities is not None:
            update["total_entities"] = total_entities
        if scored_entities is not None:
            update["scored_entities"] = scored_entities
        if failed_entities is not None:
            update["failed_entities"] = failed_entities
        if error_summary is not _UNSET:
            update["error_summary"] = error_summary
        if started_at is not None:
            update["started_at"] = started_at
        if finished_at is not None:
            update["finished_at"] = finished_at
        data = existing.model_dump()
        data.update(update)
        updated = ScoreRun(**data)
        self._runs[run_id] = updated
        return _copy_run(updated)

    def upsert_batch(self, batch: ScoreBatch) -> ScoreBatch:
        key = (batch.run_id, batch.batch_number)
        stored = _copy_batch(batch)
        self._batches[key] = stored
        return _copy_batch(stored)

    def get_batch(self, *, run_id: str, batch_number: int) -> ScoreBatch | None:
        batch = self._batches.get((run_id, batch_number))
        return _copy_batch(batch) if batch is not None else None

    def claim_batch(
        self,
        *,
        run_id: str,
        batch_number: int,
        now: datetime,
    ) -> ScoreBatch | None:
        key = (run_id, batch_number)
        batch = self._batches.get(key)
        if batch is None or batch.status != "queued":
            return None
        claimed = batch.model_copy(
            update={
                "status": "running",
                "attempts": batch.attempts + 1,
                "started_at": batch.started_at or now,
                "updated_at": now,
            }
        )
        self._batches[key] = claimed
        return _copy_batch(claimed)

    def list_batches(
        self,
        *,
        run_id: str,
        status: ScoreBatchStatus | None = None,
    ) -> list[ScoreBatch]:
        matches = [
            batch
            for (candidate_run_id, _), batch in self._batches.items()
            if candidate_run_id == run_id and (status is None or batch.status == status)
        ]
        matches.sort(key=lambda batch: batch.batch_number)
        return [_copy_batch(batch) for batch in matches]

    def list_stale_runs(
        self,
        *,
        statuses: tuple[ScoreRunStatus, ...],
        updated_before: datetime,
        limit: int = 1000,
    ) -> list[ScoreRun]:
        matches = [
            run
            for run in self._runs.values()
            if run.status in statuses and run.updated_at < updated_before
        ]
        matches.sort(key=lambda run: run.updated_at)
        return [_copy_run(run) for run in matches[:limit]]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        run_ids = [
            run_id
            for run_id, run in self._runs.items()
            if run.knowledge_base_id == knowledge_base_id
        ]
        for run_id in run_ids:
            removed = self._runs.pop(run_id)
            if removed.idempotency_key is not None:
                self._idempotency_index.pop((knowledge_base_id, removed.idempotency_key), None)
        batch_keys = [
            key
            for key, batch in self._batches.items()
            if batch.knowledge_base_id == knowledge_base_id
        ]
        for key in batch_keys:
            del self._batches[key]
        return len(run_ids)


def _copy_run(run: ScoreRun) -> ScoreRun:
    return run.model_copy(deep=True)


def _copy_batch(batch: ScoreBatch) -> ScoreBatch:
    return batch.model_copy(deep=True)
