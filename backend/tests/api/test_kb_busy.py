from __future__ import annotations

import pytest

from api._kb_busy import KbBusyError, ensure_kb_idle


def test_idle_kb_does_not_raise() -> None:
    class StubTracker:
        def is_busy(self, kb_id: str) -> bool:
            return False

    ensure_kb_idle("kb-1", tracker=StubTracker())  # no exception


def test_busy_kb_raises() -> None:
    class StubTracker:
        def is_busy(self, kb_id: str) -> bool:
            return True

    with pytest.raises(KbBusyError):
        ensure_kb_idle("kb-1", tracker=StubTracker())
