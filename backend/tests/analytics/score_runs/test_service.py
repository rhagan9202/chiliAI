"""Tests for the score-run orchestration service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.models import ScoreBatch, ScoreRun
from analytics.score_runs.service import ScoreRunService, create_score_run_service


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _service() -> ScoreRunService:
    return create_score_run_service(InMemoryScoreRunRepository(), clock=lambda: BASE_TIME)


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

    assert replay.run.status == "replayed"
    assert replay.run.replay_of_run_id == original.id
    assert replay.run.total_entities == 2
    assert replay.run.requested_by == "operator-2"
    assert [batch.entity_ids for batch in replay.batches] == [["claim-1", "claim-2"]]
    assert replay.batches[0].attempts == 0
    assert replay.batches[0].status == "queued"


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

