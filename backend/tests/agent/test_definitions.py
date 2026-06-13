"""Tests for workflow definition registry models."""

from __future__ import annotations

import pytest

from agent.definitions import (
    WorkflowDefinition,
    WorkflowDefinitionRegistry,
    WorkflowStepDef,
    default_workflow_registry,
)


def test_registry_resolves_default_step_plan_and_event_mapping() -> None:
    registry = WorkflowDefinitionRegistry(
        definitions=(
            WorkflowDefinition(
                definition_id="default",
                steps=(
                    WorkflowStepDef(name="parse"),
                    WorkflowStepDef(name="chunk"),
                ),
                event_step_mapping={"documents.uploaded": "parse"},
            ),
        ),
        default_definition_id="default",
    )

    assert registry.default_step_names() == ["parse", "chunk"]
    assert registry.step_for_event_type("documents.uploaded") == "parse"
    assert registry.step_for_event_type("missing.event") is None
    assert registry.has_step("chunk") is True
    assert registry.has_step("missing") is False


def test_registry_rejects_event_mapping_to_unknown_step() -> None:
    with pytest.raises(ValueError, match="unknown step"):
        WorkflowDefinitionRegistry(
            definitions=(
                WorkflowDefinition(
                    definition_id="default",
                    steps=(WorkflowStepDef(name="parse"),),
                    event_step_mapping={"documents.chunked": "chunk"},
                ),
            ),
            default_definition_id="default",
        )


def test_default_registry_preserves_current_step_sequence_and_event_mapping() -> None:
    registry = default_workflow_registry()

    assert registry.default_step_names() == [
        "parse",
        "chunk",
        "extract",
        "validate",
        "graph_build",
        "embed",
        "vector_index",
        "ready",
        "monitoring",
    ]
    assert {
        event_type: registry.step_for_event_type(event_type)
        for event_type in [
            "documents.uploaded",
            "documents.parsed",
            "documents.failed",
            "records.ingested",
            "documents.chunked",
            "entities.extracted",
            "entities.validated",
            "graph.updated",
            "embeddings.complete",
            "vectors.indexed",
            "kb.ready",
            "risk.scored",
        ]
    } == {
        "documents.uploaded": "parse",
        "documents.parsed": "chunk",
        "documents.failed": "parse",
        "records.ingested": "records_ingest",
        "documents.chunked": "extract",
        "entities.extracted": "validate",
        "entities.validated": "graph_build",
        "graph.updated": "embed",
        "embeddings.complete": "vector_index",
        "vectors.indexed": "ready",
        "kb.ready": "ready",
        "risk.scored": "monitoring",
    }
