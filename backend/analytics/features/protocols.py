"""Protocols for feature-value persistence."""

from __future__ import annotations

from typing import Protocol

from analytics.features.models import FeatureValueRecord


class FeatureValueRepositoryProtocol(Protocol):
    """Repository for normalized feature values."""

    def upsert(self, record: FeatureValueRecord) -> None:
        """Create or replace a feature value record."""

    def list_for_entity(
        self,
        knowledge_base_id: str,
        entity_type: str,
        entity_id: str,
    ) -> list[FeatureValueRecord]:
        """List feature values for a KB-scoped entity."""

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all feature values for a knowledge base; return rows removed."""


__all__ = ["FeatureValueRepositoryProtocol"]
