"""Tests for the score-batch executor."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.risk.exceptions import RiskInsufficientSignalsError
from analytics.risk.service_models import RiskAssessmentRequest, RiskAssessmentResponse
from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.executor import handle_score_batch_queued
from analytics.score_runs.models import ScoreBatch, ScoreRun
from config.schema import DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from events.types import ScoreBatchQueuedEvent
from execution.deps import ExecutionDeps

BASE_TIME = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
_RUN_ID = "score-run-1"
_KB = "kb-1"


class _StubRiskService:
    """Records assess() calls and can be told to skip specific entities."""

    def __init__(self, *, insufficient: set[str] | None = None) -> None:
        self.requests: list[RiskAssessmentRequest] = []
        self._insufficient = insufficient or set()

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
        self.requests.append(request)
        if request.entity_id in self._insufficient:
            raise RiskInsufficientSignalsError(
                f"entity {request.entity_id} has too few signals"
            )
        return RiskAssessmentResponse(
            request_id=request.request_id,
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            overall_score=0.5,
            risk_level="medium",
            factor_count=0,
            factors=[],
        )


def _run(*, status: str = "queued", catalog_version: str = "cms-v1") -> ScoreRun:
    return ScoreRun(
        id=_RUN_ID,
        knowledge_base_id=_KB,
        status=status,  # type: ignore[arg-type]
        model_version="risk-linear-v1",
        catalog_version=catalog_version,
        total_entities=0,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _batch(batch_number: int, entity_ids: list[str]) -> ScoreBatch:
    return ScoreBatch(
        id=f"{_RUN_ID}-batch-{batch_number}",
        run_id=_RUN_ID,
        knowledge_base_id=_KB,
        batch_number=batch_number,
        status="queued",
        entity_ids=entity_ids,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _event(batch_number: int = 0) -> ScoreBatchQueuedEvent:
    return ScoreBatchQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id=_KB,
        run_id=_RUN_ID,
        batch_id=f"{_RUN_ID}-batch-{batch_number}",
        batch_number=batch_number,
    )


def _deps(
    repository: InMemoryScoreRunRepository,
    *,
    risk_service: _StubRiskService | None = None,
    catalog_version: str = "cms-v1",
) -> ExecutionDeps:
    config = DomainConfig.model_construct(
        feature_catalog=DomainConfig.model_fields["feature_catalog"].default_factory()  # type: ignore[misc]
    )
    object.__setattr__(config.feature_catalog, "version", catalog_version)
    return ExecutionDeps(
        event_bus=InMemoryEventBus(),
        risk_service=risk_service or _StubRiskService(),  # type: ignore[arg-type]
        score_run_repository=repository,
        graph_repository=None,
        domain_config=config,
    )


def _seed(
    *, batches: list[list[str]], run_status: str = "queued"
) -> tuple[InMemoryScoreRunRepository, ExecutionDeps, _StubRiskService]:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(status=run_status))
    total = 0
    for number, entity_ids in enumerate(batches):
        repository.upsert_batch(_batch(number, entity_ids))
        total += len(entity_ids)
    repository.update_run(_RUN_ID, total_entities=total)
    risk_service = _StubRiskService()
    return repository, _deps(repository, risk_service=risk_service), risk_service


def test_executor_scores_every_entity_in_the_batch() -> None:
    repository, deps, risk_service = _seed(batches=[["e1", "e2"]])

    processed = handle_score_batch_queued(_event(), deps)

    run = repository.get_run(_RUN_ID)
    assert processed == 1
    assert [r.entity_id for r in risk_service.requests] == ["e1", "e2"]
    assert run is not None and run.scored_entities == 2


def test_request_ids_are_derived_from_the_run_and_batch() -> None:
    """Determinism source is score_request_id, not the event correlation id.

    That is what makes a replayed batch re-assess idempotently instead of
    accumulating duplicate risk_score_history rows.
    """
    _, deps, risk_service = _seed(batches=[["e1"]])

    handle_score_batch_queued(_event(), deps)

    assert risk_service.requests[0].request_id == f"risk:{_RUN_ID}:batch-0:e1"


def test_executor_is_idempotent_under_duplicate_delivery() -> None:
    """Spec 6.1/6.4 — counters are derived from batch state, never incremented."""
    repository, deps, _ = _seed(batches=[["e1", "e2"]])

    handle_score_batch_queued(_event(), deps)
    handle_score_batch_queued(_event(), deps)  # redelivered after a reclaim

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities == 2  # NOT 4


def test_entities_below_the_signal_floor_count_as_failed_not_scored() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(0, ["e1", "e2"]))
    repository.update_run(_RUN_ID, total_entities=2)
    risk_service = _StubRiskService(insufficient={"e2"})

    handle_score_batch_queued(_event(), _deps(repository, risk_service=risk_service))

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities == 1
    assert run.failed_entities == 1


def test_executor_stops_without_scoring_when_the_run_is_cancelled() -> None:
    repository, deps, risk_service = _seed(batches=[["e1"]])
    repository.update_run(_RUN_ID, status="canceled")

    processed = handle_score_batch_queued(_event(), deps)

    batch = repository.get_batch(run_id=_RUN_ID, batch_number=0)
    assert processed == 0
    assert risk_service.requests == []
    assert batch is not None and batch.status == "queued"


def test_executor_enqueues_the_next_queued_batch() -> None:
    repository, deps, _ = _seed(batches=[["e1"], ["e2"]])

    handle_score_batch_queued(_event(batch_number=0), deps)

    queued = [
        event
        for event in deps.event_bus.published_events  # type: ignore[union-attr]
        if event.event_type == "score.batch.queued"
    ]
    assert [event.batch_number for event in queued] == [1]


def test_executor_completes_the_run_when_no_batches_remain() -> None:
    repository, deps, _ = _seed(batches=[["e1"]])

    handle_score_batch_queued(_event(), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.status == "completed"
    assert run.finished_at is not None


def test_executor_fails_the_run_when_the_catalog_version_changed_mid_run() -> None:
    """Spec 6.5 — dependencies rebuild between drains, so a pack hot-swap can
    resume a run under a different feature catalogue. Scoring the tail of a run
    against a catalogue it did not start with would make its own recorded
    catalog_version false.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(catalog_version="cms-v1"))
    repository.upsert_batch(_batch(0, ["e1"]))
    repository.update_run(_RUN_ID, total_entities=1)
    risk_service = _StubRiskService()
    deps = _deps(repository, risk_service=risk_service, catalog_version="cms-v2")

    processed = handle_score_batch_queued(_event(), deps)

    run = repository.get_run(_RUN_ID)
    assert processed == 0
    assert risk_service.requests == []
    assert run is not None
    assert run.status == "failed"
    assert run.error_summary == "catalog_version_changed"


