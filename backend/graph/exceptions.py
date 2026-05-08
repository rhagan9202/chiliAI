"""Exception hierarchy for the graph module."""

from __future__ import annotations


class GraphError(Exception):
    """Base exception for graph module failures."""


class GraphPersistenceError(GraphError):
    """Raised when graph state or graph artifacts cannot be persisted."""


class BatchUpsertError(GraphPersistenceError):
    """Raised when a chunked graph upsert fails after partial success."""

    def __init__(
        self,
        successful_entity_count: int,
        successful_relationship_count: int,
    ) -> None:
        self.successful_entity_count = successful_entity_count
        self.successful_relationship_count = successful_relationship_count
        super().__init__(
            "Failed to upsert a graph batch after persisting "
            f"{successful_entity_count} entities and "
            f"{successful_relationship_count} relationships."
        )


__all__ = [
    "BatchUpsertError",
    "GraphError",
    "GraphPersistenceError",
]