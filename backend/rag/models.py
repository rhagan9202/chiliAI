"""Internal transport and workflow models for rag orchestration."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


MetadataValue = str | int | float | bool


class ContextRecord(BaseModel):
    """A retrievable context record with its embedding."""

    record_id: str
    content_id: str
    embedding: list[float] = Field(default_factory=list)
    content: str
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_embedding(self) -> ContextRecord:
        if not self.embedding:
            raise ValueError("ContextRecord requires a non-empty embedding.")
        if self.content.strip() == "":
            raise ValueError("ContextRecord content must not be empty.")
        return self


class RetrievedContextItem(BaseModel):
    """A retrieval match carried forward into prompt assembly."""

    record_id: str
    content_id: str
    score: float = Field(ge=-1.0, le=1.0)
    content: str
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class GraphContextNode(BaseModel):
    """A graph node included in an expanded rag context."""

    entity_id: str
    entity_type: str | None = None
    summary: str


class GraphContextEdge(BaseModel):
    """A graph edge included in an expanded rag context."""

    relationship_id: str
    relationship_type: str
    source_id: str
    target_id: str
    summary: str | None = None


class GraphContext(BaseModel):
    """Graph-derived context assembled alongside retrieved documents."""

    nodes: list[GraphContextNode] = Field(default_factory=list)
    edges: list[GraphContextEdge] = Field(default_factory=list)
    summary: str | None = None


class RagGenerationRequest(BaseModel):
    """Normalized prompt assembly payload for answer generation."""

    request_id: str
    knowledge_base_id: str
    question: str
    context_items: list[RetrievedContextItem] = Field(default_factory=list)
    graph_context: GraphContext | None = None
    system_prompt: str | None = None

    @model_validator(mode="after")
    def _validate_question(self) -> RagGenerationRequest:
        if self.question.strip() == "":
            raise ValueError("RagGenerationRequest question must not be empty.")
        return self


class RagGenerationResult(BaseModel):
    """Internal answer-generation result returned by a rag adapter."""

    request_id: str
    answer: str
    provider: str
    model_name: str

    @model_validator(mode="after")
    def _validate_answer(self) -> RagGenerationResult:
        if self.answer.strip() == "":
            raise ValueError("RagGenerationResult answer must not be empty.")
        return self


class RagWorkflowState(BaseModel):
    """Mutable-by-copy workflow state for the rag pipeline."""

    request_id: str
    knowledge_base_id: str
    question: str
    query_vector: list[float] | None = None
    context_items: list[RetrievedContextItem] = Field(default_factory=list)
    graph_context: GraphContext | None = None

    @model_validator(mode="after")
    def _validate_question(self) -> RagWorkflowState:
        if self.question.strip() == "":
            raise ValueError("RagWorkflowState question must not be empty.")
        return self


__all__ = [
    "ContextRecord",
    "GraphContext",
    "GraphContextEdge",
    "GraphContextNode",
    "MetadataValue",
    "RagGenerationRequest",
    "RagGenerationResult",
    "RagWorkflowState",
    "RetrievedContextItem",
]