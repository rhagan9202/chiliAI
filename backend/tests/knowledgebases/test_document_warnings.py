"""Repository contract tests for per-document warning persistence."""

from __future__ import annotations

import pytest

from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _repositories() -> list[KnowledgeBaseRepository]:
    return [
        InMemoryKnowledgeBaseRepository(),
        ObjectStoreKnowledgeBaseRepository(InMemoryObjectStore()),
    ]


def _register(repository: KnowledgeBaseRepository) -> DocumentRecord:
    repository.create(
        KnowledgeBase(id="kb-1", name="KB", description="", created_at=utc_now())
    )
    return repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="claims.csv",
            content_type="text/csv",
        )
    )


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_record_document_warnings_accumulates(repository: KnowledgeBaseRepository) -> None:
    _register(repository)

    first = repository.record_document_warnings(
        "kb-1", "doc-1", additional_count=2, reasons=["csv.ragged_row: row 1"]
    )
    assert first is not None
    assert first.warning_count == 2
    assert first.warning_reasons == ["csv.ragged_row: row 1"]

    second = repository.record_document_warnings(
        "kb-1", "doc-1", additional_count=1, reasons=["entity claim-1: dropped"]
    )
    assert second is not None
    assert second.warning_count == 3
    assert second.warning_reasons == [
        "csv.ragged_row: row 1",
        "entity claim-1: dropped",
    ]

    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.warning_count == 3


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_record_document_warnings_caps_reasons_at_ten(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    updated = repository.record_document_warnings(
        "kb-1",
        "doc-1",
        additional_count=12,
        reasons=[f"reason-{index}" for index in range(12)],
    )
    assert updated is not None
    assert updated.warning_count == 12
    assert len(updated.warning_reasons) == 10


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_record_document_warnings_unknown_document_returns_none(
    repository: KnowledgeBaseRepository,
) -> None:
    assert (
        repository.record_document_warnings(
            "kb-1", "missing", additional_count=1, reasons=[]
        )
        is None
    )


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_document_warnings_is_absolute_not_additive(
    repository: KnowledgeBaseRepository,
) -> None:
    """Replaying the same set (retry, at-least-once redelivery) must converge."""
    _register(repository)

    repository.set_document_warnings(
        "kb-1", "doc-1", count=2, reasons=["csv.ragged_row: row 1"]
    )
    repository.set_document_warnings(
        "kb-1", "doc-1", count=2, reasons=["csv.ragged_row: row 1"]
    )

    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.warning_count == 2
    assert stored.warning_reasons == ["csv.ragged_row: row 1"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_document_warnings_overwrites_a_prior_value(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    repository.set_document_warnings(
        "kb-1", "doc-1", count=5, reasons=["reason-a", "reason-b"]
    )
    repository.set_document_warnings("kb-1", "doc-1", count=1, reasons=["reason-c"])

    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.warning_count == 1
    assert stored.warning_reasons == ["reason-c"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_document_warnings_caps_reasons_at_ten(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    repository.set_document_warnings(
        "kb-1", "doc-1", count=12, reasons=[f"reason-{index}" for index in range(12)]
    )

    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.warning_count == 12
    assert len(stored.warning_reasons) == 10


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_document_warnings_empty_reasons_clears_prior_reasons(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    repository.set_document_warnings("kb-1", "doc-1", count=3, reasons=["stale reason"])
    repository.set_document_warnings("kb-1", "doc-1", count=0, reasons=[])

    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.warning_count == 0
    assert stored.warning_reasons == []


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_document_warnings_unknown_document_is_a_no_op(
    repository: KnowledgeBaseRepository,
) -> None:
    # Must not raise, and must not create a document as a side effect.
    repository.set_document_warnings("kb-1", "missing", count=1, reasons=[])

    assert repository.get_document("kb-1", "missing") is None
