"""Graph repository adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository

if TYPE_CHECKING:
	from graph.adapters.neo4j_adapter import Neo4jGraphRepository as Neo4jGraphRepository
else:
	Neo4jGraphRepository: type[GraphRepository] | None

	try:
		from graph.adapters.neo4j_adapter import Neo4jGraphRepository as _Neo4jGraphRepository
	except ImportError:  # pragma: no cover - optional dependency
		Neo4jGraphRepository = None
	else:
		Neo4jGraphRepository = _Neo4jGraphRepository

__all__ = ["GraphRepository", "InMemoryGraphRepository", "Neo4jGraphRepository"]