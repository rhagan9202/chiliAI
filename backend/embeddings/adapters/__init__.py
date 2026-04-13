"""Embedding adapters."""

from __future__ import annotations

from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol

__all__ = ["EmbedderProtocol", "InMemoryEmbedder"]