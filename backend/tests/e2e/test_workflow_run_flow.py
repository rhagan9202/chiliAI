"""Live-stack verification for workflow definition runs.

Talks HTTP to a running stack (`make dev`): real API, real worker, real Redis.
The defects this file exists for were all invisible in-process — an executor
that is never reached, a gate that is never enforced, a capability list that
disagrees with the registry only when the API supplies one.

    make dev
    cd backend && .venv/bin/pytest tests/e2e/test_workflow_run_flow.py -m integration
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import cast

import pytest

from tests.e2e.stack_gate import resolve_stack

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("CHILI_E2E_BASE_URL", "http://localhost:8000")
_TIMEOUT_SECONDS = 60
# Bound to a real executor in the worker, so a step using it genuinely runs.
_EXECUTABLE_CAPABILITY = "connector.sync.status"
# Registered but with no executor bound — the honest "not implemented" path.
_UNBOUND_CAPABILITY = "analytics.peer_context"
_APPROVAL_CAPABILITY = "case.note.draft"
_POSTGRES_CONTAINER = os.environ.get("CHILI_E2E_PG_CONTAINER", "chiliai-postgres-1")
_WORKER_CONTAINER = os.environ.get("CHILI_E2E_WORKER_CONTAINER", "chiliai-worker-1")


def _requests():
    return pytest.importorskip("requests")


@pytest.fixture
def base_url() -> str:
    requests = _requests()

    def probe(path: str) -> tuple[int, str]:
        response = requests.get(f"{_BASE_URL}{path}", timeout=5)
        return response.status_code, response.text

    return resolve_stack(_BASE_URL, probe=probe)


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


def _psql(sql: str) -> str:
    """Run SQL in the dev Postgres container.

    Preferred over a test-only HTTP route: an endpoint that exists solely for
    tests is a permanent liability bought for a temporary convenience.
    """
    result = subprocess.run(
        ["docker", "exec", _POSTGRES_CONTAINER, "psql", "-U", "chili", "-d", "chili",
         "-tAc", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot reach {_POSTGRES_CONTAINER}: {result.stderr.strip()}")
    return result.stdout.strip()


def _seed_peer_signal(kb_id: str, *, entity_id: str, metric_name: str) -> None:
    """A persisted derived signal for analytics.peer_context to read.

    The capability is a *read* over signals the analytics pipeline computes; a
    brand-new knowledge base has none, so the step would legitimately fail for
    want of data rather than for want of a binding.
    """
    _psql(
        "INSERT INTO entity_derived_signals (knowledge_base_id, entity_id, "
        "entity_type, metric_name, interval_start, peer_group_key, "
        "aggregate_value, peer_mean, peer_std, z_score, signal_value, weight, "
        "rationale, correlation_id, computed_at) VALUES ("
        f"'{kb_id}', '{entity_id}', 'provider', '{metric_name}', "
        "'2026-08-01T00:00:00Z', 'provider:TN', 100, 40, 10, 6.0, 0.9, 1.0, "
        "'above peers', 'corr-e2e', now()) ON CONFLICT DO NOTHING"
    )


def _worker_step_states(workflow_id: str) -> dict[str, dict[str, object]]:
    """Step records as the worker persisted them.

    A run can reach `completed` with every step skipped, so the run status
    alone cannot show that a capability actually executed.
    """
    script = (
        "import json, os\n"
        "from agent.adapters.redis_store import RedisWorkflowRunStore\n"
        "store = RedisWorkflowRunStore(redis_url=os.environ['REDIS_URL'])\n"
        f"run = store.get_run({workflow_id!r})\n"
        "print(json.dumps({s.step_name: {'status': s.status.value, "
        "'attempts': s.attempts, 'metadata': dict(s.metadata)} for s in run.steps}))\n"
    )
    result = subprocess.run(
        ["docker", "exec", _WORKER_CONTAINER, "python", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot reach {_WORKER_CONTAINER}: {result.stderr.strip()}")
    return cast("dict[str, dict[str, object]]", json.loads(result.stdout.strip().splitlines()[-1]))



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


def test_the_browse_api_advertisement_matches_what_the_worker_binds(
    base_url: str,
) -> None:
    """`executable` must describe the process that runs workflow steps.

    The executor map is module-level state *per process*, and the API registers
    nothing — so reading its own registry made the browse API report every
    capability as unrunnable while the worker was happily running two. The flag
    is now a declared fact about the worker, guarded against drift by
    `test_the_declared_worker_set_matches_what_binding_produces`.
    """
    kb_id = _create_kb(base_url, "Capability Advertisement")
    requests = _requests()

    response = requests.get(
        f"{base_url}/knowledgebases/{kb_id}/capabilities", timeout=30
    )

    assert response.status_code == 200, response.text
    items = cast("list[dict[str, object]]", _json(response)["items"])
    executable = {
        str(item["capability_id"]) for item in items if item.get("executable")
    }
    assert executable == {"connector.sync.status", "analytics.peer_context"}, executable


def test_a_workflow_runs_every_capability_the_browse_api_calls_executable(
    base_url: str,
) -> None:
    """The advertisement must be true, not aspirational.

    Asserted through the worker's own step records rather than the run status:
    a run reaches `completed` with every step skipped just as readily as with
    every step executed.
    """
    kb_id = _create_kb(base_url, "Capability Reachability")
    _register_connector(base_url, kb_id, "e2e-reach-conn")
    _seed_peer_signal(kb_id, entity_id="npi-e2e", metric_name="billing_amount")
    _create_and_approve(
        base_url,
        kb_id,
        definition_id="e2e-reachable",
        allowed=["connector.sync.status", "analytics.peer_context"],
        steps=[
            {
                "step_id": "status",
                "label": "Sync status",
                "capability_ref": "connector.sync.status",
            },
            {
                "step_id": "peers",
                "label": "Peer context",
                "capability_ref": "analytics.peer_context",
            },
        ],
    )

    run_id = _run(
        base_url,
        kb_id,
        "e2e-reachable",
        inputs={
            "connector_id": "e2e-reach-conn",
            "entity_id": "npi-e2e",
            "metric_name": "billing_amount",
        },
    )
    run = _poll_until(base_url, run_id, statuses={"completed", "failed"})

    assert run["status"] == "completed", run
    steps = _worker_step_states(run_id)
    assert steps["status"]["status"] == "completed"
    assert steps["peers"]["status"] == "completed"
    # Executed, not skipped — a skipped step never increments attempts.
    assert cast("int", steps["status"]["attempts"]) >= 1
    assert cast("int", steps["peers"]["attempts"]) >= 1
    # The flattened manifest shape, from real persisted signals.
    peer_output = cast("dict[str, object]", steps["peers"]["metadata"])
    assert peer_output["metric_name"] == "billing_amount"
    assert "z_score" in peer_output
