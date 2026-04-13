"""Service-boundary models for rag queries and answers."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from rag.models import MetadataValue


class RagQueryRequest(BaseModel):
    """A caller-supplied rag query."""

    knowledge_base_id: str
    question: str
    top_k: int = Field(default=5, gt=0)
    include_graph_context: bool = True
    system_prompt: str | None = None
    filters: dict[str, MetadataValue] = Field(default_factory=dict)

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


class RagQueryResponse(BaseModel):
    """A generated answer plus supporting citations."""

    request_id: str
    knowledge_base_id: str
    answer: str
    provider: str
    model_name: str
    citations: list[RagCitation] = Field(default_factory=list)
    graph_summary: str | None = None


__all__ = ["RagCitation", "RagQueryRequest", "RagQueryResponse"]