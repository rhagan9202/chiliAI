"""Storage-layer models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StoredObjectWriteResult(BaseModel):
    """Metadata returned after storing an object."""

    key: str
    size_bytes: int = Field(ge=0)
    media_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class StoredObject(BaseModel):
    """Stored object data plus metadata."""

    key: str
    content: bytes
    size_bytes: int = Field(ge=0)
    media_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    # TODO(production): Add created_at/updated_at timestamps, etag/version_id for
    # optimistic concurrency, and checksum: str | None for integrity verification.
    # Add ListObjectsResult model for paginated listing with cursor support.


__all__ = [
    "StoredObject",
    "StoredObjectWriteResult",
]