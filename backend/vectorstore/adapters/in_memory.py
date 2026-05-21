"""In-memory vectorstore adapter for tests and local development."""

from __future__ import annotations

import math

from vectorstore.exceptions import VectorDimensionMismatchError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord

__all__ = ["InMemoryVectorStore"]


class InMemoryVectorStore:
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
        stored_records = [record.model_copy(deep=True) for record in records]
        for record in stored_records:
            bucket[record.id] = record
        return [record.model_copy(deep=True) for record in stored_records]

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

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        record = self._records.get(knowledge_base_id, {}).get(record_id)
        if record is None:
            return None
        return record.model_copy(deep=True)

    def count_records(self, knowledge_base_id: str) -> int:
        return len(self._records.get(knowledge_base_id, {}))

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        bucket = self._records.get(knowledge_base_id)
        if bucket is None or record_id not in bucket:
            return False
        del bucket[record_id]
        if not bucket:
            self._records.pop(knowledge_base_id, None)
            self._dimensions.pop(knowledge_base_id, None)
        return True

    def delete_namespace(self, knowledge_base_id: str) -> int:
        deleted_count = len(self._records.get(knowledge_base_id, {}))
        self._records.pop(knowledge_base_id, None)
        self._dimensions.pop(knowledge_base_id, None)
        return deleted_count


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
