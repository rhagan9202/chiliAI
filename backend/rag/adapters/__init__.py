"""Rag adapters."""

from __future__ import annotations

from rag.adapters.embeddings_bridge import ServiceQueryEmbedder
from rag.adapters.graph_bridge import ServiceGraphContextExpander
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
)
from rag.adapters.llm_bridge import ServiceAnswerGenerator
from rag.adapters.protocols import (
    AnswerGeneratorProtocol,
    ContextRetrieverProtocol,
    GraphContextExpanderProtocol,
    QueryEmbedderProtocol,
)
from rag.adapters.vectorstore_bridge import ServiceContextRetriever

__all__ = [
    "AnswerGeneratorProtocol",
    "ContextRetrieverProtocol",
    "GraphContextExpanderProtocol",
    "InMemoryAnswerGenerator",
    "InMemoryContextRetriever",
    "InMemoryGraphContextExpander",
    "InMemoryQueryEmbedder",
    "QueryEmbedderProtocol",
    "ServiceAnswerGenerator",
    "ServiceContextRetriever",
    "ServiceGraphContextExpander",
    "ServiceQueryEmbedder",
]