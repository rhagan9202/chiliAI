"""Internal transport and workflow models for embedding generation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now


class EmbeddingItem(BaseModel):
    """A single item to embed."""

    id: str
    content: str

    @model_validator(mode="after")
    def _validate_content(self) -> EmbeddingItem:
        if self.content.strip() == "":
            raise ValueError("EmbeddingItem content must not be empty.")
        return self


class EmbeddingRequest(BaseModel):
    """Internal embedding request passed to an embedder adapter."""

    request_id: str
    knowledge_base_id: str | None = None
    model_name: str
    items: list[EmbeddingItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_items(self) -> EmbeddingRequest:
        if not self.items:
            raise ValueError("EmbeddingRequest requires at least one item.")
        return self


class EmbeddingMetadata(BaseModel):
    """Metadata attached to an embedding batch result."""

    model_name: str
    dimensions: int = Field(gt=0)
    provider: str
    created_at: datetime = Field(default_factory=utc_now)


class EmbeddingResult(BaseModel):
    """Internal embedding batch result returned by an embedder adapter."""

    request_id: str
    vectors: dict[str, list[float]] = Field(default_factory=dict)
    metadata: EmbeddingMetadata

    @model_validator(mode="after")
    def _validate_vectors(self) -> EmbeddingResult:
        if not self.vectors:
            raise ValueError("EmbeddingResult requires at least one vector.")
        return self


__all__ = [
    "EmbeddingItem",
    "EmbeddingMetadata",
    "EmbeddingRequest",
    "EmbeddingResult",
]