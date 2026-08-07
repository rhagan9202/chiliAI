"""Service layer for durable score-all workflow state."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from analytics.score_runs.models import ScoreBatch, ScoreRun
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from events.protocols import EventBus
from events.types import (
    ScoreBatchQueuedEvent,
    ScoreRunQueuedEvent,
    ScoreRunStatusChangedEvent,
)
from shared.utils import generate_id, utc_now

__all__ = [
    "ScoreRunConflictError",
    "ScoreRunService",
    "ScoreRunStartResult",
    "create_score_run_service",
]


class ScoreRunConflictError(RuntimeError):
    """A score run is already active for this knowledge base.

    Two live runs would race on `risk_projections` with last-write-wins, making
    `scored_entities` meaningless across runs. Replay is unaffected: it targets
    an existing terminal run rather than starting a new one.
    """


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
        event_bus: EventBus | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self._event_bus = event_bus
        self._clock = clock

    def start_score_all(
        self,
        *,
        knowledge_base_id: str,
        entity_ids: Sequence[str] | None,
        requested_by: str | None,
        model_version: str,
        catalog_version: str,
        idempotency_key: str | None = None,
        batch_size: int = 100,
    ) -> ScoreRunStartResult:
        entities = None if entity_ids is None else _validated_entity_ids(entity_ids)
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

        # Only after the idempotency lookup: an idempotent retry (a client
        # resending after a network timeout) must get its existing run back,
        # not a 409 for the run it already started.
        self._reject_if_a_run_is_active(knowledge_base_id)

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
                total_entities=0 if entities is None else len(entities),
                created_at=now,
                updated_at=now,
            )
        )
        # entity_ids=None defers enumeration to the executor: listing every
        # entity in a large KB inside the HTTP request is risk R2, and it fails
        # the request before any executor is involved.
        batches = (
            []
            if entities is None
            else self._create_batches(
                run=run,
                entity_ids=entities,
                batch_size=batch_size,
                now=now,
            )
        )
        self._publish_status(run)
        if self._event_bus is None:
            # No bus configured (unit tests, in-process use): the run is durable
            # but nothing will drive it. Callers that need execution wire a bus.
            pass
        elif entities is None:
            # Nothing has been enumerated yet: hand the run to the executor,
            # which lists the KB's entities and creates the batches.
            self._event_bus.publish(
                ScoreRunQueuedEvent(
                    correlation_id=run.id,
                    knowledge_base_id=knowledge_base_id,
                    run_id=run.id,
                    batch_size=batch_size,
                )
            )
        elif batches:
            # Batches already exist; start the chain at the first one.
            self._event_bus.publish(
                ScoreBatchQueuedEvent(
                    correlation_id=run.id,
                    knowledge_base_id=knowledge_base_id,
                    run_id=run.id,
                    batch_id=batches[0].id,
                    batch_number=batches[0].batch_number,
                )
            )
        return ScoreRunStartResult(run=run, batches=batches, created=True)

    def _reject_if_a_run_is_active(self, knowledge_base_id: str) -> None:
        for status in ("queued", "running"):
            page = self.repository.list_runs(
                knowledge_base_id=knowledge_base_id,
                status=status,  # type: ignore[arg-type]
                limit=1,
            )
            if page.items:
                raise ScoreRunConflictError(
                    f"A score run is already active for knowledge base "
                    f"'{knowledge_base_id}'."
                )

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
        self._publish_status(canceled)
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
                status="queued",
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
        self._publish_status(run)
        if self._event_bus is not None and replay_batches:
            # Start the chain. `_publish_status` emits `score_run.status_changed`,
            # which is a *notification* the worker does not subscribe to — so
            # without this the replayed run is durable and completely inert:
            # queued forever, with nothing to explain why.
            #
            # Only the first batch. The executor enqueues batch N+1 from batch
            # N, so publishing all of them would run them concurrently and
            # defeat the sequencing the chain exists to provide.
            self._event_bus.publish(
                ScoreBatchQueuedEvent(
                    correlation_id=run.id,
                    knowledge_base_id=run.knowledge_base_id,
                    run_id=run.id,
                    batch_id=replay_batches[0].id,
                    batch_number=replay_batches[0].batch_number,
                )
            )
        return ScoreRunStartResult(run=run, batches=replay_batches, created=True)

    def list_batches(self, *, run_id: str) -> list[ScoreBatch]:
        return self.repository.list_batches(run_id=run_id)

    def list_runs(
        self,
        *,
        knowledge_base_id: str,
        limit: int = 50,
        offset: int = 0,
    ):
        return self.repository.list_runs(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )

    def get_run(self, run_id: str) -> ScoreRun:
        return self._require_run(run_id)

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

    def _publish_status(self, run: ScoreRun) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            ScoreRunStatusChangedEvent(
                knowledge_base_id=run.knowledge_base_id,
                run_id=run.id,
                status=run.status,
                total_entities=run.total_entities,
                scored_entities=run.scored_entities,
                failed_entities=run.failed_entities,
                model_version=run.model_version,
                catalog_version=run.catalog_version,
                replay_of_run_id=run.replay_of_run_id,
            )
        )


def create_score_run_service(
    repository: ScoreRunRepositoryProtocol,
    *,
    event_bus: EventBus | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> ScoreRunService:
    """Create the default score-run service."""

    return ScoreRunService(repository, event_bus=event_bus, clock=clock)


def _validated_entity_ids(entity_ids: Sequence[str]) -> list[str]:
    entities = list(entity_ids)
    if not entities:
        raise ValueError("entity_ids must include at least one entity.")
    if any(not entity_id for entity_id in entities):
        raise ValueError("entity_ids cannot include blank ids.")
    if len(set(entities)) != len(entities):
        raise ValueError("entity_ids must be unique.")
    return entities
