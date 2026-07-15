"""Monotonic-transition semantics of the in-memory document status store."""

from __future__ import annotations

from datetime import UTC, datetime

from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
)

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 1, 12, 1, tzinfo=UTC)
T2 = datetime(2026, 7, 1, 12, 2, tzinfo=UTC)


def _transition(
    status: IngestionStatus,
    *,
    doc: str = "doc-1",
    occurred_at: datetime = T0,
    error: str | None = None,
    dropped_entities: int | None = None,
    dropped_relationships: int | None = None,
    reasons: list[str] | None = None,
) -> DocumentStatusTransition:
    return DocumentStatusTransition(
        knowledge_base_id="kb-1",
        source_document_id=doc,
        status=status,
        error_message=error,
        dropped_entity_count=dropped_entities,
        dropped_relationship_count=dropped_relationships,
        sample_reasons=reasons,
        occurred_at=occurred_at,
    )


def test_satisfies_protocol() -> None:
    assert isinstance(InMemorySourceDocumentStatusStore(), SourceDocumentStatusStore)


def test_apply_inserts_first_transition() -> None:
    store = InMemorySourceDocumentStatusStore()
    record = store.apply(_transition(IngestionStatus.PENDING))
    assert record.current_status == IngestionStatus.PENDING
    assert record.status_rank == STATUS_RANK[IngestionStatus.PENDING]
    assert record.first_event_at == T0
    assert record.updated_at == T0
    assert record.dropped_entity_count == 0
    assert record.sample_reasons == []


def test_forward_transition_advances_status() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PENDING, occurred_at=T0))
    record = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    assert record.current_status == IngestionStatus.PARSED
    assert record.first_event_at == T0
    assert record.updated_at == T1


def test_stale_transition_after_failed_is_ignored() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="parse exploded")
    )
    record = store.apply(
        _transition(IngestionStatus.PARSING, occurred_at=T2, error="stale noise")
    )
    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "parse exploded"
    assert record.status_rank == STATUS_RANK[IngestionStatus.FAILED]


def test_failed_redelivery_refreshes_last_error() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="first failure")
    )
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T2, error="second failure")
    )
    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "second failure"
    assert record.updated_at == T2


def test_redelivery_is_idempotent() -> None:
    store = InMemorySourceDocumentStatusStore()
    first = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    replay = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    assert replay == first


def test_warning_counts_overwrite_without_status_regression() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            dropped_relationships=2,
            reasons=["entity cand-1: unknown type"],
        )
    )
    # A later transition without counts leaves them untouched.
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T2, error="late failure")
    )
    assert record.current_status == IngestionStatus.FAILED
    assert record.dropped_entity_count == 4
    assert record.dropped_relationship_count == 2
    assert record.sample_reasons == ["entity cand-1: unknown type"]
    assert record.last_error == "late failure"


def test_get_many_returns_only_known_documents() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))
    store.apply(_transition(IngestionStatus.FAILED, doc="doc-2", error="x"))
    found = store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1", "doc-2", "doc-3"]
    )
    assert set(found) == {"doc-1", "doc-2"}
    assert found["doc-2"].current_status == IngestionStatus.FAILED


def test_list_filters_by_status_and_paginates_newest_first() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-2", occurred_at=T1, error="x")
    )
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-3", occurred_at=T2, error="y")
    )

    all_items, all_total = store.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert all_total == 3
    assert [item.source_document_id for item in all_items] == [
        "doc-3", "doc-2", "doc-1"
    ]

    failed, failed_total = store.list(
        knowledge_base_id="kb-1", limit=1, offset=1, status=IngestionStatus.FAILED
    )
    assert failed_total == 2
    assert [item.source_document_id for item in failed] == ["doc-2"]

    other_kb, other_total = store.list(knowledge_base_id="kb-9", limit=10, offset=0)
    assert other_kb == [] and other_total == 0


def test_delete_by_kb_removes_all_rows_for_kb() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-2"))
    assert store.delete_by_kb("kb-1") == 2
    assert store.delete_by_kb("kb-1") == 0
    assert store.list(knowledge_base_id="kb-1", limit=10, offset=0) == ([], 0)


def test_delete_by_document_removes_only_that_row() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-2"))

    assert store.delete_by_document("kb-1", "doc-1") is True

    remaining, total = store.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1
    assert [item.source_document_id for item in remaining] == ["doc-2"]


def test_delete_by_document_returns_false_for_missing_row() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))

    assert store.delete_by_document("kb-1", "doc-missing") is False
    assert store.delete_by_document("kb-missing", "doc-1") is False
