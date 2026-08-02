"""In-memory feature-value repository."""

from __future__ import annotations

from analytics.features.models import FeatureValueRecord


class InMemoryFeatureValueRepository:
    """Store normalized feature values in process memory."""

    def __init__(self) -> None:
        self._records: dict[
            tuple[str, str, str, str, str, str, str | None],
            FeatureValueRecord,
        ] = {}

    @staticmethod
    def _key(
        record: FeatureValueRecord,
    ) -> tuple[str, str, str, str, str, str, str | None]:
        return (
            record.knowledge_base_id,
            record.entity_type,
            record.entity_id,
            record.feature_id,
            record.catalog_version,
            record.transformation_version,
            record.score_run_id,
        )

    def upsert(self, record: FeatureValueRecord) -> None:
        """Create or replace a feature value record."""

        self._records[self._key(record)] = record.model_copy(deep=True)

    def list_for_entity(
        self,
        knowledge_base_id: str,
        entity_type: str,
        entity_id: str,
    ) -> list[FeatureValueRecord]:
        """List feature values for a KB-scoped entity."""

        values = [
            record.model_copy(deep=True)
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_type == entity_type
            and record.entity_id == entity_id
        ]
        values.sort(key=lambda record: (record.feature_id, record.observed_at))
        return values

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all feature values for a knowledge base; return rows removed."""

        keys = [
            key
            for key, record in self._records.items()
            if record.knowledge_base_id == knowledge_base_id
        ]
        for key in keys:
            del self._records[key]
        return len(keys)


__all__ = ["InMemoryFeatureValueRepository"]
