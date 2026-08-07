"""Tests for stale connector sync-run reconciliation.

The executor advances a run by enqueueing its own successor, one page at a
time. That makes retry and cancellation granular, but it means a single lost
event stalls the run silently: no error, no terminal state, just a run that
stays `running` forever. This is the backstop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncRun,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
)
from connectors.reconciler import ConnectorSyncReconciler

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
_KB_ID = "kb-cms"
_CONNECTOR_ID = "cms-claims-drop"


def _definition() -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id=_CONNECTOR_ID,
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id=_KB_ID,
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims", mapping_version="v1", feed_name="claims_feed"
        ),
        config={"path": "/imports"},
    )


def _stale_run(
    *,
    status: str = "running",
    age: timedelta = timedelta(hours=3),
) -> tuple[InMemoryConnectorRepository, ConnectorSyncRun]:
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition())
    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            requested_by="operator-1",
        )
    )
    repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(status=status),  # type: ignore[arg-type]
    )
    repository.set_updated_at_for_test(run.run_id, NOW - age)
    stored = repository.get_run(run.run_id)
    assert stored is not None
    return repository, stored


def _reconciler(repository: InMemoryConnectorRepository) -> ConnectorSyncReconciler:
    return ConnectorSyncReconciler(repository, clock=lambda: NOW)


def test_reconciles_a_run_that_stopped_progressing() -> None:
    repository, run = _stale_run()

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 1

    reconciled = repository.get_run(run.run_id)
    assert reconciled is not None
    assert reconciled.status == "failed"
    assert reconciled.error_message == "stale_connector_sync_reconciled"


def test_reconciles_a_run_that_never_started() -> None:
    """`queued` counts too: a kickoff event lost before the first page leaves a
    run that never moves, and it is just as stuck as one that stalled mid-pull."""
    repository, run = _stale_run(status="queued")

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 1

    reconciled = repository.get_run(run.run_id)
    assert reconciled is not None
    assert reconciled.status == "failed"


def test_leaves_a_run_that_is_still_progressing() -> None:
    repository, run = _stale_run(age=timedelta(minutes=5))

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 0

    current = repository.get_run(run.run_id)
    assert current is not None
    assert current.status == "running"


def test_never_touches_a_terminal_run() -> None:
    """Reaching a terminal state is what makes a run immune."""
    repository, run = _stale_run(status="completed")

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 0

    current = repository.get_run(run.run_id)
    assert current is not None
    assert current.status == "completed"


def test_leaves_a_run_that_progressed_between_the_scan_and_the_write() -> None:
    """The re-read is the point.

    A page landing mid-sweep means the run is alive. Failing it would kill work
    that was proceeding correctly — and once operators have seen a reconciler do
    that, they stop trusting the ones that are right.
    """

    class _ProgressingRepository(InMemoryConnectorRepository):
        """Advances the run the first time the reconciler re-reads it."""

        def __init__(self) -> None:
            super().__init__()
            self.reread = False

        def get_run(self, run_id: str) -> ConnectorSyncRun | None:
            if not self.reread:
                self.reread = True
                super().update_run(
                    run_id, ConnectorSyncRunUpdate(source_cursor="claims.csv:250")
                )
            return super().get_run(run_id)

    repository = _ProgressingRepository()
    repository.save_definition(_definition())
    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            requested_by="operator-1",
        )
    )
    repository.update_run(run.run_id, ConnectorSyncRunUpdate(status="running"))
    repository.set_updated_at_for_test(run.run_id, NOW - timedelta(hours=3))

    reconciled = _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 0
    current = repository.get_run(run.run_id)
    assert current is not None
    assert current.status == "running"


def test_reconciles_across_knowledge_bases() -> None:
    """A maintenance sweep, not a KB-scoped query."""
    repository, first = _stale_run()
    other_kb = f"{_KB_ID}-other"
    repository.save_definition(
        _definition().model_copy(update={"knowledge_base_id": other_kb})
    )
    second = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=other_kb,
            requested_by="operator-1",
        )
    )
    repository.update_run(second.run_id, ConnectorSyncRunUpdate(status="running"))
    repository.set_updated_at_for_test(second.run_id, NOW - timedelta(hours=3))

    assert _reconciler(repository).reconcile_stale_runs(max_age_seconds=3600) == 2
    assert first.run_id != second.run_id


def test_respects_the_batch_size() -> None:
    repository, _ = _stale_run()

    reconciled = _reconciler(repository).reconcile_stale_runs(
        max_age_seconds=3600, batch_size=1
    )

    assert reconciled == 1


@pytest.mark.parametrize(
    ("max_age_seconds", "batch_size", "match"),
    [(0, 1000, "max_age_seconds"), (-1, 1000, "max_age_seconds"), (3600, 0, "batch_size")],
)
def test_rejects_nonsensical_bounds(
    max_age_seconds: int, batch_size: int, match: str
) -> None:
    repository, _ = _stale_run()

    with pytest.raises(ValueError, match=match):
        _reconciler(repository).reconcile_stale_runs(
            max_age_seconds=max_age_seconds, batch_size=batch_size
        )
