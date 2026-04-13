"""Exception hierarchy for the timeseries analytics module."""

from __future__ import annotations


class TimeseriesError(Exception):
    """Base exception for timeseries module failures."""


class TimeseriesConfigurationError(TimeseriesError):
    """Raised when a timeseries request is invalid or incomplete."""


class TimeseriesInsufficientHistoryError(TimeseriesError):
    """Raised when a series does not contain enough observations for analysis."""


class TimeseriesSourceError(TimeseriesError):
    """Raised when the configured series source cannot return observations."""


__all__ = [
    "TimeseriesConfigurationError",
    "TimeseriesError",
    "TimeseriesInsufficientHistoryError",
    "TimeseriesSourceError",
]