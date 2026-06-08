"""Adapter protocols for peerstats record reads and signal writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec


@dataclass(frozen=True, slots=True)
class ColumnRow:
    """One record's contribution to a metric: an entity value at a time.

    ``group_values`` is a tuple so the row is genuinely immutable and hashable
    under ``frozen=True``.
    """

    entity_id: str
    entity_type: str
    group_values: tuple[str, ...] = ()
    value: float = 0.0
    observed_at: datetime = datetime.min


@runtime_checkable
class RecordColumnSourceProtocol(Protocol):
    """Load per-entity, per-interval aggregates for a metric spec."""

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]: ...


@runtime_checkable
class DerivedRiskSignalWriterProtocol(Protocol):
    """Persist derived risk signals idempotently."""

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int:
        """Persist the signals; return the count processed (not net-new inserts)."""
        ...


__all__ = [
    "ColumnRow",
    "DerivedRiskSignalWriterProtocol",
    "RecordColumnSourceProtocol",
]
