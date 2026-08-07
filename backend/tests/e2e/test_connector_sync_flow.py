"""Live-stack verification for connector sync runs.

Unlike ``test_full_pipeline.py``, which drives the coordinator in-process over
in-memory adapters, this talks HTTP to a **running** stack (`make dev`): real
API, real worker, real Redis, real Postgres. That distinction is the point —
the defect this file was written after was invisible to every in-process test,
because the executor was invoked directly and never had to be *reached*.

Skips unless the stack answers, so a normal `pytest` run is unaffected:

    make dev
    cd backend && .venv/bin/pytest tests/e2e/test_connector_sync_flow.py -m integration
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("CHILI_E2E_BASE_URL", "http://localhost:8000")
# Host side of the worker's /imports bind mount (docker-compose.dev.yaml).
_IMPORTS_DIR = Path(
    os.environ.get(
        "CHILI_E2E_CONNECTOR_IMPORTS",
        str(Path(__file__).resolve().parents[3] / "sample_data" / "connector_imports"),
    )
)
# Path as the *worker* sees it, which is what goes in the connector config.
_CONTAINER_ROOT = os.environ.get("CHILI_E2E_CONNECTOR_ROOT", "/imports")
_FEED = os.environ.get("CHILI_E2E_CONNECTOR_FEED", "carrier_claims_a")
_ROW_COUNT = 25
_TIMEOUT_SECONDS = 120

_HEADER = (
    "CLM_ID,DESYNPUF_ID,PRF_PHYSN_NPI_1,CLM_FROM_DT,CLM_THRU_DT,"
    "LINE_NCH_PMT_AMT_1,provider_specialty,provider_state,service_mix\n"
)


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


@pytest.fixture
def csv_file() -> Iterator[str]:
    """Write a feed-conformant CSV into the worker's import directory."""

    if not _IMPORTS_DIR.is_dir():
        pytest.skip(
            f"{_IMPORTS_DIR} does not exist; it is the host side of the worker's "
            f"{_CONTAINER_ROOT} mount."
        )
    name = f"e2e-carrier-{int(time.time())}.csv"
    target = _IMPORTS_DIR / name
    rows = "".join(
        f"E2ECLM{index:05d},E2EBENE{index % 7:03d},E2ENPI{1000000 + index},"
        f"20100101,20100105,{index * 100},internal_medicine,TN,office\n"
        for index in range(1, _ROW_COUNT + 1)
    )
    target.write_text(_HEADER + rows, encoding="utf-8")
    try:
        yield f"{_CONTAINER_ROOT}/{name}"
    finally:
        target.unlink(missing_ok=True)


def _json(response: object) -> dict[str, object]:
    payload = cast("dict[str, object]", response.json())  # type: ignore[attr-defined]
    return payload


def _create_kb(base_url: str, name: str) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases",
        json={"name": name, "description": "connector e2e"},
        timeout=30,
    )
    assert response.status_code in (200, 201), response.text
    kb_id = _json(response)["id"]
    assert isinstance(kb_id, str)
    return kb_id


def _register_connector(
    base_url: str, kb_id: str, *, path: str, connector_id: str = "e2e-carrier-drop"
) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors",
        json={
            "connector_id": connector_id,
            "name": "E2E Carrier Drop",
            "source_type": "filesystem",
            "schedule": {"mode": "manual"},
            "mapping": {
                "mapping_id": "carrier",
                "mapping_version": "v1",
                "feed_name": _FEED,
            },
            "config": {"path": path},
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    return connector_id


def _start_sync(base_url: str, kb_id: str, connector_id: str, key: str) -> str:
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors/{connector_id}/sync-runs",
        json={"idempotency_key": key},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    run_id = _json(response)["run_id"]
    assert isinstance(run_id, str)
    return run_id


def _poll_until_terminal(
    base_url: str, kb_id: str, connector_id: str, run_id: str
) -> dict[str, object]:
    requests = _requests()
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = requests.get(
            f"{base_url}/knowledgebases/{kb_id}/connectors/{connector_id}/sync-runs",
            timeout=30,
        )
        assert response.status_code == 200, response.text
        items = cast("list[dict[str, object]]", _json(response)["items"])
        for run in items:
            if run.get("run_id") == run_id:
                last = run
                if run.get("status") in {"completed", "failed", "canceled"}:
                    return run
        time.sleep(2)
    pytest.fail(
        f"Sync run {run_id} never reached a terminal state in "
        f"{_TIMEOUT_SECONDS}s; last seen: {last}"
    )


def test_connector_sync_ingests_records_end_to_end(
    base_url: str, csv_file: str
) -> None:
    """The whole point: POST a sync run and have rows actually arrive.

    Before this work the run was created, returned 200, and nothing ever
    executed it. The first version of this feature still did — the executor was
    registered and subscribed, but nothing published the *first* page event, so
    a run sat in `queued` forever with no error. Only a live stack showed it.
    """
    kb_id = _create_kb(base_url, "Connector E2E")
    connector_id = _register_connector(base_url, kb_id, path=csv_file)
    run_id = _start_sync(base_url, kb_id, connector_id, f"e2e-{int(time.time())}")

    run = _poll_until_terminal(base_url, kb_id, connector_id, run_id)

    counters = cast("dict[str, int]", run["counters"])
    assert run["status"] == "completed", run
    assert counters["pulled"] == _ROW_COUNT
    assert counters["accepted"] == _ROW_COUNT
    assert counters["quarantined"] == 0
    # Assigned by the executor and shared by every page of the run — this is
    # what ties the pulled rows to the run that pulled them.
    assert run["ingest_correlation_id"] is not None


def test_an_unimplemented_source_type_is_refused_before_a_run_exists(
    base_url: str,
) -> None:
    """Registering something nothing can serve must fail loudly and early."""
    requests = _requests()
    kb_id = _create_kb(base_url, "Connector E2E Guard")

    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors",
        json={
            "connector_id": "e2e-unimplemented",
            "name": "Nope",
            "source_type": "http",
            "schedule": {"mode": "manual"},
            "mapping": {
                "mapping_id": "m",
                "mapping_version": "v1",
                "feed_name": _FEED,
            },
            "config": {},
        },
        timeout=30,
    )

    assert response.status_code == 422, response.text
    assert "not implemented" in response.text


def test_a_path_outside_the_allowed_root_fails_the_run(base_url: str) -> None:
    """The root guard must hold through the real worker, not just in unit tests.

    A connector path is operator-supplied; `/etc` must never be readable no
    matter what the config says.
    """
    kb_id = _create_kb(base_url, "Connector E2E Path Guard")
    requests = _requests()
    response = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/connectors",
        json={
            "connector_id": "e2e-escape",
            "name": "Escape Attempt",
            "source_type": "filesystem",
            "schedule": {"mode": "manual"},
            "mapping": {
                "mapping_id": "m",
                "mapping_version": "v1",
                "feed_name": _FEED,
            },
            "config": {"path": "/etc"},
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    run_id = _start_sync(
        base_url, kb_id, "e2e-escape", f"e2e-escape-{int(time.time())}"
    )

    run = _poll_until_terminal(base_url, kb_id, "e2e-escape", run_id)

    # The source raises, the worker retries and dead-letters, and the run never
    # completes. What must never happen is rows from /etc being ingested.
    assert run["status"] != "completed", run
    counters = cast("dict[str, int]", run["counters"])
    assert counters["accepted"] == 0
