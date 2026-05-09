"""Embedding adapters."""

from __future__ import annotations

from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.openai_adapter import OpenAIEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbedder,
)

__all__ = [
    "EmbedderProtocol",
    "InMemoryEmbedder",
    "OpenAIEmbedder",
    "SentenceTransformersEmbedder",
]