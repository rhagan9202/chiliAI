from __future__ import annotations

from datetime import datetime, timezone

import pytest

from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowStepDefinition,
)


def _definition(
    definition_id: str,
    version: str,
    *,
    knowledge_base_id: str = "kb-1",
    name: str | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=definition_id,
        knowledge_base_id=knowledge_base_id,
        domain_name="medicare_fraud",
        name=name or definition_id,
        version=version,
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            )
        ],
        created_by="analyst-1",
        created_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
    )


def test_save_and_get_return_deep_copies() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    original = _definition("definition-a", "v1")

    saved = repository.save_definition(original)
    saved.steps[0].label = "mutated saved copy"
    original.steps[0].label = "mutated original"

    loaded = repository.get_definition("kb-1", "definition-a", "v1")
    assert loaded is not None
    loaded.steps[0].label = "mutated loaded copy"

    fresh = repository.get_definition("kb-1", "definition-a", "v1")
    assert fresh is not None
    assert fresh.steps[0].label == "Ask RAG"


def test_save_duplicate_definition_snapshot_raises() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    repository.save_definition(_definition("definition-a", "v1"))

    with pytest.raises(ValueError, match="already exists"):
        repository.save_definition(_definition("definition-a", "v1"))


def test_list_filters_sorts_and_paginates() -> None:
    repository = InMemoryWorkflowDefinitionRepository(
        [
            _definition("definition-b", "v2"),
            _definition("definition-a", "v2"),
            _definition("definition-a", "v1"),
            _definition("definition-c", "v1", knowledge_base_id="kb-2"),
        ]
    )

    page = repository.list_definitions(knowledge_base_id="kb-1", limit=2, offset=1)

    assert [(item.definition_id, item.version) for item in page.items] == [
        ("definition-a", "v2"),
        ("definition-b", "v2"),
    ]
    assert page.total_items == 3
    assert page.limit == 2
    assert page.offset == 1


def test_update_definition_replaces_existing_snapshot() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    repository.save_definition(_definition("definition-a", "v1", name="Original"))
    replacement = _definition("definition-a", "v1", name="Replacement")
    replacement.steps[0].label = "Replacement step"

    updated = repository.update_definition(replacement)
    updated.name = "mutated returned copy"

    fresh = repository.get_definition("kb-1", "definition-a", "v1")
    assert fresh is not None
    assert fresh.name == "Replacement"
    assert fresh.steps[0].label == "Replacement step"


def test_update_missing_definition_snapshot_raises() -> None:
    repository = InMemoryWorkflowDefinitionRepository()

    with pytest.raises(KeyError):
        repository.update_definition(_definition("missing", "v1"))
