"""Tests for the in-memory score-run repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.models import ScoreBatch, ScoreRun


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _run(
    run_id: str = "score-run-1",
    *,
    knowledge_base_id: str = "kb-1",
    created_at: datetime = BASE_TIME,
    idempotency_key: str | None = "score-all:kb-1:catalog-v1:model-v1",
    status: str = "queued",
    total_entities: int = 3,
) -> ScoreRun:
    return ScoreRun(
        id=run_id,
        knowledge_base_id=knowledge_base_id,
        status=status,  # type: ignore[arg-type]
        requested_by="operator-1",
        idempotency_key=idempotency_key,
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        created_at=created_at,
        updated_at=created_at,
        total_entities=total_entities,
    )


def _batch(
    run_id: str = "score-run-1",
    batch_number: int = 0,
    *,
    knowledge_base_id: str = "kb-1",
    entity_ids: list[str] | None = None,
    status: str = "queued",
    updated_at: datetime = BASE_TIME,
) -> ScoreBatch:
    return ScoreBatch(
        id=f"{run_id}-batch-{batch_number}",
        run_id=run_id,
        knowledge_base_id=knowledge_base_id,
        batch_number=batch_number,
        status=status,  # type: ignore[arg-type]
        entity_ids=entity_ids or ["provider-1", "provider-2"],
        attempts=0,
        updated_at=updated_at,
    )


def test_save_run_indexes_idempotency_and_returns_detached_copies() -> None:
    repository = InMemoryScoreRunRepository()
    saved = repository.save_run(_run())

    saved.status = "running"  # type: ignore[assignment]

    by_id = repository.get_run("score-run-1")
    by_key = repository.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="score-all:kb-1:catalog-v1:model-v1",
    )

    assert by_id is not None
    assert by_id.status == "queued"
    assert by_key is not None
    assert by_key.id == "score-run-1"
    assert by_key.status == "queued"


def test_save_run_rejects_conflicting_idempotency_key_for_same_kb() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run("score-run-1"))

    with pytest.raises(ValueError, match="idempotency_key"):
        repository.save_run(_run("score-run-2"))

    assert repository.save_run(_run("score-run-2", knowledge_base_id="kb-2")).id == "score-run-2"


def test_save_run_replaces_stale_idempotency_index_for_same_run() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run("score-run-1", idempotency_key="old"))
    repository.save_run(_run("score-run-1", idempotency_key="new"))

    assert repository.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="old",
    ) is None
    assert repository.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="new",
    ).id == "score-run-1"  # type: ignore[union-attr]

    repository.save_run(_run("score-run-1", idempotency_key=None))

    assert repository.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="new",
    ) is None


def test_update_run_tracks_status_counts_timing_and_error_summary() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    started_at = BASE_TIME + timedelta(minutes=1)
    finished_at = BASE_TIME + timedelta(minutes=5)

    running = repository.update_run(
        "score-run-1",
        status="running",
        started_at=started_at,
        scored_entities=1,
        failed_entities=0,
        updated_at=started_at,
    )
    completed = repository.update_run(
        "score-run-1",
        status="completed",
        scored_entities=3,
        failed_entities=0,
        finished_at=finished_at,
        error_summary=None,
        updated_at=finished_at,
    )

    assert running.status == "running"
    assert completed.status == "completed"
    assert completed.started_at == started_at
    assert completed.finished_at == finished_at
    assert completed.scored_entities == 3
    assert completed.failed_entities == 0


def test_update_run_revalidates_counts() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(total_entities=2))

    with pytest.raises(ValueError, match="cannot exceed total_entities"):
        repository.update_run(
            "score-run-1",
            scored_entities=2,
            failed_entities=1,
        )

    assert repository.get_run("score-run-1").scored_entities == 0  # type: ignore[union-attr]


def test_batch_upsert_replaces_same_run_batch_and_lists_in_order() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=1, entity_ids=["provider-3"]))
    repository.upsert_batch(_batch(batch_number=0, entity_ids=["provider-1", "provider-2"]))
    repository.upsert_batch(
        _batch(
            batch_number=1,
            entity_ids=["provider-3"],
            status="failed",
            updated_at=BASE_TIME + timedelta(minutes=2),
        )
    )

    batches = repository.list_batches(run_id="score-run-1")

    assert [batch.batch_number for batch in batches] == [0, 1]
    assert batches[1].status == "failed"
    assert batches[1].updated_at == BASE_TIME + timedelta(minutes=2)


def test_list_runs_filters_sorts_newest_first_and_paginates() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run("old", created_at=BASE_TIME, idempotency_key="old"))
    repository.save_run(
        _run(
            "new-a",
            created_at=BASE_TIME + timedelta(hours=1),
            idempotency_key="new-a",
        )
    )
    repository.save_run(
        _run(
            "new-b",
            created_at=BASE_TIME + timedelta(hours=1),
            idempotency_key="new-b",
        )
    )
    repository.save_run(_run("failed", idempotency_key="failed", status="failed"))
    repository.save_run(
        _run("other-kb", knowledge_base_id="kb-2", idempotency_key="other-kb")
    )

    page = repository.list_runs(
        knowledge_base_id="kb-1",
        status="queued",
        limit=2,
        offset=0,
    )

    assert page.total == 3
    assert [run.id for run in page.items] == ["new-b", "new-a"]
    next_page = repository.list_runs(
        knowledge_base_id="kb-1",
        status="queued",
        limit=2,
        offset=2,
    )
    assert [run.id for run in next_page.items] == ["old"]


def test_delete_by_kb_removes_runs_batches_and_idempotency_index() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run("delete-a", idempotency_key="delete-a"))
    repository.save_run(_run("delete-b", idempotency_key="delete-b"))
    repository.save_run(_run("keep", knowledge_base_id="kb-2", idempotency_key="keep"))
    repository.upsert_batch(_batch(run_id="delete-a"))
    repository.upsert_batch(_batch(run_id="keep", knowledge_base_id="kb-2"))

    assert repository.delete_by_kb("kb-1") == 2
    assert repository.get_run("delete-a") is None
    assert repository.list_batches(run_id="delete-a") == []
    assert repository.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="delete-a",
    ) is None
    assert repository.get_run("keep") is not None
    assert len(repository.list_batches(run_id="keep")) == 1
