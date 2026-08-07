"""Guards that executors are actually reachable from the worker.

Every other test in this suite imports an executor module directly, which
registers its handler as a side effect. That hides the failure mode this file
exists for: if nothing on the worker's import path pulls the executor modules
in, `dispatch` finds an empty registry and silently returns 0 for every event.
The seam would be wired and dead — and every unit test would still pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_EXPECTED = {"score.batch.queued", "score.run.queued"}


def _registered_after(import_statement: str) -> set[str]:
    """Register in a *fresh* interpreter, so no other test's import can mask it."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"{import_statement}\n"
            "from execution.registry import registered_event_types\n"
            "print(','.join(sorted(registered_event_types())))",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    printed = result.stdout.strip().splitlines()[-1]
    return set(filter(None, printed.split(",")))


def test_importing_the_execution_package_registers_every_executor() -> None:
    assert _EXPECTED <= _registered_after("import execution")


def test_loading_the_worker_registers_every_executor() -> None:
    """The path that actually matters in production."""
    assert _EXPECTED <= _registered_after("import agent.coordinator")


def test_worker_subscribes_to_every_registered_executor_event() -> None:
    """A registered executor that the worker never subscribes to is also dead."""
    registered = _registered_after("import agent.coordinator")
    subscribed = _registered_after(
        "import agent.coordinator\n"
        "from agent.coordinator import WORKER_EVENT_TYPES\n"
        "import execution.registry as r\n"
        "r._HANDLERS = {k: v for k, v in r._HANDLERS.items() if k in WORKER_EVENT_TYPES}"
    )
    assert registered == subscribed, (
        f"registered but never delivered: {sorted(registered - subscribed)}"
    )
