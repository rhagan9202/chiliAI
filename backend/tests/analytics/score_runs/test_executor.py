"""Tests for the score-batch executor."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.risk.exceptions import RiskInsufficientSignalsError
from analytics.risk.service_models import RiskAssessmentRequest, RiskAssessmentResponse
from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
import pytest

from analytics.score_runs import executor as score_runs_executor
from analytics.score_runs.executor import (
    handle_score_batch_queued,
    handle_score_run_queued,
)
from analytics.score_runs.models import ScoreBatch, ScoreRun
from config.schema import DomainConfig
from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity
from events.adapters.in_memory import InMemoryEventBus
from events.types import ScoreBatchQueuedEvent, ScoreRunQueuedEvent
from execution.deps import ExecutionDeps
from shared.utils import utc_now

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


def _run_queued_event(*, batch_size: int = 100) -> ScoreRunQueuedEvent:
    return ScoreRunQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id=_KB,
        run_id=_RUN_ID,
        batch_size=batch_size,
    )


def _deps_with_graph(
    repository: InMemoryScoreRunRepository,
    graph: InMemoryGraphRepository,
    *,
    batch_size: int = 100,
) -> ExecutionDeps:
    base = _deps(repository)
    return ExecutionDeps(
        event_bus=base.event_bus,
        risk_service=base.risk_service,
        score_run_repository=repository,
        graph_repository=graph,
        domain_config=base.domain_config,
    )


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


def test_entities_below_the_signal_floor_are_skipped_not_scored_or_failed() -> None:
    """A thin entity is neither scored nor broken.

    This test previously asserted `failed_entities == 1`, which was the real
    question at the time (does a skip inflate the *scored* count?) answered
    under the wrong name. Nothing failed: the executor catches
    `RiskInsufficientSignalsError`, logs it at INFO as an expected per-entity
    condition, and moves on. Counting that as a failure told operators a run
    had broken 57 times when it had done exactly what it was designed to do.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(0, ["e1", "e2"]))
    repository.update_run(_RUN_ID, total_entities=2)
    risk_service = _StubRiskService(insufficient={"e2"})

    handle_score_batch_queued(_event(), _deps(repository, risk_service=risk_service))

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities == 1
    assert run.skipped_entities == 1
    assert run.failed_entities == 0


def test_every_entity_lands_in_exactly_one_counter() -> None:
    """The three counters must partition the batch, or a run silently loses
    entities — the failure mode that made this bug invisible: `failed` was
    computed as a remainder, so it absorbed anything unaccounted for."""
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(0, ["e1", "e2", "e3", "e4"]))
    repository.update_run(_RUN_ID, total_entities=4)
    risk_service = _StubRiskService(insufficient={"e2", "e4"})

    handle_score_batch_queued(_event(), _deps(repository, risk_service=risk_service))

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.scored_entities + run.skipped_entities + run.failed_entities == 4
    assert (run.scored_entities, run.skipped_entities, run.failed_entities) == (2, 2, 0)


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
    assert batch.skipped_entities == 1
    assert batch.failed_entities == 0


