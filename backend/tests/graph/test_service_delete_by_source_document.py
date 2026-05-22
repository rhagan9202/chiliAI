from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService
from shared.provenance import SOURCE_DOCUMENT_ID_KEY, SOURCE_KIND_DOCUMENT, SOURCE_KIND_KEY
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


def test_service_delegates_to_repository() -> None:
    repo = InMemoryGraphRepository()
    service = GraphService(repo, object_store=InMemoryObjectStore(), event_bus=InMemoryEventBus())

    with repo.transaction("kb-1"):
        repo.upsert_entities("kb-1", [
            Entity(
                id="e1",
                type="provider",
                properties={"npi": "1"},
                metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"},
            ),
        ])

    report = service.delete_by_source_document("kb-1", "doc-A")
    assert report.entity_count == 1
    assert repo.count_entities("kb-1") == 0
