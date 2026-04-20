"""Service-boundary models for graph build requests and receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from graph.models import GraphMetrics
from shared.types import Entity, Relationship
from shared.utils import generate_id, utc_now


def _empty_entities() -> list[Entity]:
    return []


def _empty_relationships() -> list[Relationship]:
    return []


class GraphBuildTask(BaseModel):
    """A worker-consumable graph build task derived from validated runtime objects."""

    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    validation_storage_key: str
    correlation_id: str = Field(default_factory=generate_id)
    entities: list[Entity] = Field(default_factory=_empty_entities)
    relationships: list[Relationship] = Field(default_factory=_empty_relationships)

    @model_validator(mode="after")
    def _ensure_graph_payload(self) -> GraphBuildTask:
        if self.validation_storage_key.strip() == "":
            raise ValueError("GraphBuildTask requires a non-empty validation_storage_key.")
        return self


class GraphBuildReceipt(BaseModel):
    """Receipt returned after a graph build task is persisted and published."""

    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    validation_storage_key: str
    graph_update_storage_key: str
    upserted_entity_count: int = Field(ge=0)
    upserted_relationship_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class NeighborhoodQuery(BaseModel):
    """Query parameters for neighborhood traversal requests."""

    knowledge_base_id: str
    entity_id: str
    depth: int = Field(ge=0, le=5)
    direction: Literal["in", "out", "both"] = "both"


class EntitySearchQuery(BaseModel):
    """Query parameters for graph entity search requests."""

    knowledge_base_id: str
    query: str
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class GraphMetricsResult(BaseModel):
    """Response model wrapping aggregate graph metrics."""

    knowledge_base_id: str
    metrics: GraphMetrics
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "GraphBuildReceipt",
    "GraphBuildTask",
    "EntitySearchQuery",
    "GraphMetricsResult",
    "NeighborhoodQuery",
]