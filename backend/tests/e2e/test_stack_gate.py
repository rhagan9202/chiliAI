"""The gate that decides whether the live-stack e2e tests run or are skipped.

Two failure modes this guards against, both of which report success today:

1. In CI no application containers are started, so every live-stack test
   self-skips and the job goes green having verified nothing. A skip must be
   loud where the stack is *supposed* to exist.
2. The probe accepts whatever answers on the port. Another project's API on
   ``localhost:8000`` returns ``{"status": "ok"}`` from its own ``/health``,
   and the suite then asserts against a foreign service.
"""

from __future__ import annotations

import pytest
from _pytest.outcomes import Failed, Skipped

from tests.e2e.stack_gate import StackProbe, resolve_stack


def _chili_stack(*, healthy: bool = True, is_chili: bool = True) -> StackProbe:
    def probe(path: str) -> tuple[int, str]:
        if path == "/health":
            return (200, '{"status":"ok"}') if healthy else (503, "")
        if path == "/config/domain":
            return (200, '{"domain":{"name":"medicare_fraud"}}') if is_chili else (404, "")
        return (404, "")

    return probe


def _no_listener(path: str) -> tuple[int, str]:
    raise ConnectionError("connection refused")


class TestTheGateSkipsWhenTheStackIsOptional:
    def test_a_healthy_chili_stack_is_accepted(self) -> None:
        assert resolve_stack("http://localhost:8000", probe=_chili_stack()) == (
            "http://localhost:8000"
        )

    def test_no_listener_skips(self) -> None:
        with pytest.raises(Skipped, match="No stack answering"):
            resolve_stack("http://localhost:8000", probe=_no_listener)


class TestTheGateFailsWhenTheStackIsRequired:
    """``CHILI_E2E_REQUIRE_STACK=1`` turns a silent skip into a failure."""

    def test_no_listener_fails_instead_of_skipping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_E2E_REQUIRE_STACK", "1")

        with pytest.raises(Failed):
            resolve_stack("http://localhost:8000", probe=_no_listener)

    def test_an_unhealthy_stack_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHILI_E2E_REQUIRE_STACK", "1")

        with pytest.raises(Failed):
            resolve_stack(
                "http://localhost:8000", probe=_chili_stack(healthy=False)
            )


class TestTheGateRejectsAForeignService:
    """A different project's API answering the port must not be accepted."""

    def test_a_foreign_healthy_service_is_rejected(self) -> None:
        with pytest.raises(Skipped, match="not a chiliAI"):
            resolve_stack(
                "http://localhost:8000", probe=_chili_stack(is_chili=False)
            )

    def test_a_foreign_service_fails_when_the_stack_is_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_E2E_REQUIRE_STACK", "1")

        with pytest.raises(Failed):
            resolve_stack(
                "http://localhost:8000", probe=_chili_stack(is_chili=False)
            )
