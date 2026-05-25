"""Per-knowledge-base rate limiter for graph-metric recomputation.

A burst of ``GraphUpdatedEvent``s would otherwise trigger a metric
recompute per event. The throttle records the last recompute time per KB and
rejects further recomputes until ``min_interval_seconds`` has elapsed, so the
graph-metrics feedback loop cannot thrash the system.
"""

from __future__ import annotations

from datetime import datetime, timedelta

__all__ = ["MetricsRecomputeThrottle"]


class MetricsRecomputeThrottle:
    """Allow at most one metric recompute per KB per ``min_interval_seconds``."""

    def __init__(self, *, min_interval_seconds: int) -> None:
        if min_interval_seconds <= 0:
            raise ValueError("min_interval_seconds must be greater than 0.")
        self._min_interval = timedelta(seconds=min_interval_seconds)
        self._last_recompute: dict[str, datetime] = {}

    def should_recompute(self, knowledge_base_id: str, *, now: datetime) -> bool:
        """Return True and record ``now`` when a recompute is permitted."""

        previous = self._last_recompute.get(knowledge_base_id)
        if previous is not None and (now - previous) < self._min_interval:
            return False
        self._last_recompute[knowledge_base_id] = now
        return True
