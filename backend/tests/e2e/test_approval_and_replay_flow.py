"""Live-stack verification for approval resume, score replay and reconciliation.

Talks HTTP to a running stack (`make dev`). Each test here covers a path that
accepted work and silently never did it — and every one was invisible to a
green unit suite, because an in-process test invokes the machinery directly and
so can never discover that nothing reaches it.

    make dev
    cd backend && .venv/bin/pytest tests/e2e/test_approval_and_replay_flow.py -m integration
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import cast

import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("CHILI_E2E_BASE_URL", "http://localhost:8000")
_TIMEOUT_SECONDS = 90
_GATED_CAPABILITY = "connector.sync.status"
_POSTGRES_CONTAINER = os.environ.get("CHILI_E2E_PG_CONTAINER", "chiliai-postgres-1")
_WORKER_CONTAINER = os.environ.get("CHILI_E2E_WORKER_CONTAINER", "chiliai-worker-1")


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


def _psql(sql: str) -> str:
    """Run SQL in the dev Postgres container.

    Ugly, and deliberately preferred over a test-only HTTP route: a
    production endpoint that exists solely for tests is a permanent liability
    bought for a temporary convenience.
    """
    result = subprocess.run(
        ["docker", "exec", _POSTGRES_CONTAINER, "psql", "-U", "chili", "-d", "chili", "-tAc", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot reach {_POSTGRES_CONTAINER}: {result.stderr.strip()}")
    return result.stdout.strip()


def _reassign_requester(workflow_id: str, actor_user_id: str) -> None:
    """Give a run a different requester than the approver.

    The dev stack authenticates every caller as one anonymous identity, so
    without this the self-approval guard (correctly) refuses — and the resume
    path cannot be exercised at all.
    """
    script = (
        "import os\n"
        "from agent.adapters.redis_store import RedisWorkflowRunStore\n"
        "store = RedisWorkflowRunStore(redis_url=os.environ['REDIS_URL'])\n"
        f"run = store.get_run({workflow_id!r})\n"
        f"store.save_run(run.model_copy(update={{'actor_user_id': {actor_user_id!r}}}))\n"
    )
    result = subprocess.run(
        ["docker", "exec", _WORKER_CONTAINER, "python", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot reach {_WORKER_CONTAINER}: {result.stderr.strip()}")


def _create_kb(base_url: str, name: str) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases",
        json={"name": name, "description": "approval e2e"},
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
            "name": "E2E Connector",
            "source_type": "filesystem",
            "schedule": {"mode": "manual"},
            "mapping": {"mapping_id": "m", "mapping_version": "v1", "feed_name": "carrier_claims_a"},
            "config": {"path": "/imports"},
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text


def _gated_run(base_url: str, kb_id: str, connector_id: str, suffix: str) -> str:
    """An approved definition whose only step is behind an approval gate."""
    requests = _requests()
    definition_id = f"e2e-gated-{suffix}"
    created = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions",
        json={
            "definition_id": definition_id,
            "name": definition_id,
            "version": "v1",
            "allowed_capability_refs": [_GATED_CAPABILITY],
            "steps": [
                {
                    "step_id": "gate",
                    "label": "Gated check",
                    "capability_ref": _GATED_CAPABILITY,
                    "requires_human_approval": True,
                }
            ],
        },
        timeout=30,
    )
    assert created.status_code == 200, created.text
    base = (
        f"{base_url}/knowledgebases/{kb_id}/workflow-definitions/"
        f"{definition_id}/versions/v1"
    )
    assert requests.post(f"{base}/approve", timeout=30).status_code == 200
    started = requests.post(
        f"{base}/run",
        json={
            "target_type": "knowledge_base",
            "target_id": kb_id,
            "inputs": {"connector_id": connector_id},
            "idempotency_key": f"{definition_id}-{int(time.time())}",
        },
        timeout=30,
    )
    assert started.status_code == 200, started.text
    run_id = _json(started)["id"]
    assert isinstance(run_id, str)
    return run_id


def _poll_workflow(base_url: str, run_id: str, *, statuses: set[str]) -> dict[str, object]:
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
    pytest.fail(f"Run {run_id} never reached {sorted(statuses)}; last seen: {last}")


def test_a_parked_run_resumes_after_approval(base_url: str) -> None:
    """The gap this plan exists for.

    Parking was a dead end at both ends: nothing wrote the approval, and the
    parking event had already been acked so no event existed to resume from.
    """
    kb_id = _create_kb(base_url, "Approval E2E Resume")
    _register_connector(base_url, kb_id, "e2e-approval-conn")
    run_id = _gated_run(base_url, kb_id, "e2e-approval-conn", "resume")

    parked = _poll_workflow(base_url, run_id, statuses={"awaiting_approval"})
    assert parked["status"] == "awaiting_approval"

    _reassign_requester(run_id, "analyst-1")
    requests = _requests()
    approved = requests.post(
        f"{base_url}/workflows/{run_id}/steps/gate/approve", json={}, timeout=30
    )
    assert approved.status_code == 200, approved.text
    # Released to queued, not running: the executor claims the step itself.
    assert _json(approved)["status"] == "queued"

    resumed = _poll_workflow(base_url, run_id, statuses={"completed", "failed"})
    assert resumed["status"] == "completed", resumed


def test_the_requester_cannot_approve_their_own_run(base_url: str) -> None:
    """A gate an actor can satisfy for their own run is not a gate.

    No requester reassignment here: the dev stack authenticates everyone as the
    same anonymous identity, which is exactly the collision this guard blocks.
    """
    kb_id = _create_kb(base_url, "Approval E2E Self")
    _register_connector(base_url, kb_id, "e2e-self-conn")
    run_id = _gated_run(base_url, kb_id, "e2e-self-conn", "self")
    _poll_workflow(base_url, run_id, statuses={"awaiting_approval"})

    requests = _requests()
    response = requests.post(
        f"{base_url}/workflows/{run_id}/steps/gate/approve", json={}, timeout=30
    )

    assert response.status_code == 409, response.text
    assert "own" in response.text


def test_rejecting_a_parked_run_fails_it_with_the_reason(base_url: str) -> None:
    kb_id = _create_kb(base_url, "Approval E2E Reject")
    _register_connector(base_url, kb_id, "e2e-reject-conn")
    run_id = _gated_run(base_url, kb_id, "e2e-reject-conn", "reject")
    _poll_workflow(base_url, run_id, statuses={"awaiting_approval"})
    requests = _requests()

    missing_reason = requests.post(
        f"{base_url}/workflows/{run_id}/steps/gate/reject", json={}, timeout=30
    )
    rejected = requests.post(
        f"{base_url}/workflows/{run_id}/steps/gate/reject",
        json={"reason": "insufficient evidence"},
        timeout=30,
    )

    # A rejection with no reason is an audit record that explains nothing.
    assert missing_reason.status_code == 422
    assert rejected.status_code == 200, rejected.text
    assert _json(rejected)["status"] == "failed"
    assert _json(rejected)["last_error"] == "insufficient evidence"


def test_a_replayed_score_run_executes(base_url: str) -> None:
    """Live-confirmed broken 2026-08-07: the replayed run stayed queued forever.

    `replay_failed_batches` published only a status *notification*, which the
    worker does not consume, so the replay was inert.
    """
    requests = _requests()
    completed = _psql(
        "select id, knowledge_base_id from score_runs "
        "where status = 'completed' order by created_at desc limit 1"
    )
    if not completed:
        pytest.skip("No completed score run available to replay.")
    run_id, kb_id = completed.split("|")

    _psql(
        f"update score_batches set status='failed' where run_id='{run_id}'; "
        f"update score_runs set status='failed' where id='{run_id}'"
    )
    replayed = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/score-runs/{run_id}/replay",
        json={"requested_by": "e2e"},
        timeout=30,
    )
    assert replayed.status_code == 200, replayed.text
    replay_id = cast("dict[str, object]", _json(replayed)["run"])["id"]

    deadline = time.monotonic() + _TIMEOUT_SECONDS
    status = ""
    while time.monotonic() < deadline:
        status = _psql(
            "select status || '|' || scored_entities || '|' || failed_entities || "
            "'|' || skipped_entities || '|' || total_entities "
            f"from score_runs where id='{replay_id}'"
        )
        if status.startswith(("completed", "failed")):
            break
        time.sleep(3)

    state, scored, failed, skipped, total = status.split("|")
    assert state == "completed", status
    # The three counters must partition the run. This assertion used to be
    # `scored + failed == total`, which held only because `failed` was a
    # remainder that swallowed every skipped entity — the run this test drives
    # scores nothing and skips all 57.
    assert int(scored) + int(failed) + int(skipped) == int(total), status


def test_a_stalled_connector_sync_run_is_reconciled(base_url: str) -> None:
    """A run whose page event is lost used to stay `running` forever.

    Ages the run past the stale window and waits for the worker tick. The
    window defaults to 24h and the tick to 60s, so this ages by 30h rather
    than sleeping through a real window.
    """
    kb_id = _create_kb(base_url, "Approval E2E Reconcile")
    _register_connector(base_url, kb_id, "e2e-stale-conn")
    requests = _requests()
    started = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors/e2e-stale-conn/sync-runs",
        json={"idempotency_key": f"e2e-stale-{int(time.time())}"},
        timeout=30,
    )
    assert started.status_code == 200, started.text
    run_id = _json(started)["run_id"]

    _psql(
        "update connector_sync_runs set status='running', "
        f"updated_at = now() - interval '30 hours' where run_id='{run_id}'"
    )

    deadline = time.monotonic() + _TIMEOUT_SECONDS
    row = ""
    while time.monotonic() < deadline:
        row = _psql(
            "select status || '|' || coalesce(error_message, '') "
            f"from connector_sync_runs where run_id='{run_id}'"
        )
        if row.startswith("failed"):
            break
        time.sleep(5)

    assert row.startswith("failed"), row
    assert "stale_connector_sync_reconciled" in row
