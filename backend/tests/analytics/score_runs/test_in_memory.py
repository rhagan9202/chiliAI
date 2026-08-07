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


def test_claim_batch_transitions_queued_to_running_and_counts_the_attempt() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    claimed = repository.claim_batch(
        run_id="score-run-1", batch_number=0, now=BASE_TIME
    )

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.started_at == BASE_TIME


def test_claim_batch_returns_none_when_another_worker_already_claimed_it() -> None:
    """The claim is the concurrency guard: a second caller must get nothing.

    Redis Streams redelivers, and `reclaim_stale_pending` can hand the same
    event to a second worker. Without this, both execute the same batch.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    first = repository.claim_batch(run_id="score-run-1", batch_number=0, now=BASE_TIME)
    second = repository.claim_batch(run_id="score-run-1", batch_number=0, now=BASE_TIME)

    assert first is not None
    assert second is None


def test_claim_batch_returns_none_for_an_unknown_batch() -> None:
    repository = InMemoryScoreRunRepository()
    assert repository.claim_batch(run_id="nope", batch_number=0, now=BASE_TIME) is None


def test_get_batch_returns_a_detached_copy() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    fetched = repository.get_batch(run_id="score-run-1", batch_number=0)
    assert fetched is not None
    fetched.status = "failed"  # type: ignore[assignment]

    assert repository.get_batch(run_id="score-run-1", batch_number=0).status == "queued"


def test_get_batch_returns_none_for_an_unknown_batch() -> None:
    repository = InMemoryScoreRunRepository()
    assert repository.get_batch(run_id="nope", batch_number=0) is None


def test_claim_batch_reclaims_a_running_batch_older_than_the_threshold() -> None:
    """A worker killed mid-batch leaves it `running` with the event in the PEL.

    reclaim_stale_pending hands that event to another worker; without this the
    claim returns None, the batch is stuck forever, and the whole run is
    eventually failed by the reconciler instead of resuming.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))
    repository.claim_batch(run_id="score-run-1", batch_number=0, now=BASE_TIME)

    later = BASE_TIME + timedelta(minutes=30)
    reclaimed = repository.claim_batch(
        run_id="score-run-1",
        batch_number=0,
        now=later,
        stale_running_before=later - timedelta(minutes=10),
    )

    assert reclaimed is not None
    assert reclaimed.status == "running"
    assert reclaimed.attempts == 2  # the reclaim is a second attempt


def test_claim_batch_does_not_reclaim_a_batch_still_within_the_threshold() -> None:
    """A healthy in-flight batch must never be stolen from its worker."""
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))
    repository.claim_batch(run_id="score-run-1", batch_number=0, now=BASE_TIME)

    soon = BASE_TIME + timedelta(seconds=30)
    assert (
        repository.claim_batch(
            run_id="score-run-1",
            batch_number=0,
            now=soon,
            stale_running_before=soon - timedelta(minutes=10),
        )
        is None
    )


def test_claim_batch_without_a_threshold_never_reclaims() -> None:
    """Default behaviour is unchanged: only `queued` batches are claimable."""
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))
    repository.claim_batch(run_id="score-run-1", batch_number=0, now=BASE_TIME)

    assert (
        repository.claim_batch(
            run_id="score-run-1",
            batch_number=0,
            now=BASE_TIME + timedelta(hours=5),
        )
        is None
    )
