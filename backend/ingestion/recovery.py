"""Recovery markers for ingestion writes that succeeded before event publication failed."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from shared.protocols import ObjectStoreProtocol
from shared.utils import generate_id, utc_now

_RECOVERY_PREFIX = "recovery/ingestion/"


class IngestionRecoveryMarker(BaseModel):
    marker_id: str = Field(default_factory=generate_id)
    knowledge_base_id: str
    source_document_id: str
    storage_key: str | None
    content_hash: str | None
    correlation_id: str
    event_type: str
    failure_reason: str
    created_at: datetime = Field(default_factory=utc_now)


@runtime_checkable
class IngestionRecoveryStore(Protocol):
    """Store recovery markers for event publication retries."""

    def add_marker(self, marker: IngestionRecoveryMarker) -> None: ...

    def list_markers(
        self,
        *,
        event_type: str | None = None,
    ) -> list[IngestionRecoveryMarker]: ...

    def find_marker(
        self,
        *,
        event_type: str,
        knowledge_base_id: str,
        source_document_id: str,
        content_hash: str | None = None,
    ) -> IngestionRecoveryMarker | None: ...

    def remove_marker(self, marker_id: str) -> None: ...


class InMemoryIngestionRecoveryStore:
    def __init__(self) -> None:
        self._markers: list[IngestionRecoveryMarker] = []

    def add_marker(self, marker: IngestionRecoveryMarker) -> None:
        self._markers.append(marker)

    def list_markers(
        self,
        *,
        event_type: str | None = None,
    ) -> list[IngestionRecoveryMarker]:
        markers = list(self._markers)
        if event_type is not None:
            markers = [marker for marker in markers if marker.event_type == event_type]
        return markers

    def find_marker(
        self,
        *,
        event_type: str,
        knowledge_base_id: str,
        source_document_id: str,
        content_hash: str | None = None,
    ) -> IngestionRecoveryMarker | None:
        for marker in self._markers:
            if (
                marker.event_type == event_type
                and marker.knowledge_base_id == knowledge_base_id
                and marker.source_document_id == source_document_id
                and (content_hash is None or marker.content_hash == content_hash)
            ):
                return marker
        return None

    def remove_marker(self, marker_id: str) -> None:
        self._markers = [
            marker for marker in self._markers if marker.marker_id != marker_id
        ]


class ObjectStoreIngestionRecoveryStore:
    """Persist ingestion recovery markers as JSON objects."""

    def __init__(
        self,
        object_store: ObjectStoreProtocol,
        *,
        prefix: str = _RECOVERY_PREFIX,
    ) -> None:
        self._object_store = object_store
        self._prefix = prefix.rstrip("/") + "/"

    def add_marker(self, marker: IngestionRecoveryMarker) -> None:
        self._object_store.put_bytes(
            self._marker_key(marker.marker_id),
            marker.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "event_type": marker.event_type,
                "knowledge_base_id": marker.knowledge_base_id,
                "source_document_id": marker.source_document_id,
            },
        )

    def list_markers(
        self,
        *,
        event_type: str | None = None,
    ) -> list[IngestionRecoveryMarker]:
        markers: list[IngestionRecoveryMarker] = []
        for key in self._object_store.list_keys(self._prefix):
            stored = self._object_store.get_bytes(key)
            marker = IngestionRecoveryMarker.model_validate_json(stored.content)
            if event_type is None or marker.event_type == event_type:
                markers.append(marker)
        return sorted(markers, key=lambda marker: marker.created_at)

    def find_marker(
        self,
        *,
        event_type: str,
        knowledge_base_id: str,
        source_document_id: str,
        content_hash: str | None = None,
    ) -> IngestionRecoveryMarker | None:
        for marker in self.list_markers(event_type=event_type):
            if (
                marker.knowledge_base_id == knowledge_base_id
                and marker.source_document_id == source_document_id
                and (content_hash is None or marker.content_hash == content_hash)
            ):
                return marker
        return None

    def remove_marker(self, marker_id: str) -> None:
        self._object_store.delete(self._marker_key(marker_id))

    def _marker_key(self, marker_id: str) -> str:
        return f"{self._prefix}{marker_id}.json"


__all__ = [
    "IngestionRecoveryMarker",
    "IngestionRecoveryStore",
    "InMemoryIngestionRecoveryStore",
    "ObjectStoreIngestionRecoveryStore",
]
