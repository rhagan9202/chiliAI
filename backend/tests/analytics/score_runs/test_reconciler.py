"""Tests for stale score-run reconciliation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.models import ScoreRun
from analytics.score_runs.reconciler import ScoreRunReconciler

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _run(
    run_id: str = "score-run-1",
    *,
    status: str = "running",
    age_hours: float = 3.0,
) -> ScoreRun:
    updated = NOW - timedelta(hours=age_hours)
    return ScoreRun(
        id=run_id,
        knowledge_base_id="kb-1",
        status=status,  # type: ignore[arg-type]
        model_version="risk-linear-v1",
        catalog_version="cms-v1",
        created_at=updated,
        updated_at=updated,
    )


def _reconciler(repository: InMemoryScoreRunRepository) -> ScoreRunReconciler:
    return ScoreRunReconciler(repository, clock=lambda: NOW)


def test_a_run_with_no_progress_past_the_cutoff_is_failed() -> None:
    """A dropped chain link leaves a run running with no error.

    The executor enqueues its own successor, so one lost event stalls the run
    silently. This is the backstop.
    """
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(age_hours=3))

    reconciled = _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600)

    run = repository.get_run("score-run-1")
    assert reconciled == 1
    assert run is not None
    assert run.status == "failed"
    assert run.error_summary == "stale_score_run_reconciled"
    assert run.finished_at is not None


def test_a_recently_updated_run_is_left_alone() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(age_hours=0.1))

    reconciled = _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600)

    run = repository.get_run("score-run-1")
    assert reconciled == 0
    assert run is not None and run.status == "running"


@pytest.mark.parametrize("status", ["completed", "failed", "canceled", "replayed"])
def test_terminal_runs_are_never_reconciled(status: str) -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(status=status, age_hours=99))

    reconciled = _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600)

    run = repository.get_run("score-run-1")
    assert reconciled == 0
    assert run is not None and run.status == status


def test_queued_runs_are_reconciled_too() -> None:
    """A run whose very first event was lost never leaves `queued`."""
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run(status="queued", age_hours=5))

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 1


def test_reconciliation_is_scoped_per_knowledge_base_run() -> None:
    repository = InMemoryScoreRunRepository()
    repository.save_run(_run("stale-1", age_hours=5))
    fresh = _run("fresh-1", age_hours=0.1)
    repository.save_run(fresh.model_copy(update={"knowledge_base_id": "kb-2"}))

    reconciled = _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 1
    stale = repository.get_run("stale-1")
    fresh_run = repository.get_run("fresh-1")
    assert stale is not None and stale.status == "failed"
    assert fresh_run is not None and fresh_run.status == "running"


def test_rejects_a_non_positive_max_age() -> None:
    repository = InMemoryScoreRunRepository()
    with pytest.raises(ValueError, match="max_age_seconds"):
        _reconciler(repository).reconcile_stale_runs(max_age_seconds=0)
