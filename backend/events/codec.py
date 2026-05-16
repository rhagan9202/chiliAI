"""Serialization helpers for typed backend events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from events.types import (
    AgentWorkflowStartedEvent,
    AlertCreatedEvent,
    AlertsCreatedEvent,
    AnalysisFailedEvent,
    AnyEvent,
    ClaimsIngestedEvent,
    ClaimsReceivedEvent,
    EmbeddingsCompleteEvent,
    EmbeddingsGeneratedEvent,
    ExplainabilityGeneratedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    GnnAnalyzedEvent,
    GraphUpdatedEvent,
    DocumentsChunkedEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EventBase,
    KnowledgeBaseCreatedEvent,
    KnowledgeBaseDeletedEvent,
    KnowledgeBaseReadyEvent,
    LlmCompletedEvent,
    PipelineProgressEvent,
    RagCompletedEvent,
    RecordsIngestedEvent,
    RiskScoredEvent,
    TimeseriesAnalyzedEvent,
    VectorsIndexedEvent,
)


EVENT_TYPE_REGISTRY: dict[str, type[EventBase]] = {
    # TODO(production): Replace manual registry with auto-discovery from EventBase
    # subclasses (use __init_subclass__ or a class decorator) so new event types
    # are registered automatically. Add schema_version field to serialized payloads
    # for backward-compatible deserialization across deployments.
    "agent.workflow.started": AgentWorkflowStartedEvent,
    "alert.created": AlertCreatedEvent,
    "alerts.created": AlertsCreatedEvent,
    "analysis.failed": AnalysisFailedEvent,
    "pipeline.progress": PipelineProgressEvent,
    "kb.create": KnowledgeBaseCreatedEvent,
    "kb.delete": KnowledgeBaseDeletedEvent,
    "documents.uploaded": DocumentsUploadedEvent,
    "documents.parsed": DocumentsParsedEvent,
    "documents.chunked": DocumentsChunkedEvent,
    "entities.extracted": EntitiesExtractedEvent,
    "entities.validated": EntitiesValidatedEvent,
    "graph.updated": GraphUpdatedEvent,
    "embeddings.complete": EmbeddingsCompleteEvent,
    "vectors.indexed": VectorsIndexedEvent,
    "kb.ready": KnowledgeBaseReadyEvent,
    "llm.completed": LlmCompletedEvent,
    "embeddings.generated": EmbeddingsGeneratedEvent,
    "rag.completed": RagCompletedEvent,
    "timeseries.analyzed": TimeseriesAnalyzedEvent,
    "gnn.analyzed": GnnAnalyzedEvent,
    "risk.scored": RiskScoredEvent,
    "explainability.generated": ExplainabilityGeneratedEvent,
    "documents.failed": DocumentsFailedEvent,
    "claims.received": ClaimsReceivedEvent,
    "claims.ingested": ClaimsIngestedEvent,
    "records.ingested": RecordsIngestedEvent,
}


def encode_event(event: AnyEvent) -> dict[str, str]:
    """Serialize a typed event for transport over Redis Streams."""
    return {
        "event_type": event.event_type,
        "event_body": event.model_dump_json(),
    }


def decode_event(payload: Mapping[str, str] | Mapping[bytes, bytes]) -> AnyEvent:
    """Deserialize a typed event from transport payload fields."""
    normalized = {_decode_key(key): _decode_value(value) for key, value in payload.items()}
    event_type = normalized.get("event_type")
    if event_type is None:
        raise ValueError("Event payload is missing 'event_type'.")

    event_body = normalized.get("event_body")
    if event_body is None:
        raise ValueError("Event payload is missing 'event_body'.")

    event_model = EVENT_TYPE_REGISTRY.get(event_type)
    if event_model is None:
        raise ValueError(f"Unsupported event type: {event_type}")
    body = json.loads(event_body)
    if not isinstance(body, dict):
        raise ValueError("Event body must be a JSON object.")
    body_mapping = cast(dict[str, object], body)
    body_event_type = body_mapping.get("event_type")
    if body_event_type != event_type:
        raise ValueError(
            f"Transport event_type '{event_type}' does not match body event_type "
            f"'{body_event_type}'."
        )
    return cast(AnyEvent, event_model.model_validate(body_mapping))


def _decode_key(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_value(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


__all__ = [
    "EVENT_TYPE_REGISTRY",
    "decode_event",
    "encode_event",
]
