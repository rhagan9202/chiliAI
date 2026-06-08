"""Pure helpers: interval bucketing, aggregation, peer-group keys, z→signal."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from analytics.peerstats.exceptions import PeerStatsConfigurationError

__all__ = [
    "apply_aggregation",
    "bucket_start",
    "peer_group_key",
    "z_to_signal",
]

Interval = Literal["day", "week", "month"]
Aggregation = Literal["sum", "mean", "count", "max", "min"]
Direction = Literal["high", "low", "two_sided"]


def bucket_start(observed_at: datetime, interval: Interval) -> datetime:
    """Return the start of the interval bucket containing ``observed_at``."""

    midnight = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "day":
        return midnight
    if interval == "week":
        return midnight - timedelta(days=midnight.weekday())
    if interval == "month":
        return midnight.replace(day=1)
    raise PeerStatsConfigurationError(  # pragma: no cover - unreachable under Interval
        f"Unknown interval '{interval}'."
    )


def apply_aggregation(values: list[float], fn: Aggregation) -> float:
    """Aggregate a non-empty list of numeric values by the named function."""

    if not values:
        raise PeerStatsConfigurationError("Cannot aggregate an empty value list.")
    if fn == "sum":
        return float(sum(values))
    if fn == "mean":
        return float(sum(values) / len(values))
    if fn == "count":
        return float(len(values))
    if fn == "max":
        return float(max(values))
    if fn == "min":
        return float(min(values))
    raise PeerStatsConfigurationError(  # pragma: no cover - unreachable under Aggregation
        f"Unknown aggregation '{fn}'."
    )


def peer_group_key(entity_type: str, group_values: Sequence[str]) -> str:
    """Build a stable cohort key from entity type and grouping-column values."""

    return "|".join([entity_type, *group_values])


def z_to_signal(z_score: float, *, direction: Direction, z_cap: float) -> float:
    """Map a z-score to a [0,1] risk signal value on the risky tail."""

    if direction == "high":
        tail = max(z_score, 0.0)
    elif direction == "low":
        tail = max(-z_score, 0.0)
    else:
        tail = abs(z_score)
    return min(tail / z_cap, 1.0)
