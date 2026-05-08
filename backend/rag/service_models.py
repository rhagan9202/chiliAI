"""Service-boundary models for rag queries and answers."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from rag.models import MetadataValue


def _empty_filters() -> dict[str, MetadataValue]:
    return {}


def _empty_citations() -> list[RagCitation]:
    return []


def _empty_sources() -> list[str]:
    return []


class RagQueryRequest(BaseModel):
    """A caller-supplied rag query."""

    knowledge_base_id: str
    question: str
    top_k: int = Field(default=5, gt=0)
    include_graph_context: bool = True
    system_prompt: str | None = None
    filters: dict[str, MetadataValue] = Field(default_factory=_empty_filters)

    @model_validator(mode="after")
    def _validate_question(self) -> RagQueryRequest:
        if self.question.strip() == "":
            raise ValueError("RagQueryRequest question must not be empty.")
        return self


class RagCitation(BaseModel):
    """A citation returned with a rag answer."""

    record_id: str
    content_id: str
    score: float = Field(ge=-1.0, le=1.0)
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None


class RagQueryResponse(BaseModel):
    """A generated answer plus supporting citations."""

    request_id: str
    knowledge_base_id: str
    answer: str
    provider: str
    model_name: str
    citations: list[RagCitation] = Field(default_factory=_empty_citations)
    graph_summary: str | None = None


class RagAnswer(BaseModel):
    """A simplified answer used by the chat router."""

    content: str
    sources: list[str] = Field(default_factory=_empty_sources)


class RagStreamChunk(BaseModel):
    """A single chunk of a streaming rag answer.

    Non-final chunks carry generated text in ``chunk_text`` with an empty
    ``citations`` list. The final chunk has ``is_final=True``, an empty
    ``chunk_text``, and the full citation set assembled from retrieval.
    """

    chunk_text: str
    is_final: bool
    citations: list[RagCitation] = Field(default_factory=_empty_citations)


__all__ = [
    "RagAnswer",
    "RagCitation",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagStreamChunk",
]
