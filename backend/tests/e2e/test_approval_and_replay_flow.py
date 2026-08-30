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

from tests.e2e.stack_gate import require_stack_condition, resolve_stack

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("CHILI_E2E_BASE_URL", "http://localhost:8000")
_TIMEOUT_SECONDS = 90
_GATED_CAPABILITY = "connector.sync.status"
_POSTGRES_CONTAINER = os.environ.get("CHILI_E2E_PG_CONTAINER", "chiliai-postgres-1")
_WORKER_CONTAINER = os.environ.get("CHILI_E2E_WORKER_CONTAINER", "chiliai-worker-1")
# Free-form version tags recorded on a score run, not validated against a
# real catalog -- matching the values analytics/score_runs' own unit tests use.
_SCORE_MODEL_VERSION = "risk-linear-v1"
_SCORE_CATALOG_VERSION = "cms-fraud-features-v1"


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
    require_stack_condition(
        result.returncode == 0,
        f"Cannot reach {_POSTGRES_CONTAINER}: {result.stderr.strip()}",
    )
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
    require_stack_condition(
        result.returncode == 0,
        f"Cannot reach {_WORKER_CONTAINER}: {result.stderr.strip()}",
    )


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


def _push_carrier_claims(base_url: str, kb_id: str, *, row_count: int) -> None:
    """Ingest via the JSON api-push route -- no filesystem/bind-mount needed.

    Same feed and column shape ``test_connector_sync_flow.py`` writes as a
    CSV; pushed as JSON here since this file has no reason to depend on the
    worker's ``/imports`` mount just to get entities into the graph.
    """
    requests = _requests()
    rows = [
        {
            "CLM_ID": f"E2ESCORE{index:05d}",
            "DESYNPUF_ID": f"E2ESCOREBENE{index % 3:03d}",
            "PRF_PHYSN_NPI_1": f"E2ESCORENPI{2000000 + index}",
            "CLM_FROM_DT": "20100101",
            "CLM_THRU_DT": "20100105",
            "LINE_NCH_PMT_AMT_1": index * 100,
            "provider_specialty": "internal_medicine",
            "provider_state": "TN",
            "service_mix": "office",
        }
        for index in range(1, row_count + 1)
    ]
    response = requests.post(
        f"{base_url}/records/{kb_id}/push",
        json={"feed_name": "carrier_claims_a", "rows": rows},
        timeout=30,
    )
    assert response.status_code == 202, response.text


def _poll_kb_entity_count(base_url: str, kb_id: str, *, minimum: int) -> None:
    """Wait for the records workflow to land entities in the graph.

    ``GET /knowledgebases/{id}`` recomputes ``entity_count`` live from graph
    metrics on every read (see ``api/_kb_projection.py``), so this needs no
    docker exec -- an HTTP poll is enough to know the ingest landed.
    """
    requests = _requests()
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = requests.get(f"{base_url}/knowledgebases/{kb_id}", timeout=30)
        assert response.status_code == 200, response.text
        last = _json(response)
        entity_count = last.get("entity_count")
        if isinstance(entity_count, int) and entity_count >= minimum:
            return
        time.sleep(2)
    pytest.fail(
        f"KB {kb_id} never reached {minimum} entities in {_TIMEOUT_SECONDS}s; "
        f"last seen: {last}"
    )


def _start_score_run(base_url: str, kb_id: str, *, idempotency_key: str) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/score-runs",
        json={
            "model_version": _SCORE_MODEL_VERSION,
            "catalog_version": _SCORE_CATALOG_VERSION,
            "idempotency_key": idempotency_key,
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    run = cast("dict[str, object]", _json(response)["run"])
    run_id = run["id"]
    assert isinstance(run_id, str)
    return run_id


def _poll_score_run(
    base_url: str, kb_id: str, run_id: str, *, statuses: set[str]
) -> dict[str, object]:
    requests = _requests()
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = requests.get(
            f"{base_url}/knowledgebases/{kb_id}/score-runs/{run_id}", timeout=30
        )
        assert response.status_code == 200, response.text
        last = cast("dict[str, object]", _json(response)["run"])
        if last.get("status") in statuses:
            return last
        time.sleep(2)
    pytest.fail(
        f"Score run {run_id} never reached {sorted(statuses)} in {_TIMEOUT_SECONDS}s; "
        f"last seen: {last}"
    )


def test_a_replayed_score_run_executes(base_url: str) -> None:
    """Live-confirmed broken 2026-08-07: the replayed run stayed queued forever.

    `replay_failed_batches` published only a status *notification*, which the
    worker does not consume, so the replay was inert.

    Drives its own completed score run rather than scavenging the `score_runs`
    table for one left behind by another test. Nothing in the pipeline creates
    a `score_runs` row as a side effect of ingest -- that's a *different*,
    per-entity analytics fan-out (`assess_entities`/the risk service, fired
    from `agent/coordinator.py`'s records handler), not the batch-oriented
    score-all runs this feature replays. Scavenging previously depended on
    pytest's collection order placing the one test that ingests real data
    (`test_connector_sync_flow.py::test_connector_sync_ingests_records_end_to_end`)
    before this one -- true only by accident, and false in CI, which brings up
    a fresh Postgres with no seed step between `alembic upgrade head` and
    pytest. See cicd.22.
    """
    requests = _requests()
    kb_id = _create_kb(base_url, "Approval E2E Score Replay")
    _push_carrier_claims(base_url, kb_id, row_count=10)
    _poll_kb_entity_count(base_url, kb_id, minimum=1)

    run_id = _start_score_run(
        base_url, kb_id, idempotency_key=f"e2e-score-{int(time.time())}"
    )
    initial = _poll_score_run(base_url, kb_id, run_id, statuses={"completed", "failed"})
    assert initial["status"] == "completed", initial

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
    # remainder that swallowed every skipped entity. The "all 57 skipped"
    # this once named belonged to the run scavenged from the connector-sync
    # test's CSV; this test drives its own much smaller run, so assert the
    # partition invariant itself rather than any particular count.
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
