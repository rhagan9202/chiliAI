"""API-boundary models for embedding generation."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, model_validator

from embeddings.models import EmbeddingChannel, GraphEmbeddingStatus


class EmbedSubmission(BaseModel):
    """A single caller-supplied item to embed."""

    content_id: str
    content: str

    @model_validator(mode="after")
    def _validate_content(self) -> EmbedSubmission:
        if self.content.strip() == "":
            raise ValueError("EmbedSubmission content must not be empty.")
        return self


class EmbedRequest(BaseModel):
    """Service-boundary embedding request."""

    knowledge_base_id: str | None = None
    model_name: str = "in-memory-embedder"
    include_graph_embeddings: bool = False
    require_graph_embeddings: bool = False
    graph_embedding_dimension: int = Field(default=8, gt=0, le=256)
    submissions: list[EmbedSubmission] = Field(
        default_factory=lambda: cast(list[EmbedSubmission], [])
    )

    @model_validator(mode="after")
    def _validate_submissions(self) -> EmbedRequest:
        if not self.submissions:
            raise ValueError("EmbedRequest requires at least one submission.")
        return self


class EmbeddedItem(BaseModel):
    """One embedded item returned to callers."""

    content_id: str
    vector: list[float] = Field(default_factory=lambda: cast(list[float], []))
    channel: EmbeddingChannel = "text"
    model_name: str | None = None
    provider: str | None = None
    dimensions: int | None = None

    @model_validator(mode="after")
    def _default_dimensions(self) -> EmbeddedItem:
        if self.dimensions is None:
            self.dimensions = len(self.vector)
        return self


class EmbedResponse(BaseModel):
    """Service-boundary embedding response."""

    request_id: str
    model_name: str
    dimensions: int = Field(gt=0)
    items: list[EmbeddedItem] = Field(
        default_factory=lambda: cast(list[EmbeddedItem], [])
    )
    graph_status: GraphEmbeddingStatus | None = None


__all__ = ["EmbedRequest", "EmbedResponse", "EmbedSubmission", "EmbeddedItem"]