def test_executor_returns_zero_when_a_required_dependency_is_missing() -> None:
    """A partially configured worker must not dead-letter every event."""
    repository, deps, _ = _seed(batches=[["e1"]])
    without_risk = ExecutionDeps(
        event_bus=deps.event_bus,
        risk_service=None,
        score_run_repository=repository,
        graph_repository=None,
        domain_config=deps.domain_config,
    )

    assert handle_score_batch_queued(_event(), without_risk) == 0


def test_counters_are_summed_across_batches_not_carried_forward() -> None:
    """Regression guard: the first implementation read the run's existing
    scored_entities when more than one batch had completed, which is
    incrementing by another name. Summing per-batch outcomes is what makes a
    replay idempotent.
    """
    repository, deps, _ = _seed(batches=[["e1", "e2"], ["e3"]])

    handle_score_batch_queued(_event(batch_number=0), deps)
    handle_score_batch_queued(_event(batch_number=1), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities == 3
    assert run.status == "completed"


def test_replaying_one_batch_of_many_does_not_inflate_the_run_total() -> None:
    repository, deps, _ = _seed(batches=[["e1", "e2"], ["e3"]])
    handle_score_batch_queued(_event(batch_number=0), deps)
    handle_score_batch_queued(_event(batch_number=1), deps)

    # A DLQ replay or replay_failed_batches re-drives batch 0.
    handle_score_batch_queued(_event(batch_number=0), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities == 3  # NOT 5


def test_batch_records_its_own_outcome() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(0, ["e1", "e2"]))
    repository.update_run(_RUN_ID, total_entities=2)
    risk_service = _StubRiskService(insufficient={"e2"})

    handle_score_batch_queued(_event(), _deps(repository, risk_service=risk_service))

    batch = repository.get_batch(run_id=_RUN_ID, batch_number=0)
    assert batch is not None
    assert batch.scored_entities == 1
    assert batch.failed_entities == 1
