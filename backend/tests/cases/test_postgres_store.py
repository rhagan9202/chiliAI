"""Integration tests for the Postgres case repository (BL-010)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from cases.adapters.postgres import PostgresCaseRepository
from cases.exceptions import CaseConcurrentModificationError, CaseNotFoundError
from cases.models import Case, CasePriority, CaseStatus, CaseTimelineEvent
from cases.service import create_case_service
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from shared.types import Alert
from shared.utils import utc_now

pytestmark = pytest.mark.integration

_KB = "kb-cases-test"


def _case(
    case_id: str, *, status: CaseStatus = "open", priority: CasePriority = "high"
) -> Case:
    return Case(
        id=case_id,
        knowledge_base_id=_KB,
        title=f"Case {case_id}",
        status=status,
        priority=priority,
        originating_alert_id="alert-1",
        evidence_pack_id="ev-1",
        alert_ids=["alert-1"],
        timeline=[
            CaseTimelineEvent(
                occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                label="promoted",
                detail="Promoted from alert-1.",
            )
        ],
    )


def _alert(alert_id: str) -> Alert:
    return Alert(
        id=alert_id,
        entity_type="provider",
        entity_id="provider-1",
        severity="high",
        title="Elevated risk: provider-1",
        reasoning="Unusual billing.",
        evidence_pack_id="ev-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def test_case_repository_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresCaseRepository(provider)
    try:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()

        repo.create(_case("c1"))
        repo.create(_case("c2", status="closed", priority="low"))

        # Idempotent create.
        repo.create(_case("c1"))

        fetched = repo.get(knowledge_base_id=_KB, case_id="c1")
        assert fetched is not None
        assert fetched.evidence_pack_id == "ev-1"
        assert fetched.alert_ids == ["alert-1"]
        assert fetched.timeline[0].label == "promoted"

        items, total = repo.list(knowledge_base_id=_KB, limit=10, offset=0)
        assert total == 2
        assert {case.id for case in items} == {"c1", "c2"}

        open_items, open_total = repo.list(
            knowledge_base_id=_KB, limit=10, offset=0, status="open"
        )
        assert open_total == 1
        assert [case.id for case in open_items] == ["c1"]

        updated = fetched.model_copy(update={"status": "closed", "updated_at": utc_now()})
        repo.update(updated, expected_updated_at=fetched.updated_at)
        refetched = repo.get(knowledge_base_id=_KB, case_id="c1")
        assert refetched is not None
        assert refetched.status == "closed"

        assert repo.get(knowledge_base_id="other-kb", case_id="c1") is None
    finally:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()


def test_update_missing_raises(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresCaseRepository(provider)

    with pytest.raises(CaseNotFoundError):
        repo.update(_case("ghost-case"), expected_updated_at=utc_now())


def test_update_raises_when_the_row_changed_concurrently(database_url: str) -> None:
    """A stale ``updated_at`` snapshot must not be honored (unit-level guard).

    Same defect as the threaded test below, exercised directly against the
    repository with an explicit stale snapshot instead of real concurrency.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresCaseRepository(provider)
    try:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()

        repo.create(_case("c-cas"))
        stale = repo.get(knowledge_base_id=_KB, case_id="c-cas")
        assert stale is not None

        # A legitimate concurrent writer commits first, using the same snapshot.
        winner = stale.model_copy(update={"status": "closed", "updated_at": utc_now()})
        repo.update(winner, expected_updated_at=stale.updated_at)

        with pytest.raises(CaseConcurrentModificationError):
            repo.update(
                stale.model_copy(update={"priority": "critical", "updated_at": utc_now()}),
                expected_updated_at=stale.updated_at,
            )

        final = repo.get(knowledge_base_id=_KB, case_id="c-cas")
        assert final is not None
        assert final.status == "closed"
        assert final.priority == "high"  # the loser's write never landed
    finally:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()


def test_concurrent_attach_does_not_silently_drop_the_other_alert(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two analysts attach different alerts to one case at the same time.

    Both read alert_ids=['alert-1'], both pass the duplicate check, and --
    pre-fix -- both write the whole jsonb array from their own stale copy.
    Whoever commits second wins and the other attachment vanishes, with no
    error raised to the loser. Post-fix, exactly one thread must succeed and
    the other must raise CaseConcurrentModificationError.

    A threading.Barrier forces both threads' ``repository.get`` (the read
    inside ``CaseService.attach_alert``) to complete before either thread's
    write proceeds, reproducing the interleave deterministically.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresCaseRepository(provider)
    service = create_case_service(repo)
    try:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()

        repo.create(_case("c-race"))

        barrier = threading.Barrier(2)
        original_get = repo.get

        def synced_get(*, knowledge_base_id: str, case_id: str) -> Case | None:
            barrier.wait(timeout=5)
            result = original_get(knowledge_base_id=knowledge_base_id, case_id=case_id)
            barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(repo, "get", synced_get)

        results: dict[str, Case | BaseException] = {}

        def attach(alert_id: str) -> None:
            try:
                results[alert_id] = service.attach_alert(
                    knowledge_base_id=_KB, case_id="c-race", alert=_alert(alert_id)
                )
            except BaseException as exc:  # captured for the joining thread to assert on
                results[alert_id] = exc

        thread_a = threading.Thread(target=attach, args=("alert-2",))
        thread_b = threading.Thread(target=attach, args=("alert-3",))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        final = original_get(knowledge_base_id=_KB, case_id="c-race")
        assert final is not None

        successes = {
            alert_id: result for alert_id, result in results.items() if isinstance(result, Case)
        }
        failures = {
            alert_id: result
            for alert_id, result in results.items()
            if isinstance(result, BaseException)
        }
        assert len(successes) == 1 and len(failures) == 1, (
            "expected exactly one thread to succeed and the other to raise "
            f"CaseConcurrentModificationError; got results={results!r}, "
            f"final.alert_ids={final.alert_ids!r}"
        )
        [failure] = failures.values()
        assert isinstance(failure, CaseConcurrentModificationError)

        winner_alert_id = next(iter(successes))
        assert final.alert_ids == ["alert-1", winner_alert_id]
        assert final.timeline[-1].label == "Alert attached"
    finally:
        with provider.connection() as conn:
            conn.execute("DELETE FROM cases WHERE knowledge_base_id = %s", (_KB,))
            conn.commit()
