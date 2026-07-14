"""Internal transport and workflow models for embedding generation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now

EmbeddingChannel = Literal["text", "graph"]


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
    items: list[EmbeddingItem] = Field(
        default_factory=lambda: cast(list[EmbeddingItem], [])
    )

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
    total_tokens: int | None = Field(default=None, ge=0)


class EmbeddingVector(BaseModel):
    """A single channel-specific embedding vector."""

    content_id: str
    channel: EmbeddingChannel
    vector: list[float]
    model_name: str
    provider: str
    dimensions: int = Field(gt=0)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_vector(self) -> EmbeddingVector:
        if not self.vector:
            raise ValueError("EmbeddingVector vector must be non-empty.")
        if len(self.vector) != self.dimensions:
            raise ValueError("EmbeddingVector vector length must match dimensions.")
        return self


class GraphEmbeddingBatch(BaseModel):
    """Graph embedding vectors generated for a batch of content items."""

    vectors: dict[str, list[float]]
    model_name: str
    provider: str
    dimensions: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_vectors(self) -> GraphEmbeddingBatch:
        for content_id, vector in self.vectors.items():
            if not vector:
                raise ValueError(
                    f"GraphEmbeddingBatch vector for {content_id} must be non-empty."
                )
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"GraphEmbeddingBatch vector for {content_id} must match dimensions."
                )
        return self


class GraphEmbeddingStatus(BaseModel):
    """Graph embedding request and availability status."""

    requested: bool
    provider_configured: bool
    missing_content_ids: list[str] = Field(
        default_factory=lambda: cast(list[str], [])
    )
    failure_message: str | None = None


class CachedEmbedding(BaseModel):
    """A cached text-channel embedding with its producing model identity."""

    vector: list[float]
    model_name: str
    provider: str
    dimensions: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_vector(self) -> CachedEmbedding:
        if not self.vector:
            raise ValueError("CachedEmbedding vector must be non-empty.")
        if len(self.vector) != self.dimensions:
            raise ValueError("CachedEmbedding vector length must match dimensions.")
        return self


def build_embedding_cache_key(
    *, namespace: str, model_name: str, content: str
) -> str:
    """Build a collision-resistant cache key for one text + model identity."""

    digest = hashlib.sha256()
    digest.update(namespace.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(model_name.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(content.encode("utf-8"))
    return digest.hexdigest()


class EmbeddingResult(BaseModel):
    """Internal embedding batch result returned by an embedder adapter."""

    request_id: str
    vectors: dict[str, list[float]] = Field(
        default_factory=lambda: cast(dict[str, list[float]], {})
    )
    metadata: EmbeddingMetadata
    items: list[EmbeddingVector] = Field(
        default_factory=lambda: cast(list[EmbeddingVector], [])
    )
    graph_status: GraphEmbeddingStatus | None = None

    @model_validator(mode="after")
    def _validate_vectors(self) -> EmbeddingResult:
        if not self.items and self.vectors:
            self.items = [
                EmbeddingVector(
                    content_id=content_id,
                    channel="text",
                    vector=vector,
                    model_name=self.metadata.model_name,
                    provider=self.metadata.provider,
                    dimensions=self.metadata.dimensions,
                    created_at=self.metadata.created_at,
                )
                for content_id, vector in self.vectors.items()
            ]

        text_vectors = {
            item.content_id: item.vector for item in self.items if item.channel == "text"
        }
        if text_vectors:
            self.vectors = text_vectors

        if not self.vectors:
            raise ValueError("EmbeddingResult requires at least one text vector.")
        return self


__all__ = [
    "build_embedding_cache_key",
    "CachedEmbedding",
    "EmbeddingChannel",
    "EmbeddingItem",
    "EmbeddingMetadata",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingVector",
    "GraphEmbeddingBatch",
    "GraphEmbeddingStatus",
]
