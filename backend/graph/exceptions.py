"""Exception hierarchy for the graph module."""

from __future__ import annotations


class GraphError(Exception):
    """Base exception for graph module failures."""


class GraphPersistenceError(GraphError):
    """Raised when graph state or graph artifacts cannot be persisted."""


class GraphIntegrityError(GraphPersistenceError):
    """Raised when a relationship references entity endpoints that do not exist."""

    def __init__(
        self,
        knowledge_base_id: str,
        missing_entity_ids: list[str],
        relationship_ids: list[str],
    ) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.missing_entity_ids = missing_entity_ids
        self.relationship_ids = relationship_ids
        super().__init__(
            f"Relationship upsert references missing entities {missing_entity_ids} "
            f"in knowledge base '{knowledge_base_id}' "
            f"(relationships: {relationship_ids})."
        )


class GraphVersionConflictError(GraphPersistenceError):
    """Raised when an upsert's expected_version does not match the stored version."""

    def __init__(
        self, entity_id: str, expected_version: int, actual_version: int
    ) -> None:
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict on entity '{entity_id}': expected "
            f"{expected_version}, stored {actual_version}."
        )


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
    "GraphIntegrityError",
    "GraphPersistenceError",
    "GraphVersionConflictError",
]