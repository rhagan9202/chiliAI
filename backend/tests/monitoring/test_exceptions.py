"""Tests for the monitoring exception hierarchy."""

from __future__ import annotations

import pytest

from monitoring.exceptions import (
    AlertAlreadyResolvedError,
    AlertConcurrentModificationError,
    AlertLifecycleError,
    AlertNotFoundError,
    MonitoringConfigurationError,
    MonitoringError,
    MonitoringSourceError,
)
from shared.exceptions import ConcurrentModificationError


def test_alert_lifecycle_error_records_states() -> None:
    err = AlertLifecycleError("open", "resolved")
    assert err.current_status == "open"
    assert err.new_status == "resolved"
    assert isinstance(err, MonitoringError)


def test_alert_not_found_error_attaches_id() -> None:
    err = AlertNotFoundError("a-1")
    assert err.alert_id == "a-1"
    assert isinstance(err, MonitoringError)


def test_alert_already_resolved_error_attaches_id() -> None:
    err = AlertAlreadyResolvedError("a-1")
    assert err.alert_id == "a-1"
    assert isinstance(err, MonitoringError)


def test_alert_concurrent_modification_error_attaches_id_and_both_bases() -> None:
    err = AlertConcurrentModificationError("a-1")
    assert err.alert_id == "a-1"
    assert str(err) == "Alert 'a-1' changed concurrently; reload it and retry."
    # Module-internal callers keep catching it as a MonitoringError, same as
    # every other monitoring exception (matching cases' self-contained
    # hierarchy); a caller that only cares "was this a lost race" -- chiefly
    # the API gateway, and potentially other modules' future concurrency
    # exceptions -- can catch the shared marker base instead.
    assert isinstance(err, MonitoringError)
    assert isinstance(err, ConcurrentModificationError)
    # Distinct in kind from a persistence/source failure: a lost race is
    # always safe to retry, a source failure may not be, and conflating the
    # two by exception type is exactly the bug this task exists to close.
    assert not isinstance(err, MonitoringSourceError)


@pytest.mark.parametrize(
    "exc_cls",
    [MonitoringConfigurationError, MonitoringSourceError],
)
def test_subclasses_extend_monitoring_error(exc_cls: type[MonitoringError]) -> None:
    assert issubclass(exc_cls, MonitoringError)
