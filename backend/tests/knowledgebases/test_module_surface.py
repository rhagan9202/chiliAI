"""Pin the public surface of the knowledgebases module.

These tests fail before knowledgebases/ exists (RED) and pass once the
module ships its declared `__all__` (GREEN). They prevent the module
surface from regressing as the implementation moves between adapters.
"""

from __future__ import annotations

import importlib


def test_knowledgebases_exposes_protocol_and_models() -> None:
    module = importlib.import_module("knowledgebases")

    assert getattr(module, "KnowledgeBaseRepository", None) is not None
    assert getattr(module, "DocumentRecord", None) is not None


def test_knowledgebases_exposes_in_memory_adapter() -> None:
    module = importlib.import_module("knowledgebases")
    repository_type = getattr(module, "InMemoryKnowledgeBaseRepository")

    instance = repository_type()
    items, total = instance.list(limit=10, offset=0)
    assert items == []
    assert total == 0


def test_knowledgebases_exposes_object_store_adapter() -> None:
    module = importlib.import_module("knowledgebases")

    assert getattr(module, "ObjectStoreKnowledgeBaseRepository", None) is not None
