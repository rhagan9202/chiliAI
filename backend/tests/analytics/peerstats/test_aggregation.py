"""Tests for peerstats pure helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.peerstats.aggregation import (
    Aggregation,
    apply_aggregation,
    bucket_start,
    peer_group_key,
    z_to_signal,
)
from analytics.peerstats.exceptions import PeerStatsConfigurationError


def _dt(y: int, m: int, d: int, h: int = 0) -> datetime:
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_bucket_start_day_truncates_time() -> None:
    assert bucket_start(_dt(2026, 1, 5, 14), "day") == _dt(2026, 1, 5)


def test_bucket_start_week_floors_to_monday() -> None:
    # 2026-01-07 is a Wednesday; ISO week starts Monday 2026-01-05.
    assert bucket_start(_dt(2026, 1, 7, 9), "week") == _dt(2026, 1, 5)


def test_bucket_start_month_floors_to_first() -> None:
    assert bucket_start(_dt(2026, 3, 22, 3), "month") == _dt(2026, 3, 1)


@pytest.mark.parametrize(
    ("fn", "expected"),
    [("sum", 6.0), ("mean", 2.0), ("count", 3.0), ("max", 3.0), ("min", 1.0)],
)
def test_apply_aggregation(fn: Aggregation, expected: float) -> None:
    assert apply_aggregation([1.0, 2.0, 3.0], fn) == expected


def test_apply_aggregation_empty_raises() -> None:
    with pytest.raises(PeerStatsConfigurationError, match="empty"):
        apply_aggregation([], "sum")


def test_peer_group_key_type_only_when_no_group_cols() -> None:
    assert peer_group_key("provider", []) == "provider"


def test_peer_group_key_includes_group_values() -> None:
    assert peer_group_key("provider", ["cardiology", "TX"]) == "provider|cardiology|TX"


def test_z_to_signal_high_clamps_positive_tail() -> None:
    assert z_to_signal(2.0, direction="high", z_cap=4.0) == 0.5
    assert z_to_signal(-3.0, direction="high", z_cap=4.0) == 0.0
    assert z_to_signal(10.0, direction="high", z_cap=4.0) == 1.0


def test_z_to_signal_low_uses_negative_tail() -> None:
    assert z_to_signal(-2.0, direction="low", z_cap=4.0) == 0.5
    assert z_to_signal(2.0, direction="low", z_cap=4.0) == 0.0


def test_z_to_signal_two_sided_uses_abs() -> None:
    assert z_to_signal(-2.0, direction="two_sided", z_cap=4.0) == 0.5
    assert z_to_signal(2.0, direction="two_sided", z_cap=4.0) == 0.5
