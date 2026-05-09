"""Vector store adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol

if TYPE_CHECKING:
	from vectorstore.adapters.qdrant_adapter import QdrantVectorStore as QdrantVectorStore
else:
	QdrantVectorStore: type[VectorStoreProtocol] | None

	try:
		from vectorstore.adapters.qdrant_adapter import QdrantVectorStore as _QdrantVectorStore
	except ImportError:  # pragma: no cover - optional dependency
		QdrantVectorStore = None
	else:
		QdrantVectorStore = _QdrantVectorStore

__all__ = ["InMemoryVectorStore", "QdrantVectorStore", "VectorStoreProtocol"]