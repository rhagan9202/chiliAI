"""Graph-layer transport models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GraphUpsertResult(BaseModel):
    """Summary of one graph upsert operation."""

    knowledge_base_id: str
    validation_report_id: str
    extraction_result_id: str
    upserted_entity_ids: list[str] = Field(default_factory=list)
    upserted_relationship_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)