"""Tests for the monitoring exception hierarchy."""

from __future__ import annotations

import pytest

from monitoring.exceptions import (
    AlertAlreadyResolvedError,
    AlertLifecycleError,
    AlertNotFoundError,
    MonitoringConfigurationError,
    MonitoringError,
    MonitoringSourceError,
)


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


@pytest.mark.parametrize(
    "exc_cls",
    [MonitoringConfigurationError, MonitoringSourceError],
)
def test_subclasses_extend_monitoring_error(exc_cls: type[MonitoringError]) -> None:
    assert issubclass(exc_cls, MonitoringError)
