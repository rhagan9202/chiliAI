"""Integration tests for the Postgres case repository (BL-010)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cases.adapters.postgres import PostgresCaseRepository
from cases.exceptions import CaseNotFoundError
from cases.models import Case, CasePriority, CaseStatus, CaseTimelineEvent
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

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

        updated = _case("c1", status="closed")
        repo.update(updated)
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
        repo.update(_case("ghost-case"))
