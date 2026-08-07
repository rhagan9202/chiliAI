"""Tests for KB-scoped score-run API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.models import ScoreBatch
from analytics.score_runs.service import ScoreRunService, create_score_run_service
from api.contracts import ScoreRunReplayRequest, ScoreRunStartRequest
from api.middleware.auth import User
from api.routers import score_runs as score_runs_router
from graph.adapters.in_memory import InMemoryGraphRepository
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import Entity, KnowledgeBase


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _repository_with_kb() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-1",
            name="Score KB",
            description="Score-run test KB",
            created_at=BASE_TIME,
        )
    )
    return repository


def _service() -> tuple[ScoreRunService, InMemoryScoreRunRepository]:
    repository = InMemoryScoreRunRepository()
    return create_score_run_service(repository, clock=lambda: BASE_TIME), repository


def _graph_repository_with_entities(*entity_ids: str) -> InMemoryGraphRepository:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [Entity(id=entity_id, type="provider") for entity_id in entity_ids],
    )
    return repository


def test_start_score_run_maps_request_and_user() -> None:
    service, _ = _service()

    payload = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-1", "provider-2"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            idempotency_key="score-all:kb-1:v1",
            batch_size=1,
        ),
        _repository_with_kb(),
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    assert payload.created is True
    assert payload.run.knowledge_base_id == "kb-1"
    assert payload.run.requested_by == "operator-1"
    assert payload.run.status == "queued"
    assert [batch.batch_number for batch in payload.batches] == [0, 1]
    assert [batch.entity_ids for batch in payload.batches] == [
        ["provider-1"],
        ["provider-2"],
    ]


def test_list_score_runs_returns_recent_runs_for_kb() -> None:
    repository = InMemoryScoreRunRepository()
    times = iter(
        [
            BASE_TIME.replace(minute=0),
            BASE_TIME.replace(minute=1),
        ]
    )
    service = create_score_run_service(repository, clock=lambda: next(times))
    kb_repository = _repository_with_kb()
    first = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-1"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
        ),
        kb_repository,
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )
    # A KB may only have one live run (spec decision D3), so the first must
    # reach a terminal state before a second can start.
    repository.update_run(first.run.id, status="completed")
    second = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-2"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
        ),
        kb_repository,
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    payload = score_runs_router.list_score_runs(
        "kb-1",
        1,
        0,
        kb_repository,
        service,
        User(user_id="viewer-1", roles=["viewer"]),
    )

    assert payload.total == 2
    assert payload.limit == 1
    assert payload.offset == 0
    assert [run.id for run in payload.items] == [second.run.id]
    assert first.run.id != second.run.id


def test_start_score_run_defers_enumeration_to_the_executor() -> None:
    service, _ = _service()

    payload = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            batch_size=2,
        ),
        _repository_with_kb(),
        _graph_repository_with_entities("provider-1", "claim-1", "beneficiary-1"),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    assert payload.created is True
    # total_entities is authoritative only at completion (spec decision D2):
    # the executor enumerates, creates batches, and reconciles the total.
    assert payload.run.total_entities == 0
    assert payload.batches == []



def test_start_score_run_returns_existing_for_idempotency_key() -> None:
    service, _ = _service()
    request = ScoreRunStartRequest(
        entity_ids=["provider-1"],
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        idempotency_key="score-all:kb-1:v1",
    )
    first = score_runs_router.start_score_run(
        "kb-1",
        request,
        _repository_with_kb(),
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    second = score_runs_router.start_score_run(
        "kb-1",
        request,
        _repository_with_kb(),
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    assert second.created is False
    assert second.run.id == first.run.id


def test_start_score_run_404s_for_missing_kb() -> None:
    service, _ = _service()

    with pytest.raises(HTTPException) as exc_info:
        score_runs_router.start_score_run(
            "missing",
            ScoreRunStartRequest(
                entity_ids=["provider-1"],
                model_version="risk-linear-v1",
                catalog_version="cms-fraud-features-v1",
            ),
            InMemoryKnowledgeBaseRepository(),
            _graph_repository_with_entities(),
            service,
            User(user_id="operator-1", roles=["analyst"]),
        )

    assert exc_info.value.status_code == 404


def test_get_cancel_and_replay_score_run() -> None:
    service, repository = _service()
    kb_repository = _repository_with_kb()
    started = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-1", "provider-2"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            batch_size=1,
        ),
        kb_repository,
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )
    repository.upsert_batch(
        ScoreBatch(
            id="failed-batch",
            run_id=started.run.id,
            knowledge_base_id="kb-1",
            batch_number=1,
            status="failed",
            entity_ids=["provider-2"],
            updated_at=BASE_TIME,
        )
    )
    repository.update_run(
        started.run.id,
        status="failed",
        failed_entities=1,
        updated_at=BASE_TIME,
    )

    status_payload = score_runs_router.get_score_run(
        "kb-1",
        started.run.id,
        kb_repository,
        service,
        User(user_id="viewer-1", roles=["viewer"]),
    )
    replay_payload = score_runs_router.replay_score_run(
        "kb-1",
        started.run.id,
        ScoreRunReplayRequest(requested_by="operator-2", idempotency_key="replay-1"),
        kb_repository,
        service,  # type: ignore[arg-type]
        User(user_id="operator-ignored", roles=["analyst"]),
    )
    # The replay produced a live run; only one may be active per KB
    # (spec decision D3), so terminate it before starting a fresh one.
    repository.update_run(replay_payload.run.id, status="completed")
    cancelable = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-3"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
        ),
        kb_repository,
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )
    canceled_payload = score_runs_router.cancel_score_run(
        "kb-1",
        cancelable.run.id,
        kb_repository,
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    assert status_payload.run.id == started.run.id
    assert status_payload.batches[1].status == "failed"
    assert replay_payload.run.status == "queued"
    assert replay_payload.run.replay_of_run_id == started.run.id
    assert replay_payload.batches[0].entity_ids == ["provider-2"]
    assert canceled_payload.run.status == "canceled"


def test_get_score_run_hides_runs_from_other_kb() -> None:
    service, _ = _service()
    kb_repository = _repository_with_kb()
    started = score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(
            entity_ids=["provider-1"],
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
        ),
        kb_repository,
        _graph_repository_with_entities(),
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )
    kb_repository.create(
        KnowledgeBase(
            id="kb-2",
            name="Other KB",
            description="Other",
            created_at=BASE_TIME,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        score_runs_router.get_score_run(
            "kb-2",
            started.run.id,
            kb_repository,
            service,
            User(user_id="viewer-1", roles=["viewer"]),
        )

    assert exc_info.value.status_code == 404


def test_start_score_run_does_not_enumerate_entities_in_the_request() -> None:
    """Risk R2: the route used to list every entity in the KB synchronously.

    On a large KB that failed inside the HTTP request, before any executor was
    involved. Enumeration is the executor's job now.
    """

    class _CountingGraphRepository(InMemoryGraphRepository):
        def __init__(self) -> None:
            super().__init__()
            self.get_entities_calls = 0

        def get_entities(self, knowledge_base_id: str) -> list[Entity]:
            self.get_entities_calls += 1
            return super().get_entities(knowledge_base_id)

    service, _ = _service()
    graph_repository = _CountingGraphRepository()
    graph_repository.upsert_entities("kb-1", [Entity(id="e1", type="provider")])

    score_runs_router.start_score_run(
        "kb-1",
        ScoreRunStartRequest(model_version="m1", catalog_version="c1"),
        _repository_with_kb(),
        graph_repository,
        service,
        User(user_id="operator-1", roles=["analyst"]),
    )

    assert graph_repository.get_entities_calls == 0


def test_second_concurrent_run_for_the_same_kb_is_rejected() -> None:
    """Spec decision D3.

    Two live runs would race on risk_projections with last-write-wins and make
    scored_entities meaningless across runs.
    """
    service, _ = _service()
    kb_repository = _repository_with_kb()
    graph_repository = _graph_repository_with_entities("e1")
    request = ScoreRunStartRequest(model_version="m1", catalog_version="c1")

    score_runs_router.start_score_run(
        "kb-1", request, kb_repository, graph_repository, service, User(user_id="operator-1", roles=["analyst"])
    )

    with pytest.raises(HTTPException) as excinfo:
        score_runs_router.start_score_run(
            "kb-1", request, kb_repository, graph_repository, service, User(user_id="operator-1", roles=["analyst"])
        )

    assert excinfo.value.status_code == 409


def test_a_terminal_run_does_not_block_a_new_one() -> None:
    service, repository = _service()
    kb_repository = _repository_with_kb()
    graph_repository = _graph_repository_with_entities("e1")
    request = ScoreRunStartRequest(model_version="m1", catalog_version="c1")

    first = score_runs_router.start_score_run(
        "kb-1", request, kb_repository, graph_repository, service, User(user_id="operator-1", roles=["analyst"])
    )
    repository.update_run(first.run.id, status="completed")

    second = score_runs_router.start_score_run(
        "kb-1", request, kb_repository, graph_repository, service, User(user_id="operator-1", roles=["analyst"])
    )

    assert second.run.id != first.run.id
