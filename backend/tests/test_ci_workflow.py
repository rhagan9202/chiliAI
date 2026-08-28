"""Guards for the CI workflow's own correctness.

A workflow step is code that runs nowhere else, so nothing catches it drifting
from the stack it describes. Two ways it did:

* the backend job started ``api`` and ``worker`` and then called
  ``scripts/wait_for_stack.sh`` with no arguments — whose defaults require the
  Vite app on ``:5173``, a container that job never starts and that nothing
  pulls in (``app`` depends on ``api``, not the reverse). The step could only
  spin and exit 1, and the ``e2e`` job ``needs`` it, so the Playwright suite
  still never ran.
* the ``e2e`` job's comment quoted a spec count that matched no measurement.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_WORKFLOW = _REPO_ROOT / ".github/workflows/ci.yml"
_WAIT_SCRIPT = _REPO_ROOT / "scripts/wait_for_stack.sh"
_E2E_SPEC_DIR = _REPO_ROOT / "chili_app/e2e"

# Which compose service has to be running for a localhost port to answer.
_PORT_OWNER: dict[str, str] = {"8000": "api", "5173": "app"}


def _workflow() -> dict[str, object]:
    with _CI_WORKFLOW.open("rb") as handle:
        return cast(dict[str, object], yaml.safe_load(handle))


def _job(job_id: str) -> dict[str, object]:
    jobs = cast(dict[str, object], _workflow()["jobs"])
    return cast(dict[str, object], jobs[job_id])


def _step_run(job_id: str, step_name: str) -> str:
    steps = cast(list[dict[str, object]], _job(job_id)["steps"])
    for step in steps:
        if step.get("name") == step_name:
            return str(step["run"])
    raise AssertionError(f"job '{job_id}' has no step named '{step_name}'")


def _wait_script_defaults() -> list[str]:
    """The URLs the script polls when a caller passes none."""
    text = _WAIT_SCRIPT.read_text()
    return re.findall(r'"\$\{[12]:-([^}]+)\}"', text)


def _started_compose_services(run_script: str) -> set[str]:
    services: set[str] = set()
    for command in re.findall(
        r"docker compose[^\n]*up[^\n]*", run_script.replace("\\\n", " ")
    ):
        tokens = command.split()
        # Service names are the trailing bare words after the last flag/value.
        for token in reversed(tokens):
            if token.startswith("-") or token.endswith((".yaml", ".yml")):
                break
            services.add(token)
    return services - {"up", "-d", "--build", "--wait"}


def _waited_urls(run_script: str) -> list[str]:
    match = re.search(
        r"scripts/wait_for_stack\.sh((?:[^\n\\]|\\\n)*)", run_script
    )
    assert match is not None, "the step no longer calls scripts/wait_for_stack.sh"
    arguments = match.group(1).replace("\\\n", " ").split()
    return arguments or _wait_script_defaults()


def test_the_backend_job_only_waits_on_services_it_starts() -> None:
    run_script = _step_run("backend", "Bring up the service stack")
    started = _started_compose_services(run_script)

    unreachable = [
        url
        for url in _waited_urls(run_script)
        for port in re.findall(r"localhost:(\d+)", url)
        if _PORT_OWNER.get(port, "") not in started
    ]

    assert not unreachable, (
        "the backend job waits for URLs served by containers it never starts, "
        f"so the step can only time out and fail: {unreachable} "
        f"(started: {sorted(started)})"
    )


def test_the_e2e_job_quotes_the_real_spec_file_count() -> None:
    e2e_job = _job("e2e")
    steps = cast(list[dict[str, object]], e2e_job["steps"])
    commentary = "\n".join(str(step.get("name", "")) for step in steps)
    commentary += "\n" + _CI_WORKFLOW.read_text()
    quoted = re.search(r"(\d+) spec files, (\d+) test cases", commentary)

    assert quoted is not None, (
        "the e2e job no longer states how many specs it runs as "
        "'<N> spec files, <M> test cases', so the claim cannot be checked"
    )
    actual_files = len(list(_E2E_SPEC_DIR.glob("*.spec.ts")))
    assert int(quoted.group(1)) == actual_files, (
        f"the e2e job claims {quoted.group(1)} spec files but the suite has "
        f"{actual_files}"
    )
    # A static count of top-level `test(` calls undercounts specs that declare
    # cases in a loop, so it is a floor for the quoted number, not an equality.
    static_floor = sum(
        len(re.findall(r"^\s*test\(", spec.read_text(), flags=re.MULTILINE))
        for spec in _E2E_SPEC_DIR.glob("*.spec.ts")
    )
    assert int(quoted.group(2)) >= static_floor, (
        f"the e2e job claims {quoted.group(2)} test cases but at least "
        f"{static_floor} are declared literally"
    )
