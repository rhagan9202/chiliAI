"""Tests for graph service-boundary models."""

from __future__ import annotations

import pytest

from graph.service_models import GraphBuildTask
from shared.types import Entity


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