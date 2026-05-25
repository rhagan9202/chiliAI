"""Adapter-level protocol for entity-metric persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.metrics.models import EntityMetricSample, EntityMetricValue


@runtime_checkable
class EntityMetricRepository(Protocol):
    """Persist graph metrics over time and expose the current snapshot."""

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        """Append samples to history and upsert the current snapshot.

        Returns the count of newly inserted history rows. Idempotent: a sample
        with the same (knowledge_base_id, entity_id, metric_name, observed_at)
        is not double-counted.
        """
        ...

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        """Return the latest value of every metric for one entity."""
        ...


__all__ = [
    "EntityMetricRepository",
]
