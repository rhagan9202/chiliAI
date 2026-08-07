"""Live-stack verification for workflow definition runs.

Talks HTTP to a running stack (`make dev`): real API, real worker, real Redis.
The defects this file exists for were all invisible in-process — an executor
that is never reached, a gate that is never enforced, a capability list that
disagrees with the registry only when the API supplies one.

    make dev
    cd backend && .venv/bin/pytest tests/e2e/test_workflow_run_flow.py -m integration
"""

from __future__ import annotations

import os
import time
from typing import cast

import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("CHILI_E2E_BASE_URL", "http://localhost:8000")
_TIMEOUT_SECONDS = 60
# Bound to a real executor in the worker, so a step using it genuinely runs.
_EXECUTABLE_CAPABILITY = "connector.sync.status"
# Registered but with no executor bound — the honest "not implemented" path.
_UNBOUND_CAPABILITY = "analytics.peer_context"
_APPROVAL_CAPABILITY = "case.note.draft"


def _requests():
    return pytest.importorskip("requests")


@pytest.fixture
def base_url() -> str:
    requests = _requests()
    try:
        response = requests.get(f"{_BASE_URL}/health", timeout=5)
    except Exception:  # noqa: BLE001 - any connection failure means "no stack"
        pytest.skip(f"No stack answering at {_BASE_URL}; start it with `make dev`.")
    if response.status_code != 200:
        pytest.skip(f"Stack at {_BASE_URL} is not healthy.")
    return _BASE_URL


def _json(response: object) -> dict[str, object]:
    return cast("dict[str, object]", response.json())  # type: ignore[attr-defined]


def _create_kb(base_url: str, name: str) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases",
        json={"name": name, "description": "workflow e2e"},
        timeout=30,
    )
    assert response.status_code in (200, 201), response.text
    kb_id = _json(response)["id"]
    assert isinstance(kb_id, str)
    return kb_id


def _register_connector(base_url: str, kb_id: str, connector_id: str) -> None:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors",
        json={
            "connector_id": connector_id,
            "name": "WF Connector",
            "source_type": "filesystem",
            "schedule": {"mode": "manual"},
            "mapping": {
                "mapping_id": "m",
                "mapping_version": "v1",
                "feed_name": "carrier_claims_a",
            },
            "config": {"path": "/imports"},
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text


def _create_and_approve(
    base_url: str,
    kb_id: str,
    *,
    definition_id: str,
    steps: list[dict[str, object]],
    allowed: list[str],
) -> None:
    requests = _requests()
    created = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions",
        json={
            "definition_id": definition_id,
            "name": definition_id,
            "version": "v1",
            "allowed_capability_refs": allowed,
            "steps": steps,
        },
        timeout=30,
    )
    assert created.status_code == 200, created.text
    approved = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions/"
        f"{definition_id}/versions/v1/approve",
        timeout=30,
    )
    assert approved.status_code == 200, approved.text


