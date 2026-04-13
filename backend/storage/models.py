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


__all__ = [
    "StoredObject",
    "StoredObjectWriteResult",
]