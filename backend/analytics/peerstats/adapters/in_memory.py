"""In-memory peerstats adapters for tests and local development."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.aggregation import (
    apply_aggregation,
    bucket_start,
    peer_group_key,
)
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec

__all__ = ["InMemoryDerivedRiskSignalWriter", "InMemoryRecordColumnSource"]


class InMemoryRecordColumnSource:
    """Aggregate seeded column rows in Python, mirroring the Postgres adapter."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], list[ColumnRow]] = defaultdict(list)

    def add_rows(
        self, knowledge_base_id: str, record_type: str, rows: list[ColumnRow]
    ) -> None:
        self._rows[(knowledge_base_id, record_type)].extend(rows)

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        wanted = set(interval_starts)
        buckets: dict[tuple[str, str, str, datetime], list[float]] = defaultdict(list)
        for row in self._rows.get((knowledge_base_id, spec.record_type), []):
            start = bucket_start(row.observed_at, spec.interval)
            if wanted and start not in wanted:
                continue
            group_key = peer_group_key(row.entity_type, row.group_values)
            key = (row.entity_id, row.entity_type, group_key, start)
            buckets[key].append(row.value)
        aggregates: list[PeerAggregate] = []
        for (entity_id, entity_type, group_key, start), values in buckets.items():
            aggregates.append(
                PeerAggregate(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    peer_group_key=group_key,
                    interval_start=start,
                    aggregate_value=apply_aggregation(values, spec.aggregation),
                )
            )
        return aggregates


class InMemoryDerivedRiskSignalWriter:
    """Store derived signals keyed by (kb, entity, metric, interval)."""

    def __init__(self) -> None:
        self._signals: dict[tuple[str, str, str, datetime], DerivedRiskSignal] = {}

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int:
        for signal in signals:
            key = (
                signal.knowledge_base_id,
                signal.entity_id,
                signal.metric_name,
                signal.interval_start,
            )
            self._signals[key] = signal
        return len(signals)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._signals if key[0] == knowledge_base_id]
        for key in keys:
            del self._signals[key]
        return len(keys)

    def latest_signals(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str | None = None,
    ) -> list[DerivedRiskSignal]:
        by_metric: dict[str, DerivedRiskSignal] = {}
        for signal in self._signals.values():
            if (
                signal.knowledge_base_id != knowledge_base_id
                or signal.entity_id != entity_id
                or (metric_name is not None and signal.metric_name != metric_name)
            ):
                continue
            current = by_metric.get(signal.metric_name)
            if current is None or signal.interval_start >= current.interval_start:
                by_metric[signal.metric_name] = signal
        return sorted(
            by_metric.values(),
            key=lambda signal: (signal.metric_name, signal.interval_start),
        )

    def peer_group_signals(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        interval_start: datetime,
        peer_group_key: str,
    ) -> list[DerivedRiskSignal]:
        return sorted(
            [
                signal
                for signal in self._signals.values()
                if signal.knowledge_base_id == knowledge_base_id
                and signal.metric_name == metric_name
                and signal.interval_start == interval_start
                and signal.peer_group_key == peer_group_key
            ],
            key=lambda signal: signal.entity_id,
        )
