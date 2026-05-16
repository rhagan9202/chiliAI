"""Tests for events.types — event model construction and validation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from events.types import (
    DocumentReference,
    DocumentsParsedEvent,
    KnowledgeBaseCreatedEvent,
    ParsedDocumentReference,
)


class TestEventBase:
    def test_occurred_at_default(self) -> None:
        event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo == timezone.utc

    def test_envelope_defaults(self) -> None:
        event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")

        assert UUID(event.correlation_id).version == 4
        assert event.source is None
        assert event.schema_version == 1

    def test_event_type_literal(self) -> None:
        event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")
        assert event.event_type == "kb.create"


class TestDocumentReference:
    def test_round_trip(self) -> None:
        ref = DocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            filename="test.csv",
        )
        data = ref.model_dump()
        restored = DocumentReference.model_validate(data)
        assert restored == ref


class TestDocumentsParsedEvent:
    def test_construction(self) -> None:
        ref = ParsedDocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="pd-1",
            parser_name="csv",
        )
        event = DocumentsParsedEvent(documents=[ref])
        assert event.event_type == "documents.parsed"
        assert len(event.documents) == 1

    def test_serialization(self) -> None:
        ref = ParsedDocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="pd-1",
            parser_name="csv",
        )
        event = DocumentsParsedEvent(
            correlation_id="corr-123",
            source="chili-worker",
            schema_version=2,
            documents=[ref],
        )
        data = event.model_dump()
        restored = DocumentsParsedEvent.model_validate(data)
        assert restored.event_type == event.event_type
        assert len(restored.documents) == len(event.documents)
        assert restored.correlation_id == "corr-123"
        assert restored.source == "chili-worker"
        assert restored.schema_version == 2


def test_risk_scored_reference_carries_factors() -> None:
    from events.types import RiskFactorReference, RiskScoredReference

    reference = RiskScoredReference(
        knowledge_base_id="kb-1",
        request_id="req-1",
        entity_id="claim:c1",
        overall_score=0.8,
        risk_level="high",
        factor_count=1,
        factors=[
            RiskFactorReference(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=0.8,
            )
        ],
    )
    assert reference.factors[0].factor_name == "anomaly"


def test_risk_scored_reference_factors_default_empty() -> None:
    from events.types import RiskScoredReference

    reference = RiskScoredReference(
        knowledge_base_id="kb-1",
        request_id="req-1",
        entity_id="claim:c1",
        overall_score=0.8,
        risk_level="high",
        factor_count=0,
    )
    assert reference.factors == []


def test_alert_created_reference_new_fields_default() -> None:
    from events.types import AlertCreatedReference

    reference = AlertCreatedReference(
        knowledge_base_id="kb-1",
        alert_id="a-1",
        entity_id="claim:c1",
        severity="high",
    )
    assert reference.entity_type == ""
    assert reference.status == "open"
    assert reference.title == ""
    assert reference.reasoning == ""
    assert reference.metric_name == ""