def test_executor_enumerates_and_creates_batches_for_a_deferred_run() -> None:
    """A run started with entity_ids=None has no batches; the executor builds them.

    Enumeration moved out of the HTTP request (risk R2), so the first unit of
    work for such a run is enumeration, not scoring.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    graph = InMemoryGraphRepository()
    graph.upsert_entities(
        _KB, [Entity(id=f"e{n}", type="provider") for n in range(1, 4)]
    )
    deps = _deps_with_graph(repository, graph)

    processed = handle_score_run_queued(_run_queued_event(batch_size=2), deps)

    batches = repository.list_batches(run_id=_RUN_ID)
    run = repository.get_run(_RUN_ID)
    assert processed == 1
    assert [b.entity_ids for b in batches] == [["e1", "e2"], ["e3"]]
    assert run is not None and run.total_entities == 3


def test_enumeration_publishes_only_the_first_batch() -> None:
    """The chain advances one unit at a time; the executor enqueues successors."""
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    graph = InMemoryGraphRepository()
    graph.upsert_entities(
        _KB, [Entity(id=f"e{n}", type="provider") for n in range(1, 4)]
    )
    deps = _deps_with_graph(repository, graph)

    handle_score_run_queued(_run_queued_event(batch_size=1), deps)

    queued = [
        event
        for event in deps.event_bus.published_events  # type: ignore[union-attr]
        if event.event_type == "score.batch.queued"
    ]
    assert [event.batch_number for event in queued] == [0]


def test_enumerating_an_empty_knowledge_base_completes_the_run() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    deps = _deps_with_graph(repository, InMemoryGraphRepository())

    handle_score_run_queued(_run_queued_event(), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.status == "completed"
    assert run.total_entities == 0


def test_enumeration_is_idempotent_under_duplicate_delivery() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    graph = InMemoryGraphRepository()
    graph.upsert_entities(_KB, [Entity(id="e1", type="provider")])
    deps = _deps_with_graph(repository, graph)

    handle_score_run_queued(_run_queued_event(), deps)
    handle_score_run_queued(_run_queued_event(), deps)  # redelivered

    run = repository.get_run(_RUN_ID)
    assert len(repository.list_batches(run_id=_RUN_ID)) == 1
    assert run is not None and run.total_entities == 1


def test_executor_resumes_a_batch_abandoned_by_a_dead_worker() -> None:
    """The mid-run worker-death path.

    Worker A claims the batch and dies; its event sits in the Redis pending
    list until reclaim_stale_pending hands it to worker B. Without a reclaim
    window B could not take it, the batch would stall, and the reconciler would
    fail the whole run instead of resuming it.
    """
    repository, deps, risk_service = _seed(batches=[["e1"]])
    abandoned = datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc)
    repository.claim_batch(run_id=_RUN_ID, batch_number=0, now=abandoned)

    processed = handle_score_batch_queued(_event(), deps)

    run = repository.get_run(_RUN_ID)
    batch = repository.get_batch(run_id=_RUN_ID, batch_number=0)
    assert processed == 1
    assert [r.entity_id for r in risk_service.requests] == ["e1"]
    assert batch is not None and batch.attempts == 2
    assert run is not None and run.status == "completed"


def test_executor_does_not_steal_a_batch_a_live_worker_is_running() -> None:
    repository, deps, risk_service = _seed(batches=[["e1"]])
    repository.claim_batch(run_id=_RUN_ID, batch_number=0, now=utc_now())

    processed = handle_score_batch_queued(_event(), deps)

    assert processed == 0
    assert risk_service.requests == []


def test_a_batch_reclaimed_too_many_times_is_failed_not_retried_forever() -> None:
    """A batch that kills its worker every time must not loop indefinitely."""
    repository, deps, risk_service = _seed(batches=[["e1"]])
    abandoned = datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc)
    batch = repository.get_batch(run_id=_RUN_ID, batch_number=0)
    assert batch is not None
    repository.upsert_batch(
        batch.model_copy(
            update={"status": "running", "attempts": 5, "updated_at": abandoned}
        )
    )

    processed = handle_score_batch_queued(_event(), deps)

    reloaded = repository.get_batch(run_id=_RUN_ID, batch_number=0)
    run = repository.get_run(_RUN_ID)
    assert processed == 1
    assert risk_service.requests == []  # not re-scored
    assert reloaded is not None and reloaded.status == "failed"
    assert run is not None and run.status == "completed"
    assert run.failed_entities == 1


# --- bounded enumeration ----------------------------------------------------


class _CountingGraphRepository(InMemoryGraphRepository):
    """Records which read shape enumeration used."""

    def __init__(self) -> None:
        super().__init__()
        self.unbounded_calls = 0
        self.page_calls = 0

    def get_entities(self, knowledge_base_id: str) -> list[Entity]:
        self.unbounded_calls += 1
        return super().get_entities(knowledge_base_id)

    def get_entities_page(
        self, knowledge_base_id: str, *, limit: int, offset: int
    ) -> list[Entity]:
        self.page_calls += 1
        return super().get_entities_page(
            knowledge_base_id, limit=limit, offset=offset
        )


def _graph_with(count: int) -> _CountingGraphRepository:
    repository = _CountingGraphRepository()
    repository.upsert_entities(
        _KB,
        [Entity(id=f"entity-{index:04d}", type="provider") for index in range(count)],
    )
    return repository


def _enumeration_deps(
    graph_repository: _CountingGraphRepository,
) -> tuple[ExecutionDeps, InMemoryScoreRunRepository]:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    return _deps_with_graph(repository, graph_repository), repository


def test_enumeration_pages_rather_than_materialising_every_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk R2, second half.

    Moving enumeration into the worker made the read retryable; it did not make
    it bounded. `get_entities` has no LIMIT at all.
    """
    monkeypatch.setattr(score_runs_executor, "_ENUMERATION_PAGE_SIZE", 100)
    graph_repository = _graph_with(250)
    deps, repository = _enumeration_deps(graph_repository)

    handle_score_run_queued(_run_queued_event(batch_size=100), deps)

    assert graph_repository.unbounded_calls == 0
    assert graph_repository.page_calls >= 3
    assert repository.get_run(_RUN_ID) is not None


def test_enumeration_covers_every_entity_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test that matters.

    An off-by-one in a paging loop produces a run that **completes** having
    scored fewer entities than exist — no error, no failed batch, just a
    smaller number nobody checks.
    """
    monkeypatch.setattr(score_runs_executor, "_ENUMERATION_PAGE_SIZE", 7)
    graph_repository = _graph_with(25)
    deps, repository = _enumeration_deps(graph_repository)

    handle_score_run_queued(_run_queued_event(batch_size=4), deps)

    enumerated = [
        entity_id
        for batch in repository.list_batches(run_id=_RUN_ID)
        for entity_id in batch.entity_ids
    ]
    expected = sorted(entity.id for entity in graph_repository.get_entities(_KB))
    assert sorted(enumerated) == expected
    assert len(enumerated) == len(set(enumerated))
    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.total_entities == 25


def test_enumeration_handles_a_count_that_is_an_exact_multiple_of_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boundary an `is empty` termination check gets wrong.

    Stopping on a short page rather than an empty one saves a query per run;
    stopping on the wrong one either costs an extra query or drops the tail.
    """
    monkeypatch.setattr(score_runs_executor, "_ENUMERATION_PAGE_SIZE", 5)
    graph_repository = _graph_with(10)
    deps, repository = _enumeration_deps(graph_repository)

    handle_score_run_queued(_run_queued_event(batch_size=10), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.total_entities == 10


def test_an_empty_knowledge_base_completes_without_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(score_runs_executor, "_ENUMERATION_PAGE_SIZE", 5)
    graph_repository = _CountingGraphRepository()
    deps, repository = _enumeration_deps(graph_repository)

    handle_score_run_queued(_run_queued_event(batch_size=10), deps)

    run = repository.get_run(_RUN_ID)
    assert run is not None
    assert run.status == "completed"
    assert run.total_entities == 0
