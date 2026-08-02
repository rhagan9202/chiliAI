"""Service layer for durable score-all workflow state."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from analytics.score_runs.models import ScoreBatch, ScoreRun
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from shared.utils import generate_id, utc_now

__all__ = ["ScoreRunStartResult", "ScoreRunService", "create_score_run_service"]


@dataclass(frozen=True)
class ScoreRunStartResult:
    """A score-run start or replay result plus its queued work batches."""

    run: ScoreRun
    batches: list[ScoreBatch]
    created: bool


class ScoreRunService:
    """Coordinate score-all run state without executing scoring inline."""

    def __init__(
        self,
        repository: ScoreRunRepositoryProtocol,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self._clock = clock

    def start_score_all(
        self,
        *,
        knowledge_base_id: str,
        entity_ids: Sequence[str],
        requested_by: str | None,
        model_version: str,
        catalog_version: str,
        idempotency_key: str | None = None,
        batch_size: int = 100,
    ) -> ScoreRunStartResult:
        entities = _validated_entity_ids(entity_ids)
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")
        if idempotency_key is not None:
            existing = self.repository.find_by_idempotency_key(
                knowledge_base_id=knowledge_base_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return ScoreRunStartResult(
                    run=existing,
                    batches=self.repository.list_batches(run_id=existing.id),
                    created=False,
                )

        now = self._now()
        run = self.repository.save_run(
            ScoreRun(
                id=generate_id(),
                knowledge_base_id=knowledge_base_id,
                status="queued",
                requested_by=requested_by,
                idempotency_key=idempotency_key,
                model_version=model_version,
                catalog_version=catalog_version,
                total_entities=len(entities),
                created_at=now,
                updated_at=now,
            )
        )
        batches = self._create_batches(
            run=run,
            entity_ids=entities,
            batch_size=batch_size,
            now=now,
        )
        return ScoreRunStartResult(run=run, batches=batches, created=True)

    def cancel_run(self, run_id: str) -> ScoreRun:
        run = self._require_run(run_id)
        if run.status not in {"queued", "running"}:
            raise ValueError(f"ScoreRun '{run_id}' cannot cancel from status '{run.status}'.")
        now = self._now()
        canceled = self.repository.update_run(
            run_id,
            status="canceled",
            finished_at=now,
            updated_at=now,
        )
        for batch in self.repository.list_batches(run_id=run_id):
            if batch.status in {"queued", "running"}:
                self.repository.upsert_batch(
                    batch.model_copy(
                        update={
                            "status": "canceled",
                            "finished_at": now,
                            "updated_at": now,
                        }
                    )
                )
        return canceled

    def replay_failed_batches(
        self,
        run_id: str,
        *,
        requested_by: str | None,
        idempotency_key: str | None = None,
    ) -> ScoreRunStartResult:
        original = self._require_run(run_id)
        failed_batches = self.repository.list_batches(run_id=run_id, status="failed")
        if not failed_batches:
            raise ValueError(f"ScoreRun '{run_id}' has no failed batches to replay.")
        if idempotency_key is not None:
            existing = self.repository.find_by_idempotency_key(
                knowledge_base_id=original.knowledge_base_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return ScoreRunStartResult(
                    run=existing,
                    batches=self.repository.list_batches(run_id=existing.id),
                    created=False,
                )

        now = self._now()
        run = self.repository.save_run(
            ScoreRun(
                id=generate_id(),
                knowledge_base_id=original.knowledge_base_id,
                status="replayed",
                requested_by=requested_by,
                idempotency_key=idempotency_key,
                model_version=original.model_version,
                catalog_version=original.catalog_version,
                replay_of_run_id=original.id,
                total_entities=sum(len(batch.entity_ids) for batch in failed_batches),
                created_at=now,
                updated_at=now,
            )
        )
        replay_batches = [
            self.repository.upsert_batch(
                ScoreBatch(
                    id=f"{run.id}:batch-{index}",
                    run_id=run.id,
                    knowledge_base_id=run.knowledge_base_id,
                    batch_number=index,
                    status="queued",
                    entity_ids=list(batch.entity_ids),
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            for index, batch in enumerate(failed_batches)
        ]
        return ScoreRunStartResult(run=run, batches=replay_batches, created=True)

    def list_batches(self, *, run_id: str) -> list[ScoreBatch]:
        return self.repository.list_batches(run_id=run_id)

    def score_request_id(self, *, run_id: str, batch_number: int, entity_id: str) -> str:
        return f"risk:{run_id}:batch-{batch_number}:{entity_id}"

    def _create_batches(
        self,
        *,
        run: ScoreRun,
        entity_ids: list[str],
        batch_size: int,
        now: datetime,
    ) -> list[ScoreBatch]:
        batches: list[ScoreBatch] = []
        for batch_number, start in enumerate(range(0, len(entity_ids), batch_size)):
            batch = ScoreBatch(
                id=f"{run.id}:batch-{batch_number}",
                run_id=run.id,
                knowledge_base_id=run.knowledge_base_id,
                batch_number=batch_number,
                status="queued",
                entity_ids=entity_ids[start : start + batch_size],
                created_at=now,
                updated_at=now,
            )
            batches.append(self.repository.upsert_batch(batch))
        return batches

    def _require_run(self, run_id: str) -> ScoreRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def _now(self) -> datetime:
        return self._clock()


def create_score_run_service(
    repository: ScoreRunRepositoryProtocol,
    *,
    clock: Callable[[], datetime] = utc_now,
) -> ScoreRunService:
    """Create the default score-run service."""

    return ScoreRunService(repository, clock=clock)


def _validated_entity_ids(entity_ids: Sequence[str]) -> list[str]:
    entities = list(entity_ids)
    if not entities:
        raise ValueError("entity_ids must include at least one entity.")
    if any(not entity_id for entity_id in entities):
        raise ValueError("entity_ids cannot include blank ids.")
    if len(set(entities)) != len(entities):
        raise ValueError("entity_ids must be unique.")
    return entities