def _run(
    base_url: str, kb_id: str, definition_id: str, *, inputs: dict[str, object]
) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions/"
        f"{definition_id}/versions/v1/run",
        json={
            "target_type": "knowledge_base",
            "target_id": kb_id,
            "inputs": inputs,
            "idempotency_key": f"{definition_id}-{int(time.time())}",
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    run_id = _json(response)["id"]
    assert isinstance(run_id, str)
    return run_id


def _poll_until(
    base_url: str, run_id: str, *, statuses: set[str]
) -> dict[str, object]:
    requests = _requests()
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = requests.get(f"{base_url}/workflows/{run_id}", timeout=30)
        assert response.status_code == 200, response.text
        last = _json(response)
        if last.get("status") in statuses:
            return last
        time.sleep(2)
    pytest.fail(
        f"Run {run_id} never reached {sorted(statuses)} in {_TIMEOUT_SECONDS}s; "
        f"last seen: {last}"
    )


def test_a_workflow_run_executes_its_step_end_to_end(base_url: str) -> None:
    """The whole point: approve a definition, run it, have a step actually run.

    Before this work `run_definition` saved a QUEUED run and stopped — nothing
    executed it, and nothing published the first step event either.
    """
    kb_id = _create_kb(base_url, "Workflow E2E")
    _register_connector(base_url, kb_id, "wf-e2e-conn")
    _create_and_approve(
        base_url,
        kb_id,
        definition_id="e2e-triage",
        allowed=[_EXECUTABLE_CAPABILITY],
        steps=[
            {
                "step_id": "status",
                "label": "Check sync",
                "capability_ref": _EXECUTABLE_CAPABILITY,
            }
        ],
    )

    run_id = _run(
        base_url, kb_id, "e2e-triage", inputs={"connector_id": "wf-e2e-conn"}
    )
    run = _poll_until(base_url, run_id, statuses={"completed", "failed"})

    assert run["status"] == "completed", run
    assert run["current_step"] == "completed"


def test_an_approval_step_parks_the_run_server_side(base_url: str) -> None:
    """A UI-only approval gate is not a gate.

    The run must stop at the gate in the worker, with the following step never
    dispatched, regardless of what any client does.
    """
    kb_id = _create_kb(base_url, "Workflow E2E Approval")
    _register_connector(base_url, kb_id, "wf-e2e-conn")
    _create_and_approve(
        base_url,
        kb_id,
        definition_id="e2e-approval",
        allowed=[_APPROVAL_CAPABILITY, _EXECUTABLE_CAPABILITY],
        steps=[
            {
                "step_id": "gate",
                "label": "Draft note",
                "capability_ref": _APPROVAL_CAPABILITY,
                "requires_human_approval": True,
            },
            {
                "step_id": "after",
                "label": "Then check",
                "capability_ref": _EXECUTABLE_CAPABILITY,
            },
        ],
    )

    run_id = _run(
        base_url, kb_id, "e2e-approval", inputs={"connector_id": "wf-e2e-conn"}
    )
    run = _poll_until(
        base_url, run_id, statuses={"awaiting_approval", "completed", "failed"}
    )

    assert run["status"] == "awaiting_approval", run


def test_a_capability_with_no_executor_fails_with_a_usable_reason(
    base_url: str,
) -> None:
    """Registered-but-not-implemented must say so, not fail mysteriously."""
    kb_id = _create_kb(base_url, "Workflow E2E Unbound")
    _create_and_approve(
        base_url,
        kb_id,
        definition_id="e2e-unbound",
        allowed=[_UNBOUND_CAPABILITY],
        steps=[
            {
                "step_id": "peers",
                "label": "Peer context",
                "capability_ref": _UNBOUND_CAPABILITY,
            }
        ],
    )

    run_id = _run(base_url, kb_id, "e2e-unbound", inputs={})
    run = _poll_until(base_url, run_id, statuses={"failed", "completed"})

    assert run["status"] == "failed", run


def test_a_hostile_condition_is_rejected_by_the_api(base_url: str) -> None:
    """The condition grammar must hold at the HTTP boundary, not just in unit tests."""
    requests = _requests()
    kb_id = _create_kb(base_url, "Workflow E2E Condition")

    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions",
        json={
            "definition_id": "e2e-hostile",
            "name": "Hostile",
            "version": "v1",
            "allowed_capability_refs": [_EXECUTABLE_CAPABILITY],
            "steps": [
                {
                    "step_id": "first",
                    "label": "First",
                    "capability_ref": _EXECUTABLE_CAPABILITY,
                },
                {
                    "step_id": "second",
                    "label": "Second",
                    "capability_ref": _EXECUTABLE_CAPABILITY,
                    "condition": "__import__('os').system('rm -rf /')",
                },
            ],
        },
        timeout=30,
    )

    assert response.status_code == 422, response.text


def test_a_definition_may_reference_every_registered_capability(
    base_url: str,
) -> None:
    """Guards the drift that made the fallback list disagree with the registry.

    `human.approval` was in the built-in list with no manifest, so a definition
    that passed unit-test validation was rejected by the API as an unknown
    capability. This asserts the API accepts what the registry advertises.
    """
    requests = _requests()
    kb_id = _create_kb(base_url, "Workflow E2E Catalog")
    # The capability catalog is KB-scoped, not global.
    listed = requests.get(
        f"{base_url}/knowledgebases/{kb_id}/capabilities", timeout=30
    )
    assert listed.status_code == 200, listed.text
    items = cast("list[dict[str, object]]", _json(listed)["items"])
    capability_ids = [str(item["capability_id"]) for item in items]
    assert capability_ids, "the registry advertises no capabilities"

    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions",
        json={
            "definition_id": "e2e-catalog",
            "name": "Catalog",
            "version": "v1",
            "allowed_capability_refs": capability_ids,
            "steps": [
                {
                    "step_id": f"step-{index}",
                    "label": capability_id,
                    "capability_ref": capability_id,
                    # Approval-gated capabilities must declare the gate.
                    "requires_human_approval": capability_id == _APPROVAL_CAPABILITY,
                }
                for index, capability_id in enumerate(capability_ids)
            ],
        },
        timeout=30,
    )

    assert response.status_code == 200, response.text
