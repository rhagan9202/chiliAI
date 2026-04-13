"""In-memory vectorstore adapter for tests and local development."""

from __future__ import annotations

import math

from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord


class InMemoryVectorStore(VectorStoreProtocol):
    """Store vector records in process-local dictionaries keyed by knowledge base."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, VectorRecord]] = {}
        self._dimensions: dict[str, int] = {}

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        if not records:
            return []

        dimension = len(records[0].embedding)
        for record in records:
            if len(record.embedding) != dimension:
                raise VectorDimensionMismatchError(
                    "All records in a batch must have the same embedding dimension."
                )

        current_dimension = self._dimensions.get(knowledge_base_id)
        if current_dimension is not None and current_dimension != dimension:
            raise VectorDimensionMismatchError(
                "Embedding dimension does not match the existing namespace dimension."
            )

        self._dimensions[knowledge_base_id] = dimension
        bucket = self._records.setdefault(knowledge_base_id, {})
        for record in records:
            bucket[record.id] = record
        return list(records)

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]:
        dimension = self._dimensions.get(knowledge_base_id)
        if dimension is None:
            return []
        if len(query_vector) != dimension:
            raise VectorDimensionMismatchError(
                "Query vector dimension does not match the namespace dimension."
            )

        normalized_filters = filters or {}
        scored_matches: list[VectorMatch] = []
        for record in self._records.get(knowledge_base_id, {}).values():
            if not _matches_filters(record, normalized_filters):
                continue
            scored_matches.append(
                VectorMatch(
                    record_id=record.id,
                    content_id=record.content_id,
                    score=_cosine_similarity(query_vector, record.embedding),
                    content=record.content,
                    metadata=dict(record.metadata),
                )
            )

        scored_matches.sort(key=lambda match: match.score, reverse=True)
        return scored_matches[:limit]


def _matches_filters(record: VectorRecord, filters: dict[str, MetadataValue]) -> bool:
    for key, value in filters.items():
        if record.metadata.get(key) != value:
            return False
    return True


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(lhs * rhs for lhs, rhs in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)