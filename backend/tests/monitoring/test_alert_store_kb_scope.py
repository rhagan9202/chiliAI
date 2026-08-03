"""`list_alerts` filters by knowledge base in the store (UXA-408).

Before this, every KB-scoped alert read fetched the entire `alert_history`
table and filtered in Python (`api/dependencies.py::get_alert_list_payload`),
so the cost of reading one knowledge base's queue grew with every other
knowledge base's alerts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.models import AlertHistoryRecord


def _record(
    alert_id: str,
    *,
    knowledge_base_id: str = "kb-1",
    severity: str = "high",
    status: str = "open",
    day: int = 16,
    evidence_pack_id: str | None = None,
    tags: list[str] | None = None,
) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id=knowledge_base_id,
        alert_id=alert_id,
        entity_id="claim:c1",
        entity_type="claim",
        severity=severity,
        status=status,
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, day, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, day, tzinfo=timezone.utc),
        evidence_pack_id=evidence_pack_id,
        tags=tags or [],
    )


def _store() -> InMemoryAlertHistoryWriter:
    store = InMemoryAlertHistoryWriter()
    store.write_alerts(
        [
            _record("a-1", knowledge_base_id="kb-1", day=16),
            _record("a-2", knowledge_base_id="kb-2", day=17),
            _record("a-3", knowledge_base_id="kb-1", day=18, status="resolved"),
        ]
    )
    return store


def test_returns_every_alert_without_a_knowledge_base_predicate() -> None:
    records, total = _store().list_alerts(limit=10, offset=0)

    assert total == 3
    assert {record.alert_id for record in records} == {"a-1", "a-2", "a-3"}


def test_restricts_results_to_one_knowledge_base() -> None:
    records, total = _store().list_alerts(knowledge_base_id="kb-1", limit=10, offset=0)

    assert total == 2
    assert {record.alert_id for record in records} == {"a-1", "a-3"}


def test_total_reflects_the_knowledge_base_predicate_not_the_whole_table() -> None:
    # The total drives pagination; if it counted every KB the caller would
    # page past the end of its own result set.
    _, total = _store().list_alerts(knowledge_base_id="kb-2", limit=1, offset=0)

    assert total == 1


def test_combines_the_knowledge_base_and_status_predicates() -> None:
    records, total = _store().list_alerts(
        knowledge_base_id="kb-1", statuses=["open"], limit=10, offset=0
    )

    assert total == 1
    assert records[0].alert_id == "a-1"


def test_paginates_within_the_scoped_result_set() -> None:
    records, total = _store().list_alerts(knowledge_base_id="kb-1", limit=1, offset=1)

    assert total == 2
    # Ordered created_at DESC, so a-3 (18th) leads and a-1 (16th) is second.
    assert [record.alert_id for record in records] == ["a-1"]


def test_returns_nothing_for_an_unknown_knowledge_base() -> None:
    records, total = _store().list_alerts(knowledge_base_id="kb-ghost", limit=10, offset=0)

    assert (records, total) == ([], 0)


def test_combines_queue_predicates_and_filtered_total() -> None:
    store = InMemoryAlertHistoryWriter()
    store.write_alerts(
        [
            _record(
                "a-critical-billing",
                severity="critical",
                evidence_pack_id="evidence-1",
                tags=["billing"],
                day=18,
            ),
            _record(
                "a-critical-network",
                severity="critical",
                evidence_pack_id="evidence-2",
                tags=["network"],
                day=18,
            ),
            _record(
                "a-stale-billing",
                severity="critical",
                evidence_pack_id="evidence-3",
                tags=["billing"],
                day=1,
            ),
        ]
    )

    records, total = store.list_alerts(
        statuses=["open"],
        severities=["critical"],
        tags=["billing"],
        created_from="2026-05-18",
        created_to="2026-05-18",
        evidence="with_evidence",
        freshness="stale",
        limit=1,
        offset=0,
    )

    assert total == 1
    assert [record.alert_id for record in records] == ["a-critical-billing"]
