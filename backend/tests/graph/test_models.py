"""Tests for graph service-boundary models."""

from __future__ import annotations

import pytest

from graph.models import GraphMetrics, SubgraphResult
from graph.service_models import GraphBuildTask
from shared.types import Entity, Relationship


def test_subgraph_result_defaults_to_empty_lists() -> None:
    result = SubgraphResult()

    assert result.entities == []
    assert result.relationships == []


def test_subgraph_result_accepts_entities_and_relationships() -> None:
    result = SubgraphResult(
        entities=[Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
        relationships=[
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            )
        ],
    )

    assert result.entities[0].id == "entity-1"
    assert result.relationships[0].id == "relationship-1"


def test_graph_metrics_accepts_non_negative_values() -> None:
    metrics = GraphMetrics(entity_count=10, relationship_count=12, avg_degree=2.4)

    assert metrics.entity_count == 10
    assert metrics.relationship_count == 12
    assert metrics.avg_degree == 2.4


def test_graph_metrics_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        GraphMetrics(entity_count=-1, relationship_count=2, avg_degree=1.0)

    with pytest.raises(ValueError):
        GraphMetrics(entity_count=1, relationship_count=-2, avg_degree=1.0)

    with pytest.raises(ValueError):
        GraphMetrics(entity_count=1, relationship_count=2, avg_degree=-0.1)


def test_graph_build_task_accepts_valid_payload() -> None:
    task = GraphBuildTask(
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        extraction_result_id="extract-1",
        validation_report_id="validate-1",
        validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
        entities=[Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
    )

    assert task.knowledge_base_id == "kb-1"
    assert task.correlation_id
    assert task.entities[0].id == "entity-1"


def test_graph_build_task_rejects_blank_validation_storage_key() -> None:
    with pytest.raises(ValueError, match="validation_storage_key"):
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="  ",
        )