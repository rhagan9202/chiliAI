"""get_risk_signal_source selects the backend by configured database."""

from __future__ import annotations

import pytest

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.postgres import PostgresRiskSignalSource
from api import dependencies


def test_in_memory_when_no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies.get_risk_signal_source.cache_clear()
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)
    source = dependencies.get_risk_signal_source()
    assert isinstance(source, InMemoryRiskSignalSource)
    dependencies.get_risk_signal_source.cache_clear()


def test_postgres_when_provider_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies.get_risk_signal_source.cache_clear()

    class _Provider:
        def connection(self) -> object:  # pragma: no cover - not invoked here
            raise NotImplementedError

        def close(self) -> None:  # pragma: no cover - not invoked here
            return None

    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: _Provider())
    source = dependencies.get_risk_signal_source()
    assert isinstance(source, PostgresRiskSignalSource)
    dependencies.get_risk_signal_source.cache_clear()
