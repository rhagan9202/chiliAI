"""Tests for the graph-builder service."""

from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from graph.builder import create_graph_builder
from ingestion.models import ValidationReport
from shared.types import Entity, Relationship


def test_graph_builder_upserts_validated_objects() -> None:
    builder = create_graph_builder(InMemoryGraphRepository())

    result = builder.upsert_validation_report(
        "kb-1",
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(id="entity-1", type="claim", properties={"claim_id": "42"}),
                Entity(id="entity-2", type="provider", properties={"npi": "1234567890"}),
            ],
            valid_relationships=[
                Relationship(
                    id="relationship-1",
                    type="submitted_by",
                    source_id="entity-1",
                    target_id="entity-2",
                )
            ],
        ),
    )

    assert result.knowledge_base_id == "kb-1"
    assert result.validation_report_id == "validate-1"
    assert result.upserted_entity_ids == ["entity-1", "entity-2"]
    assert result.upserted_relationship_ids == ["relationship-1"]