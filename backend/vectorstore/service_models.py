"""Service-boundary models for vectorstore indexing and search."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now
from vectorstore.models import MetadataValue


def _empty_embedding() -> list[float]:
    return []


def _empty_submissions() -> list[VectorIndexSubmission]:
    return []


def _empty_matches() -> list[VectorSearchMatch]:
    return []


class VectorIndexSubmission(BaseModel):
    """A single embedding payload submitted to the vectorstore service."""

    content_id: str
    embedding: list[float] = Field(default_factory=_empty_embedding)
    content: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_embedding(self) -> VectorIndexSubmission:
        if not self.embedding:
            raise ValueError("VectorIndexSubmission requires a non-empty embedding.")
        return self


class VectorIndexRequest(BaseModel):
    """A batch vector-indexing request for one knowledge base."""

    knowledge_base_id: str
    submissions: list[VectorIndexSubmission] = Field(default_factory=_empty_submissions)

    @model_validator(mode="after")
    def _validate_submissions(self) -> VectorIndexRequest:
        if not self.submissions:
            raise ValueError("VectorIndexRequest requires at least one submission.")
        return self


class VectorIndexReceipt(BaseModel):
    """Receipt returned for each indexed embedding record."""

    knowledge_base_id: str
    record_id: str
    content_id: str
    dimension: int = Field(gt=0)
    created_at: datetime = Field(default_factory=utc_now)


class VectorSearchRequest(BaseModel):
    """A vector similarity-search request."""

    knowledge_base_id: str
    query_vector: list[float] = Field(default_factory=_empty_embedding)
    limit: int = Field(default=5, gt=0)
    filters: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_query(self) -> VectorSearchRequest:
        if not self.query_vector:
            raise ValueError("VectorSearchRequest requires a non-empty query_vector.")
        return self


class VectorSearchMatch(BaseModel):
    """Service-boundary representation of a vector search match."""

    record_id: str
    content_id: str
    score: float = Field(ge=-1.0, le=1.0)
    content: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class VectorSearchResponse(BaseModel):
    """Response returned by a vector similarity-search request."""

    knowledge_base_id: str
    query_dimension: int = Field(gt=0)
    matches: list[VectorSearchMatch] = Field(default_factory=_empty_matches)


__all__ = [
    "VectorIndexReceipt",
    "VectorIndexRequest",
    "VectorIndexSubmission",
    "VectorSearchMatch",
    "VectorSearchRequest",
    "VectorSearchResponse",
]