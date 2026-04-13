"""Vector store adapters."""

from __future__ import annotations

from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol

__all__ = ["InMemoryVectorStore", "VectorStoreProtocol"]