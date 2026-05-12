"""Tests for shared alert helpers."""

from __future__ import annotations

import pytest

from shared.alerts import normalize_severity


@pytest.mark.parametrize(
    ("raw_severity", "expected"),
    [
        ("low", "low"),
        ("MEDIUM", "medium"),
        ("High", "high"),
        ("critical", "critical"),
    ],
)
def test_normalize_severity_preserves_valid_values(
    raw_severity: str,
    expected: str,
) -> None:
    """Explicit valid severities remain authoritative."""

    assert normalize_severity(raw_severity, 0.99) == expected


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.95, "critical"),
        (0.9, "critical"),
        (0.89, "high"),
        (0.75, "high"),
        (0.74, "medium"),
        (0.5, "medium"),
        (0.49, "low"),
    ],
)
def test_normalize_severity_falls_back_to_confidence(
    confidence: float,
    expected: str,
) -> None:
    """Unknown severities derive from alert confidence thresholds."""

    assert normalize_severity("unknown", confidence) == expected
