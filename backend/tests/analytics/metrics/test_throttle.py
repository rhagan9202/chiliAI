"""Tests for the per-KB metrics recompute throttle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.metrics.throttle import MetricsRecomputeThrottle


def test_first_recompute_is_allowed() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=now) is True


def test_recompute_within_interval_is_rejected() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    start = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=start) is True
    assert (
        throttle.should_recompute("kb-1", now=start + timedelta(seconds=120))
        is False
    )


def test_recompute_after_interval_is_allowed_again() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    start = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=start) is True
    assert (
        throttle.should_recompute("kb-1", now=start + timedelta(seconds=301))
        is True
    )


def test_throttle_is_per_knowledge_base() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=now) is True
    assert throttle.should_recompute("kb-2", now=now) is True
    # Each KB throttles independently.
    assert throttle.should_recompute("kb-1", now=now + timedelta(seconds=10)) is False
    assert throttle.should_recompute("kb-2", now=now + timedelta(seconds=10)) is False


def test_zero_interval_raises() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        MetricsRecomputeThrottle(min_interval_seconds=0)


def test_negative_interval_raises() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        MetricsRecomputeThrottle(min_interval_seconds=-1)
