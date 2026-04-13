"""Service-boundary models for graph build requests and receipts."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from shared.types import Entity, Relationship


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GraphBuildTask(BaseModel):
    """A worker-consumable graph build task derived from validated runtime objects."""

    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    validation_storage_key: str
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

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
    created_at: datetime = Field(default_factory=_utc_now)