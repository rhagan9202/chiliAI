"""Executor for score-all batches.

Consumes one ``score.batch.queued`` event per batch, scores its entities, and
chains to the next batch until the run is complete.

Exceptions propagate on purpose: ``run_handler_with_retry`` in the worker owns
retry and dead-lettering. Only *expected* per-entity conditions are swallowed —
an entity below the signal floor is a failed entity, not a failed batch.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from analytics.risk.exceptions import RiskConfigurationError, RiskInsufficientSignalsError
from analytics.risk.service_models import RiskAssessmentRequest
from analytics.score_runs.models import ScoreBatch
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from events.types import AnyEvent, ScoreBatchQueuedEvent, ScoreRunQueuedEvent
from graph.adapters.protocols import GraphRepository
from execution.deps import ExecutionDeps
from execution.registry import register_handler
from shared.utils import utc_now

__all__ = ["handle_score_batch_queued", "handle_score_run_queued"]

logger = logging.getLogger(__name__)

def _positive_int_from_env(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on anything odd."""

    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%s must be positive; using %s", name, value, default)
        return default
    return value


_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled", "replayed"})

# How long a batch may sit `running` before another worker may take it over.
# Must exceed the time a healthy batch takes: too short and two workers score
# the same batch concurrently. That is safe — scoring is keyed on a
# deterministic request id, so they converge on the same rows — but wasteful.
_STALE_BATCH_SECONDS = _positive_int_from_env("CHILI_SCORE_BATCH_STALE_SECONDS", 900)

# A batch that kills its worker every time would otherwise be reclaimed
# forever. attempts counts claims, so this caps the takeover loop.
_MAX_BATCH_ATTEMPTS = _positive_int_from_env("CHILI_SCORE_BATCH_MAX_ATTEMPTS", 5)

# Entities read per graph query during enumeration. `get_entities` has no LIMIT
# at all, so a large knowledge base was one unbounded read.
_ENUMERATION_PAGE_SIZE = _positive_int_from_env(
    "CHILI_SCORE_ENUMERATION_PAGE_SIZE", 1000
)


def _enumerate_entity_ids(
    graph_repository: GraphRepository, knowledge_base_id: str
) -> list[str]:
    """Every entity id in a knowledge base, read a page at a time.

    Stops on a short page rather than an empty one: an entity count that is an
    exact multiple of the page size would otherwise cost an extra round trip
    every run.

    A dropped page here is worse than a crash — enumeration would complete over
    a subset and the run would report success having scored fewer entities than
    exist, with no error anywhere.
    """

    entity_ids: list[str] = []
    offset = 0
    while True:
        page = graph_repository.get_entities_page(
            knowledge_base_id, limit=_ENUMERATION_PAGE_SIZE, offset=offset
        )
        entity_ids.extend(entity.id for entity in page)
        if len(page) < _ENUMERATION_PAGE_SIZE:
            return entity_ids
        offset += _ENUMERATION_PAGE_SIZE


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

    now = utc_now()
    existing = repository.get_batch(
        run_id=event.run_id, batch_number=event.batch_number
    )
    if existing is not None and existing.attempts >= _MAX_BATCH_ATTEMPTS:
        # Reclaimed too many times: something about this batch takes down its
        # worker. Fail it rather than looping, so the run can still terminate
        # and the failure is visible on the batch.
        repository.upsert_batch(
            existing.model_copy(
                update={
                    "status": "failed",
                    "failed_entities": len(existing.entity_ids),
                    "error_summary": "max_attempts_exceeded",
                    "finished_at": now,
                    "updated_at": now,
                }
            )
        )
        _reconcile_run_counters(repository, run_id=run.id)
        _advance(
            repository,
            deps,
            run_id=run.id,
            knowledge_base_id=run.knowledge_base_id,
            correlation_id=event.correlation_id,
        )
        return 1

    batch = repository.claim_batch(
        run_id=event.run_id,
        batch_number=event.batch_number,
        now=now,
        # Reclaim a batch abandoned by a worker that died mid-flight: its event
        # is redelivered by reclaim_stale_pending, and without this the claim
        # fails, the batch stalls, and the reconciler fails the whole run.
        stale_running_before=now - timedelta(seconds=_STALE_BATCH_SECONDS),
    )
    if batch is None:
        # Still owned by a live worker, or a redelivery of a finished batch.
        # Neither is an error.
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


def handle_score_run_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Enumerate a run's entities, create its batches, and start the chain.

    Runs started without an explicit entity list arrive here first. Enumeration
    lives in the executor rather than the HTTP request so a large knowledge base
    cannot fail the request before any work is durable (risk R2).

    The graph read is paged. The accumulated id list is still held in memory to
    form batches, so this is bounded *per query* rather than streaming — a
    smaller claim than it sounds, and the honest one.
    """

    if not isinstance(event, ScoreRunQueuedEvent):
        return 0
    repository = deps.score_run_repository
    graph_repository = deps.graph_repository
    event_bus = deps.event_bus
    if repository is None or graph_repository is None or event_bus is None:
        logger.debug("Score-run enumeration is not configured; skipping.")
        return 0

    run = repository.get_run(event.run_id)
    if run is None or run.status in _TERMINAL_RUN_STATUSES:
        return 0
    if repository.list_batches(run_id=run.id):
        # Already enumerated: this is a redelivery. Re-enumerating would
        # duplicate batches and inflate total_entities.
        return 0

    entity_ids = _enumerate_entity_ids(graph_repository, run.knowledge_base_id)
    if not entity_ids:
        repository.update_run(
            run.id, status="completed", total_entities=0, finished_at=utc_now()
        )
        return 1

    now = utc_now()
    for batch_number, chunk in enumerate(_chunk(entity_ids, event.batch_size)):
        repository.upsert_batch(
            ScoreBatch(
                id=f"{run.id}-batch-{batch_number}",
                run_id=run.id,
                knowledge_base_id=run.knowledge_base_id,
                batch_number=batch_number,
                status="queued",
                entity_ids=list(chunk),
                created_at=now,
                updated_at=now,
            )
        )
    repository.update_run(run.id, total_entities=len(entity_ids))

    first = repository.list_batches(run_id=run.id, status="queued")[0]
    event_bus.publish(
        ScoreBatchQueuedEvent(
            correlation_id=event.correlation_id,
            knowledge_base_id=run.knowledge_base_id,
            run_id=run.id,
            batch_id=first.id,
            batch_number=first.batch_number,
        )
    )
    return 1


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


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
register_handler("score.run.queued", handle_score_run_queued)
