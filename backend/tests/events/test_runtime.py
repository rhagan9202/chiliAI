"""Event bus runtime settings loaded from the environment."""

from __future__ import annotations

import pytest

from events.runtime import EventBusSettings, load_event_bus_settings

class TestPendingEntryReclaimIsOnByDefault:
    """Redis Streams redelivery is opt-out, not opt-in.

    A worker that is killed mid-batch leaves every entry it read in the
    consumer group's PEL. ``reclaim_stale_pending`` is the only code that
    issues XAUTOCLAIM, and it is skipped entirely when ``reclaim_min_idle_ms``
    is ``None`` — so with no default those documents stop mid-pipeline and the
    only downstream signal is stale reconciliation failing the run an hour
    later.
    """

    def test_the_default_enables_reclaim(self) -> None:
        assert EventBusSettings().reclaim_min_idle_ms is not None

    def test_the_default_is_loaded_when_the_env_var_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CHILI_EVENT_RECLAIM_MIN_IDLE_MS", raising=False)

        settings = load_event_bus_settings()

        assert settings.reclaim_min_idle_ms is not None
        assert settings.reclaim_min_idle_ms > 0

    def test_an_explicit_env_value_still_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_EVENT_RECLAIM_MIN_IDLE_MS", "5000")

        assert load_event_bus_settings().reclaim_min_idle_ms == 5000

    def test_reclaim_can_still_be_disabled_explicitly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Operators keep an escape hatch, but must ask for it."""
        monkeypatch.setenv("CHILI_EVENT_RECLAIM_MIN_IDLE_MS", "0")

        assert load_event_bus_settings().reclaim_min_idle_ms is None
