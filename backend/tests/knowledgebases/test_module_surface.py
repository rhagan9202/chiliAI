"""Pin the public surface of the knowledgebases module.

These tests fail before knowledgebases/ exists (RED) and pass once the
module ships its declared `__all__` (GREEN). They prevent the module
surface from regressing as the implementation moves between adapters.
"""

from __future__ import annotations


def test_knowledgebases_exposes_protocol_and_models() -> None:
    from knowledgebases import DocumentRecord, KnowledgeBaseRepository

    assert KnowledgeBaseRepository is not None
    assert DocumentRecord is not None


def test_knowledgebases_exposes_in_memory_adapter() -> None:
    from knowledgebases import InMemoryKnowledgeBaseRepository

    instance = InMemoryKnowledgeBaseRepository()
    items, total = instance.list(limit=10, offset=0)
    assert items == []
    assert total == 0


def test_knowledgebases_exposes_object_store_adapter() -> None:
    from knowledgebases import ObjectStoreKnowledgeBaseRepository

    assert ObjectStoreKnowledgeBaseRepository is not None
