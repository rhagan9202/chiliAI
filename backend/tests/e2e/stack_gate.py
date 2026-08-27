"""Decide whether the live-stack e2e tests may run.

Kept as a module rather than inlined in each test file so all three live-stack
suites share one gate, and so the decision itself is testable without a stack.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import NoReturn

import pytest

__all__ = ["StackProbe", "resolve_stack", "stack_is_required"]

# (status_code, body) for a GET of the given path, or a raised exception when
# nothing is listening.
StackProbe = Callable[[str], tuple[int, str]]


def stack_is_required() -> bool:
    """True when a missing stack must fail rather than skip.

    CI sets this. Without it a job that starts no application containers
    reports success while every live-stack test quietly skips.
    """
    return os.environ.get("CHILI_E2E_REQUIRE_STACK", "") not in ("", "0")


def _unavailable(reason: str) -> NoReturn:
    if stack_is_required():
        pytest.fail(
            f"{reason} CHILI_E2E_REQUIRE_STACK is set, so this is a failure "
            "rather than a skip: the stack was expected to be running."
        )
    pytest.skip(f"{reason} Start it with `make dev`.")


def resolve_stack(base_url: str, *, probe: StackProbe) -> str:
    """Return ``base_url`` once a chiliAI stack is confirmed to answer there."""
    try:
        health_status, _ = probe("/health")
    except Exception:  # noqa: BLE001 - any connection failure means "no stack"
        _unavailable(f"No stack answering at {base_url}.")
    if health_status != 200:
        _unavailable(f"Stack at {base_url} is not healthy.")

    # A bare /health check accepts any service that happens to hold the port —
    # another project's API returns its own {"status": "ok"} and the suite then
    # asserts against a foreign service. Confirm this is chiliAI by asking for
    # a route only chiliAI serves.
    try:
        domain_status, body = probe("/config/domain")
    except Exception:  # noqa: BLE001
        _unavailable(f"No stack answering at {base_url}.")
    if domain_status != 200:
        _unavailable(
            f"The service at {base_url} answered /health but not /config/domain, "
            "so it is not a chiliAI API."
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict) or "domain" not in payload:
        _unavailable(
            f"The service at {base_url} did not return a domain config, "
            "so it is not a chiliAI API."
        )
    return base_url
