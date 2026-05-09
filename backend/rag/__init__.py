"""Public exports for the rag service module."""

from __future__ import annotations

from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
    InMemoryRagService,
)
from rag.adapters.protocols import (
    AnswerGeneratorProtocol,
    ContextRetrieverProtocol,
    GraphContextExpanderProtocol,
    QueryEmbedderProtocol,
)
from rag.exceptions import RagConfigurationError, RagError, RagGenerationError, RagRetrievalError
from rag.models import (
    ContextRecord,
    GraphContext,
    GraphContextEdge,
    GraphContextNode,
    RagGenerationRequest,
    RagGenerationResult,
    RagWorkflowState,
    RetrievedContextItem,
)
from rag.protocols import RagServiceProtocol
from rag.service import RagService, create_rag_service
from rag.service_models import (
    RagAnswer,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
    RagStreamChunk,
)

__all__ = [
    "AnswerGeneratorProtocol",
    "ContextRecord",
    "ContextRetrieverProtocol",
    "GraphContext",
    "GraphContextEdge",
    "GraphContextExpanderProtocol",
    "GraphContextNode",
    "InMemoryAnswerGenerator",
    "InMemoryContextRetriever",
    "InMemoryGraphContextExpander",
    "InMemoryQueryEmbedder",
    "InMemoryRagService",
    "QueryEmbedderProtocol",
    "RagAnswer",
    "RagCitation",
    "RagConfigurationError",
    "RagError",
    "RagGenerationError",
    "RagGenerationRequest",
    "RagGenerationResult",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagRetrievalError",
    "RagService",
    "RagServiceProtocol",
    "RagStreamChunk",
    "RagWorkflowState",
    "RetrievedContextItem",
    "create_rag_service",
]