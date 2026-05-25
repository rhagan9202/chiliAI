"""Tests for config-driven monitoring observation-source selection."""

from __future__ import annotations

from api.dependencies import get_connection_provider, get_monitoring_source
from monitoring.adapters.in_memory import InMemoryObservationSource


def test_in_memory_backend_selects_in_memory_source() -> None:
    """The default test config uses database.backend=in_memory."""
    get_connection_provider.cache_clear()
    get_monitoring_source.cache_clear()
    try:
        source = get_monitoring_source()
        assert isinstance(source, InMemoryObservationSource)
    finally:
        get_connection_provider.cache_clear()
        get_monitoring_source.cache_clear()
