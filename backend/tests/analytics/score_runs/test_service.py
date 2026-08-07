"""Tests for the score-run orchestration service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.models import ScoreBatch, ScoreRun
from analytics.score_runs.service import ScoreRunService, ScoreRunStartResult, create_score_run_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import ScoreRunStatusChangedEvent


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _service() -> ScoreRunService:
    return create_score_run_service(InMemoryScoreRunRepository(), clock=lambda: BASE_TIME)


def _service_with_events() -> tuple[ScoreRunService, InMemoryEventBus]:
    event_bus = InMemoryEventBus()
    return (
        create_score_run_service(
            InMemoryScoreRunRepository(),
            event_bus=event_bus,
            clock=lambda: BASE_TIME,
        ),
        event_bus,
    )


def test_start_score_all_creates_idempotent_run_and_queued_batches() -> None:
    service = _service()

    first = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1", "provider-2", "claim-1"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        idempotency_key="score-all:kb-1:v1",
        batch_size=2,
    )
    second = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1", "provider-2", "claim-1"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        idempotency_key="score-all:kb-1:v1",
        batch_size=2,
    )

    assert second.run.id == first.run.id
    assert second.created is False
    assert first.created is True
    assert first.run.status == "queued"
    assert first.run.total_entities == 3
    assert [batch.batch_number for batch in first.batches] == [0, 1]
    assert [batch.entity_ids for batch in first.batches] == [
        ["provider-1", "provider-2"],
        ["claim-1"],
    ]
    assert service.list_batches(run_id=first.run.id) == first.batches


def test_start_score_all_publishes_status_event_once_for_idempotent_retries() -> None:
    service, event_bus = _service_with_events()

    first = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1", "provider-2"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        idempotency_key="score-all:kb-1:v1",
    )
    second = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1", "provider-2"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        idempotency_key="score-all:kb-1:v1",
    )

    assert second.created is False
    # Starting a run now also publishes the event that drives execution, so
    # count status events specifically: the point is that the idempotent retry
    # publishes nothing at all.
    status_events = [
        published
        for published in event_bus.published_events
        if published.event_type == "score_run.status_changed"
    ]
    assert len(status_events) == 1
    event = status_events[0]
    assert isinstance(event, ScoreRunStatusChangedEvent)
    assert event.run_id == first.run.id
    assert event.status == "queued"
    assert event.total_entities == 2
    assert event.model_version == "risk-linear-v1"
    assert event.catalog_version == "cms-fraud-features-v1"


def test_start_score_all_rejects_empty_entities_and_invalid_batch_size() -> None:
    service = _service()

    with pytest.raises(ValueError, match="entity_ids"):
        service.start_score_all(
            knowledge_base_id="kb-1",
            entity_ids=[],
            requested_by=None,
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
        )

    with pytest.raises(ValueError, match="batch_size"):
        service.start_score_all(
            knowledge_base_id="kb-1",
            entity_ids=["provider-1"],
            requested_by=None,
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            batch_size=0,
        )


def test_cancel_run_marks_run_and_queued_batches_canceled() -> None:
    service = _service()
    result = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1", "provider-2", "claim-1"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        batch_size=2,
    )

    service.repository.upsert_batch(
        result.batches[0].model_copy(update={"status": "completed"})
    )
    canceled = service.cancel_run(result.run.id)

    assert canceled.status == "canceled"
    batches = service.list_batches(run_id=result.run.id)
    assert [batch.status for batch in batches] == ["completed", "canceled"]


def test_cancel_run_publishes_status_event() -> None:
    service, event_bus = _service_with_events()
    result = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
    )

    canceled = service.cancel_run(result.run.id)

    event = event_bus.published_events[-1]
    assert isinstance(event, ScoreRunStatusChangedEvent)
    assert event.run_id == canceled.id
    assert event.status == "canceled"


def test_cancel_completed_run_is_rejected() -> None:
    service = _service()
    run = service.repository.save_run(
        ScoreRun(
            id="score-run-1",
            knowledge_base_id="kb-1",
            status="completed",
            requested_by="operator-1",
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            total_entities=1,
            scored_entities=1,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
            started_at=BASE_TIME,
            finished_at=BASE_TIME + timedelta(minutes=1),
        )
    )

    with pytest.raises(ValueError, match="cannot cancel"):
        service.cancel_run(run.id)


def test_replay_failed_batches_links_new_run_and_requeues_failed_entities() -> None:
    service = _service()
    original = service.repository.save_run(
        ScoreRun(
            id="score-run-original",
            knowledge_base_id="kb-1",
            status="failed",
            requested_by="operator-1",
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            total_entities=4,
            scored_entities=2,
            failed_entities=2,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
        )
    )
    service.repository.upsert_batch(
        ScoreBatch(
            id="batch-ok",
            run_id=original.id,
            knowledge_base_id="kb-1",
            batch_number=0,
            status="completed",
            entity_ids=["provider-1", "provider-2"],
            updated_at=BASE_TIME,
        )
    )
    service.repository.upsert_batch(
        ScoreBatch(
            id="batch-failed",
            run_id=original.id,
            knowledge_base_id="kb-1",
            batch_number=1,
            status="failed",
            entity_ids=["claim-1", "claim-2"],
            attempts=2,
            error_summary="source unavailable",
            updated_at=BASE_TIME,
        )
    )

    replay = service.replay_failed_batches(
        original.id,
        requested_by="operator-2",
        idempotency_key="replay:kb-1:score-run-original",
    )

    assert replay.run.status == "queued"
    assert replay.run.replay_of_run_id == original.id
    assert replay.run.total_entities == 2
    assert replay.run.requested_by == "operator-2"
    assert [batch.entity_ids for batch in replay.batches] == [["claim-1", "claim-2"]]
    assert replay.batches[0].attempts == 0
    assert replay.batches[0].status == "queued"


def test_replay_failed_batches_publishes_replayed_status_event() -> None:
    service, event_bus = _service_with_events()
    original = service.repository.save_run(
        ScoreRun(
            id="score-run-original",
            knowledge_base_id="kb-1",
            status="failed",
            requested_by="operator-1",
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            total_entities=1,
            failed_entities=1,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
        )
    )
    service.repository.upsert_batch(
        ScoreBatch(
            id="batch-failed",
            run_id=original.id,
            knowledge_base_id="kb-1",
            batch_number=0,
            status="failed",
            entity_ids=["claim-1"],
            updated_at=BASE_TIME,
        )
    )

    replay = service.replay_failed_batches(original.id, requested_by="operator-2")

    # Selected explicitly rather than taken as the last event: replay now also
    # publishes the batch event that drives execution, so positional access
    # silently asserts against whichever publish happens to come last.
    event = next(
        published
        for published in event_bus.published_events
        if isinstance(published, ScoreRunStatusChangedEvent)
    )
    assert event.run_id == replay.run.id
    assert event.status == "queued"
    assert event.replay_of_run_id == original.id


def test_replay_failed_batches_requires_failed_batches() -> None:
    service = _service()
    run = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=["provider-1"],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
    ).run

    with pytest.raises(ValueError, match="failed batches"):
        service.replay_failed_batches(run.id, requested_by="operator-2")


def test_score_request_id_is_deterministic_per_run_and_entity() -> None:
    service = _service()

    request_id = service.score_request_id(
        run_id="score-run-1",
        batch_number=3,
        entity_id="provider-7",
    )

    assert request_id == "risk:score-run-1:batch-3:provider-7"
    assert service.score_request_id(
        run_id="score-run-1",
        batch_number=3,
        entity_id="provider-7",
    ) == request_id


def _run_with_failed_batches(
    service: ScoreRunService, *, batch_count: int = 2
) -> ScoreRunStartResult:
    """A run whose batches have all failed, ready to replay."""
    started = service.start_score_all(
        knowledge_base_id="kb-1",
        entity_ids=[f"provider-{index}" for index in range(batch_count)],
        requested_by="operator-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        batch_size=1,
    )
    for batch in started.batches:
        service.repository.upsert_batch(batch.model_copy(update={"status": "failed"}))
    service.repository.update_run(started.run.id, status="failed")
    return started


def _batch_events(event_bus: InMemoryEventBus, *, run_id: str) -> list[object]:
    """Batch events for one run.

    Scoped by run id deliberately: `start_score_all` publishes a batch event of
    its own, so an unscoped count is satisfied by the setup run and every
    assertion about the replay passes without the replay publishing anything.
    """
    return [
        published
        for published in event_bus.published_events
        if published.event_type == "score.batch.queued"
        and getattr(published, "run_id", None) == run_id
    ]


def test_replaying_failed_batches_enqueues_the_first_replayed_batch() -> None:
    """Without this the replayed run is durable and completely inert.

    `_publish_status` emits `score_run.status_changed`, which is a notification
    — the worker does not subscribe to it. Live-confirmed 2026-08-07: a replayed
    run stayed `queued` with `scored=0` indefinitely.
    """
    service, event_bus = _service_with_events()
    original = _run_with_failed_batches(service)

    result = service.replay_failed_batches(original.run.id, requested_by="operator-2")

    queued = _batch_events(event_bus, run_id=result.run.id)
    assert len(queued) == 1
    assert queued[0].run_id == result.run.id  # type: ignore[attr-defined]
    assert queued[0].batch_number == result.batches[0].batch_number  # type: ignore[attr-defined]


def test_replay_enqueues_only_the_first_batch_not_all_of_them() -> None:
    """The executor chains its own successor.

    Publishing every batch would run them concurrently, defeating the
    sequencing the chain exists to provide.
    """
    service, event_bus = _service_with_events()
    original = _run_with_failed_batches(service, batch_count=3)

    result = service.replay_failed_batches(original.run.id, requested_by="operator-2")

    assert len(result.batches) == 3
    assert len(_batch_events(event_bus, run_id=result.run.id)) == 1


def test_an_idempotent_replay_does_not_enqueue_a_second_time() -> None:
    service, event_bus = _service_with_events()
    original = _run_with_failed_batches(service)

    first = service.replay_failed_batches(
        original.run.id, requested_by="operator-2", idempotency_key="replay-1"
    )
    second = service.replay_failed_batches(
        original.run.id, requested_by="operator-2", idempotency_key="replay-1"
    )

    assert second.run.id == first.run.id
    assert second.created is False
    assert len(_batch_events(event_bus, run_id=first.run.id)) == 1


def test_replay_without_an_event_bus_still_creates_the_run() -> None:
    """In-process callers and unit tests may have no bus configured."""
    service = _service()
    original = _run_with_failed_batches(service)

    result = service.replay_failed_batches(original.run.id, requested_by="operator-2")

    assert result.created is True
    assert result.run.status == "queued"
