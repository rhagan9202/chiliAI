"""Graph-layer transport models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.types import Entity, Relationship
from shared.utils import utc_now


def _empty_entities() -> list[Entity]:
    return []


def _empty_relationships() -> list[Relationship]:
    return []


class GraphUpsertResult(BaseModel):
    """Summary of one graph upsert operation."""

    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    validation_report_id: str
    extraction_result_id: str
    upserted_entity_ids: list[str] = Field(default_factory=list)
    upserted_relationship_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class SubgraphResult(BaseModel):
    """A graph neighborhood or filtered subgraph query result."""

    entities: list[Entity] = Field(default_factory=_empty_entities)
    relationships: list[Relationship] = Field(default_factory=_empty_relationships)


class GraphMetrics(BaseModel):
    """Aggregate graph metrics for one knowledge base."""

    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    avg_degree: float = Field(ge=0.0)


__all__ = [
    "GraphMetrics",
    "GraphUpsertResult",
    "SubgraphResult",
]