"""Internal transport models for vectorstore indexing and search."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now


MetadataValue = str | int | float | bool


def _empty_embedding() -> list[float]:
    return []


class VectorRecord(BaseModel):
    """A persisted embedding record in a vector namespace."""

    id: str
    knowledge_base_id: str
    content_id: str
    embedding: list[float] = Field(default_factory=_empty_embedding)
    content: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)
    indexed_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_embedding(self) -> VectorRecord:
        if not self.embedding:
            raise ValueError("VectorRecord requires a non-empty embedding.")
        return self


class VectorMatch(BaseModel):
    """A similarity-search match returned by the vector store."""

    record_id: str
    content_id: str
    score: float
    content: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


__all__ = ["MetadataValue", "VectorMatch", "VectorRecord"]
