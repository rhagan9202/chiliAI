"""In-memory entity-metric repository for tests and local development."""

from __future__ import annotations

from analytics.metrics.models import EntityMetricSample, EntityMetricValue

__all__ = ["InMemoryEntityMetricRepository"]


class InMemoryEntityMetricRepository:
    """A dict-backed ``EntityMetricRepository``."""

    def __init__(self) -> None:
        self._history: list[EntityMetricSample] = []
        self._current: dict[tuple[str, str, str], EntityMetricValue] = {}

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        written = 0
        for sample in samples:
            history_key = (
                sample.knowledge_base_id,
                sample.entity_id,
                sample.metric_name,
                sample.observed_at,
            )
            if any(
                (s.knowledge_base_id, s.entity_id, s.metric_name, s.observed_at)
                == history_key
                for s in self._history
            ):
                continue
            self._history.append(sample)
            written += 1
            self._current[
                (sample.knowledge_base_id, sample.entity_id, sample.metric_name)
            ] = EntityMetricValue(
                knowledge_base_id=sample.knowledge_base_id,
                entity_id=sample.entity_id,
                metric_name=sample.metric_name,
                value=sample.value,
                updated_at=sample.observed_at,
            )
        return written

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        matches = [
            value
            for (kb, ent, _metric), value in self._current.items()
            if kb == knowledge_base_id and ent == entity_id
        ]
        return sorted(matches, key=lambda value: value.metric_name)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Remove all history and current entries for *knowledge_base_id*.

        Returns the number of history rows removed. Idempotent.
        """
        before = len(self._history)
        self._history = [
            s for s in self._history if s.knowledge_base_id != knowledge_base_id
        ]
        removed_history = before - len(self._history)
        keys_to_delete = [
            key for key in self._current if key[0] == knowledge_base_id
        ]
        for key in keys_to_delete:
            del self._current[key]
        return removed_history
