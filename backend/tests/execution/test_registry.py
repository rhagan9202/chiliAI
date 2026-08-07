"""Tests for the executor dispatch seam."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from events.types import AnyEvent, RecordsIngestedEvent, ScoreBatchQueuedEvent
from execution.deps import ExecutionDeps
from execution.registry import dispatch, register_handler, registered_event_types


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Each test starts from the real registry and restores it afterwards."""
    from execution import registry

    original = dict(registry._HANDLERS)
    yield
    registry._HANDLERS.clear()
    registry._HANDLERS.update(original)


def _deps() -> ExecutionDeps:
    return ExecutionDeps(
        event_bus=None,
        risk_service=None,
        score_run_repository=None,
        graph_repository=None,
        domain_config=None,
    )


def _score_batch_event() -> ScoreBatchQueuedEvent:
    return ScoreBatchQueuedEvent(
        correlation_id="c1",
        knowledge_base_id="kb-1",
        run_id="run-1",
        batch_id="batch-1",
        batch_number=0,
    )


def test_dispatch_returns_zero_for_an_event_with_no_handler() -> None:
    """Pipeline events flow past the seam untouched."""
    event = RecordsIngestedEvent(
        correlation_id="c1",
        knowledge_base_id="kb-1",
        feed_name="carrier_claims_a",
        record_type="carrier_claim_record",
        record_count=1,
    )

    assert dispatch(event, _deps()) == 0


def test_dispatch_routes_to_the_registered_handler() -> None:
    seen: list[str] = []

    def _handler(event: AnyEvent, deps: ExecutionDeps) -> int:
        seen.append(event.event_type)
        return 1

    register_handler("score.batch.queued", _handler)

    assert dispatch(_score_batch_event(), _deps()) == 1
    assert seen == ["score.batch.queued"]


def test_dispatch_lets_handler_exceptions_propagate() -> None:
    """The worker's retry/DLQ wrapper owns failure, not the seam.

    Swallowing here would make a failed unit look successful and silently break
    the dead-letter contract.
    """

    def _boom(event: AnyEvent, deps: ExecutionDeps) -> int:
        raise RuntimeError("executor failed")

    register_handler("score.batch.queued", _boom)

    with pytest.raises(RuntimeError, match="executor failed"):
        dispatch(_score_batch_event(), _deps())


def test_registered_event_types_reflects_registrations() -> None:
    """The worker's subscription list must be a superset of this."""

    def _handler(event: AnyEvent, deps: ExecutionDeps) -> int:
        return 1

    register_handler("score.batch.queued", _handler)

    assert "score.batch.queued" in registered_event_types()
