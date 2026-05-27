"""Recovery markers for ingestion writes that succeeded before event publication failed."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import generate_id, utc_now


class IngestionRecoveryMarker(BaseModel):
    marker_id: str = Field(default_factory=generate_id)
    knowledge_base_id: str
    source_document_id: str
    storage_key: str | None
    content_hash: str | None
    event_type: str
    failure_reason: str
    created_at: datetime = Field(default_factory=utc_now)


class InMemoryIngestionRecoveryStore:
    def __init__(self) -> None:
        self._markers: list[IngestionRecoveryMarker] = []

    def add_marker(self, marker: IngestionRecoveryMarker) -> None:
        self._markers.append(marker)

    def list_markers(self) -> list[IngestionRecoveryMarker]:
        return list(self._markers)


__all__ = ["IngestionRecoveryMarker", "InMemoryIngestionRecoveryStore"]
