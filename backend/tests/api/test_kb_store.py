"""Tests for coverage gaps in the knowledgebases adapters.

Covers uncovered branches in both InMemoryKnowledgeBaseRepository and
ObjectStoreKnowledgeBaseRepository that were missed in the inaugural pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from knowledgebases import (
    DocumentRecord,
    InMemoryKnowledgeBaseRepository,
    ObjectStoreKnowledgeBaseRepository,
)
from knowledgebases.snapshots import KnowledgeBaseStoreSnapshot
from shared.types import KnowledgeBase
from storage.adapters.in_memory import InMemoryObjectStore


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _kb(kb_id: str = "kb-1", *, name: str = "Test KB") -> KnowledgeBase:
    return KnowledgeBase(
        id=kb_id,
        name=name,
        description="Test knowledge base",
        document_count=0,
        entity_count=0,
        relationship_count=0,
        status="active",  # type: ignore[arg-type]
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _doc(
    doc_id: str = "doc-1",
    kb_id: str = "kb-1",
    *,
    status: str = "registered",
) -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=f"{doc_id}.txt",
        status=status,
    )


# ---------------------------------------------------------------------------
# InMemoryKnowledgeBaseRepository — missed branches
# ---------------------------------------------------------------------------


def test_in_memory_create_duplicate_id_raises() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    repo.create(_kb())

    with pytest.raises(ValueError, match="already exists"):
        repo.create(_kb())


def test_in_memory_update_summary_returns_none_for_missing_kb() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    assert repo.update_summary("no-such-kb", status="ready") is None


def test_in_memory_update_summary_no_op_when_nothing_changes() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    kb = repo.create(_kb())

    # Passing the same values as the current state should return the existing object.
    result = repo.update_summary(
        "kb-1",
        status=kb.status,
        entity_count=kb.entity_count,
        relationship_count=kb.relationship_count,
    )

    assert result == kb


def test_in_memory_delete_returns_false_for_missing_id() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    assert repo.delete("no-such-kb") is False


def test_in_memory_add_document_raises_for_unknown_kb() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    with pytest.raises(ValueError, match="does not exist"):
        repo.add_document(_doc(kb_id="ghost-kb"))


def test_in_memory_add_document_raises_for_duplicate_document_id() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    repo.create(_kb())
    repo.add_document(_doc())

    with pytest.raises(ValueError, match="already exists"):
        repo.add_document(_doc())


def test_in_memory_get_document_returns_none_for_unknown_kb() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    assert repo.get_document("no-kb", "doc-1") is None


def test_in_memory_update_document_status_returns_none_for_unknown_kb() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    assert repo.update_document_status("no-kb", "doc-1", "processed") is None


def test_in_memory_update_document_status_returns_none_for_unknown_doc() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    repo.create(_kb())

    assert repo.update_document_status("kb-1", "no-doc", "processed") is None


def test_in_memory_update_document_status_no_op_when_status_unchanged() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    repo.create(_kb())
    repo.add_document(_doc(status="processed"))

    result = repo.update_document_status("kb-1", "doc-1", "processed")

    assert result is not None
    assert result.status == "processed"


def test_in_memory_delete_document_returns_false_for_missing_doc() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    repo.create(_kb())

    assert repo.delete_document("kb-1", "no-doc") is False


def test_in_memory_delete_document_returns_false_for_unknown_kb() -> None:
    repo = InMemoryKnowledgeBaseRepository()

    assert repo.delete_document("no-kb", "doc-1") is False


# ---------------------------------------------------------------------------
# ObjectStoreKnowledgeBaseRepository — missed branches
# ---------------------------------------------------------------------------


def _object_store_repo(
    storage_key: str = "test/metadata.json",
) -> tuple[ObjectStoreKnowledgeBaseRepository, InMemoryObjectStore]:
    store = InMemoryObjectStore()
    repo = ObjectStoreKnowledgeBaseRepository(store, storage_key=storage_key)
    return repo, store


def test_object_store_create_stores_and_retrieves_kb() -> None:
    repo, _ = _object_store_repo()
    kb = _kb()

    created = repo.create(kb)
    retrieved = repo.get("kb-1")

    assert created.id == "kb-1"
    assert retrieved is not None
    assert retrieved.id == "kb-1"


def test_object_store_create_duplicate_id_raises() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())

    with pytest.raises(ValueError, match="already exists"):
        repo.create(_kb())


def test_object_store_get_returns_none_for_missing_kb() -> None:
    repo, _ = _object_store_repo()

    assert repo.get("no-such-kb") is None


def test_object_store_list_returns_all_kbs() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb("kb-1"))
    repo.create(_kb("kb-2"))

    items, total = repo.list(limit=10, offset=0)

    assert total == 2
    assert [kb.id for kb in items] == ["kb-1", "kb-2"]


def test_object_store_update_summary_no_op_when_nothing_changes() -> None:
    repo, _ = _object_store_repo()
    kb = repo.create(_kb())

    result = repo.update_summary(
        "kb-1",
        status=kb.status,
        entity_count=kb.entity_count,
        relationship_count=kb.relationship_count,
    )

    assert result is not None
    assert result.id == "kb-1"


def test_object_store_update_summary_returns_none_for_missing_kb() -> None:
    repo, _ = _object_store_repo()

    result = repo.update_summary("no-such-kb", status="ready")

    assert result is None


def test_object_store_update_summary_persists_change() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())

    updated = repo.update_summary("kb-1", status="ready", entity_count=5)

    assert updated is not None
    assert updated.status == "ready"
    assert updated.entity_count == 5


def test_object_store_delete_returns_false_for_missing_kb() -> None:
    repo, _ = _object_store_repo()

    assert repo.delete("no-such-kb") is False


def test_object_store_delete_removes_kb() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())

    result = repo.delete("kb-1")

    assert result is True
    assert repo.get("kb-1") is None


def test_object_store_add_document_raises_for_unknown_kb() -> None:
    repo, _ = _object_store_repo()

    with pytest.raises(ValueError, match="does not exist"):
        repo.add_document(_doc(kb_id="ghost-kb"))


def test_object_store_add_document_raises_for_duplicate_doc_id() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc())

    with pytest.raises(ValueError, match="already exists"):
        repo.add_document(_doc())


def test_object_store_get_document_returns_none_for_unknown_kb() -> None:
    repo, _ = _object_store_repo()

    assert repo.get_document("no-kb", "doc-1") is None


def test_object_store_get_document_returns_doc() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc())

    result = repo.get_document("kb-1", "doc-1")

    assert result is not None
    assert result.id == "doc-1"


def test_object_store_list_documents_returns_ordered_docs() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc("doc-1"))
    repo.add_document(_doc("doc-2"))

    items, total = repo.list_documents("kb-1", limit=10, offset=0)

    assert total == 2
    assert [d.id for d in items] == ["doc-1", "doc-2"]


def test_object_store_update_document_status_returns_none_for_unknown_kb() -> None:
    repo, _ = _object_store_repo()

    assert repo.update_document_status("no-kb", "doc-1", "processed") is None


def test_object_store_update_document_status_returns_none_for_unknown_doc() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())

    assert repo.update_document_status("kb-1", "no-doc", "processed") is None


def test_object_store_update_document_status_no_op_when_same_status() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc(status="processed"))

    result = repo.update_document_status("kb-1", "doc-1", "processed")

    assert result is not None
    assert result.status == "processed"


def test_object_store_update_document_status_persists_change() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc())

    updated = repo.update_document_status("kb-1", "doc-1", "processed")

    assert updated is not None
    assert updated.status == "processed"
    # Verify persistence: reload from store
    reloaded = repo.get_document("kb-1", "doc-1")
    assert reloaded is not None
    assert reloaded.status == "processed"


def test_object_store_delete_document_returns_false_for_unknown_kb() -> None:
    repo, _ = _object_store_repo()

    assert repo.delete_document("no-kb", "doc-1") is False


def test_object_store_delete_document_returns_false_for_unknown_doc() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())

    assert repo.delete_document("kb-1", "no-doc") is False


def test_object_store_delete_document_removes_doc() -> None:
    repo, _ = _object_store_repo()
    repo.create(_kb())
    repo.add_document(_doc())

    result = repo.delete_document("kb-1", "doc-1")

    assert result is True
    assert repo.get_document("kb-1", "doc-1") is None


def test_object_store_load_snapshot_returns_empty_when_key_missing() -> None:
    """_load_snapshot returns a fresh snapshot when the object store has no data."""
    repo, _ = _object_store_repo()

    # No data written — should return an empty snapshot (implicitly tested by list)
    items, total = repo.list(limit=10, offset=0)

    assert total == 0
    assert items == []


# ---------------------------------------------------------------------------
# Defensive guard paths in _sync_document_count
# ---------------------------------------------------------------------------


def test_in_memory_sync_document_count_is_noop_when_kb_missing() -> None:
    """_sync_document_count silently returns when the KB no longer exists.

    This defensive guard (line 239) is reached by calling the private method
    directly with an ID that is not tracked.
    """
    repo = InMemoryKnowledgeBaseRepository()
    # Call the private method via getattr to satisfy pyright's private-access rule.
    sync_fn = getattr(repo, "_sync_document_count")
    # Should not raise even though "phantom-kb" is not registered.
    sync_fn("phantom-kb")


def test_object_store_sync_document_count_is_noop_when_kb_missing() -> None:
    """ObjectStoreKnowledgeBaseRepository._sync_document_count is a no-op when
    the KB is not in the snapshot (line 429 defensive guard).
    """
    snapshot = KnowledgeBaseStoreSnapshot()
    # Call the static method with an ID that has no matching KB entry.
    sync_fn = getattr(ObjectStoreKnowledgeBaseRepository, "_sync_document_count")
    sync_fn(snapshot, "phantom-kb")
    # No exception and snapshot remains unchanged.
    assert snapshot.knowledge_bases == {}
