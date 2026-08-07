"""Executor for score-all batches.

Consumes one ``score.batch.queued`` event per batch, scores its entities, and
chains to the next batch until the run is complete.

Exceptions propagate on purpose: ``run_handler_with_retry`` in the worker owns
retry and dead-lettering. Only *expected* per-entity conditions are swallowed —
an entity below the signal floor is a failed entity, not a failed batch.
"""

from __future__ import annotations

import logging

from analytics.risk.exceptions import RiskConfigurationError, RiskInsufficientSignalsError
from analytics.risk.service_models import RiskAssessmentRequest
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from events.types import AnyEvent, ScoreBatchQueuedEvent
from execution.deps import ExecutionDeps
from execution.registry import register_handler
from shared.utils import utc_now

__all__ = ["handle_score_batch_queued"]

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled", "replayed"})


def score_request_id(*, run_id: str, batch_number: int, entity_id: str) -> str:
    """Deterministic risk request id for one entity in one batch.

    Mirrors ``ScoreRunService.score_request_id``. Deriving from the run and
    batch rather than the event correlation id is what makes a replayed batch
    re-assess idempotently instead of accumulating duplicate
    ``risk_score_history`` rows.
    """

    return f"risk:{run_id}:batch-{batch_number}:{entity_id}"


def handle_score_batch_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Score one batch, then enqueue the next or complete the run."""

    if not isinstance(event, ScoreBatchQueuedEvent):
        return 0
    repository = deps.score_run_repository
    risk_service = deps.risk_service
    event_bus = deps.event_bus
    if repository is None or risk_service is None or event_bus is None:
        # A partially configured worker does no work rather than dead-lettering
        # every event it is handed.
        logger.debug("Score-batch executor is not configured; skipping.")
        return 0

    run = repository.get_run(event.run_id)
    if run is None or run.status in _TERMINAL_RUN_STATUSES:
        return 0

    active_catalog = _active_catalog_version(deps)
    if active_catalog is not None and active_catalog != run.catalog_version:
        # Dependencies rebuild between drain iterations, so a pack hot-swap can
        # resume this run under a different feature catalogue. Fail loudly
        # rather than scoring the tail of a run against a catalogue it did not
        # start with.
        repository.update_run(
            run.id,
            status="failed",
            error_summary="catalog_version_changed",
            finished_at=utc_now(),
        )
        return 0

    batch = repository.claim_batch(
        run_id=event.run_id, batch_number=event.batch_number, now=utc_now()
    )
    if batch is None:
        # Not queued: already claimed by another worker, or this is a
        # redelivery of a batch that finished. Neither is an error.
        return 0

    if run.started_at is None:
        repository.update_run(run.id, status="running", started_at=utc_now())

    scored = 0
    for entity_id in batch.entity_ids:
        try:
            risk_service.assess(
                RiskAssessmentRequest(
                    knowledge_base_id=batch.knowledge_base_id,
                    entity_id=entity_id,
                    request_id=score_request_id(
                        run_id=run.id,
                        batch_number=batch.batch_number,
                        entity_id=entity_id,
                    ),
                )
            )
            scored += 1
        except (RiskInsufficientSignalsError, RiskConfigurationError) as exc:
            # Expected per-entity conditions: one thin entity must not abort a
            # batch. Infrastructure failures propagate to the retry/DLQ path.
            logger.info("Skipping risk assess for entity=%s: %s", entity_id, exc)

    repository.upsert_batch(
        batch.model_copy(
            update={
                "status": "completed",
                "scored_entities": scored,
                "failed_entities": len(batch.entity_ids) - scored,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
    )
    _reconcile_run_counters(repository, run_id=run.id)
    _advance(
        repository,
        deps,
        run_id=run.id,
        knowledge_base_id=batch.knowledge_base_id,
        correlation_id=event.correlation_id,
    )
    return 1


def _reconcile_run_counters(
    repository: ScoreRunRepositoryProtocol, *, run_id: str
) -> None:
    """Recompute run counters as a pure sum over batch state.

    Never incremented. A batch can be delivered more than once — a Redis
    redelivery, `replay_failed_batches`, or a DLQ replay — and incrementing
    would double-count, which also trips the run's
    `scored + failed <= total` validator on an otherwise legitimate update.
    Summing is naturally idempotent because each batch carries its own outcome.
    """

    batches = repository.list_batches(run_id=run_id)
    repository.update_run(
        run_id,
        scored_entities=sum(batch.scored_entities for batch in batches),
        failed_entities=sum(batch.failed_entities for batch in batches),
    )


def _advance(
    repository: ScoreRunRepositoryProtocol,
    deps: ExecutionDeps,
    *,
    run_id: str,
    knowledge_base_id: str,
    correlation_id: str,
) -> None:
    """Enqueue the next queued batch, or terminate the run when none remain."""

    remaining = repository.list_batches(run_id=run_id, status="queued")
    if not remaining:
        repository.update_run(run_id, status="completed", finished_at=utc_now())
        return
    nxt = remaining[0]
    event_bus = deps.event_bus
    if event_bus is None:  # pragma: no cover - guarded by the caller
        return
    event_bus.publish(
        ScoreBatchQueuedEvent(
            correlation_id=correlation_id,
            knowledge_base_id=knowledge_base_id,
            run_id=run_id,
            batch_id=nxt.id,
            batch_number=nxt.batch_number,
        )
    )


def _active_catalog_version(deps: ExecutionDeps) -> str | None:
    config = deps.domain_config
    if config is None:
        return None
    return config.feature_catalog.version


register_handler("score.batch.queued", handle_score_batch_queued)
