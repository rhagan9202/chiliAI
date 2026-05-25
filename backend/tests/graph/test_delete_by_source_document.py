"""Graph repository removes entities/relationships keyed by source_document_id."""

from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from shared.provenance import (
    SOURCE_DOCUMENT_ID_KEY,
    SOURCE_FEED_KEY,
    SOURCE_KIND_DOCUMENT,
    SOURCE_KIND_KEY,
    SOURCE_KIND_RECORD,
)
from shared.types import Entity, Relationship


def test_delete_by_source_document_removes_only_matching_provenance() -> None:
    repo = InMemoryGraphRepository()
    with repo.transaction("kb-1"):
        repo.upsert_entities("kb-1", [
            Entity(id="e1", type="provider", properties={"npi": "1"},
                   metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"}),
            Entity(id="e2", type="provider", properties={"npi": "2"},
                   metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-B"}),
            Entity(id="e3", type="provider", properties={"npi": "3"},
                   metadata={SOURCE_KIND_KEY: SOURCE_KIND_RECORD, SOURCE_FEED_KEY: "nppes_providers"}),
        ])
        repo.upsert_relationships("kb-1", [
            Relationship(id="r1", type="referred_by", source_id="e1", target_id="e2",
                         metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"}),
        ])

    deleted = repo.delete_by_source_document("kb-1", "doc-A")
    assert deleted.entity_count == 1
    assert deleted.relationship_count == 1
    assert repo.count_entities("kb-1") == 2
    assert repo.count_relationships("kb-1") == 0


def test_delete_by_source_document_returns_zero_for_unknown_kb() -> None:
    repo = InMemoryGraphRepository()
    deleted = repo.delete_by_source_document("nonexistent-kb", "doc-X")
    assert deleted.entity_count == 0
    assert deleted.relationship_count == 0


def test_delete_by_source_document_returns_zero_when_no_matching_doc() -> None:
    repo = InMemoryGraphRepository()
    with repo.transaction("kb-2"):
        repo.upsert_entities("kb-2", [
            Entity(id="e1", type="provider", properties={},
                   metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"}),
        ])
    deleted = repo.delete_by_source_document("kb-2", "doc-B")
    assert deleted.entity_count == 0
    assert deleted.relationship_count == 0
    assert repo.count_entities("kb-2") == 1


def test_delete_by_source_document_does_not_affect_other_kbs() -> None:
    repo = InMemoryGraphRepository()
    with repo.transaction("kb-1"):
        repo.upsert_entities("kb-1", [
            Entity(id="e1", type="provider", properties={},
                   metadata={SOURCE_DOCUMENT_ID_KEY: "doc-A"}),
        ])
    with repo.transaction("kb-2"):
        repo.upsert_entities("kb-2", [
            Entity(id="e1", type="provider", properties={},
                   metadata={SOURCE_DOCUMENT_ID_KEY: "doc-A"}),
        ])

    deleted = repo.delete_by_source_document("kb-1", "doc-A")
    assert deleted.entity_count == 1
    # kb-2 is untouched
    assert repo.count_entities("kb-2") == 1
