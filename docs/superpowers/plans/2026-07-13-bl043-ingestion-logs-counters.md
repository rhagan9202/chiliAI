# BL-043: Ingestion Structured Stage Logs + Prometheus Counters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every ingestion pipeline stage (parse, chunk, extract, validate) emits a structured per-document log line with `stage=`, `source_document_id=`, `kb_id=`, `duration_ms=`, `outcome=` (success|failed|empty), and three Prometheus counters (`ingestion_documents_failed_total{stage,error_class}`, `ingestion_documents_empty_extraction_total`, `ingestion_dedup_suppressed_total{kind}`) become scrapeable from the process that increments them.

**Architecture:** Counters are defined once in a new dependency-light `shared/metrics.py` (mirroring `shared/logging.py` / `shared/tracing.py`) on the **default `prometheus_client` registry**, and each process exposes its own registry: the API keeps its existing `/metrics` (`api/middleware/metrics.py`), and the worker gains a `GET /metrics` route on its **existing** asyncio health HTTP server (`agent/health.py`, port 8001). A `log_stage()` helper in the same shared module emits the structured stage log via the project's structlog setup.

**Tech Stack:** Python 3.12, prometheus-client (already a base dependency: `pyproject.toml` line 25 `"prometheus-client>=0.20"`), structlog via `shared/logging.py`, pytest.

---

## CRITICAL DESIGN DECISION: worker-process metrics exposure (resolved by code investigation)

**The question:** the Prometheus registry pattern lives in the API process (`backend/api/middleware/metrics.py`, `/metrics` route), but ingestion stages run in the WORKER process (`python -m agent.coordinator`). Counters incremented in the worker are invisible to the API's `/metrics`.

**What the code says:**

1. **The worker already has an HTTP surface.** `backend/agent/health.py` runs a hand-rolled asyncio TCP server (`start_health_server`, started by `run_worker` at `agent/coordinator.py:3615` via `start_health_server_safely`) serving `GET /health` on `HealthSettings` host `0.0.0.0` port `8001` (`agent/models.py:35-41`). This satisfies REQ-NFR-OPS-004 worker health.
2. **The API uses the DEFAULT `prometheus_client` registry.** `api/middleware/metrics.py` declares module-level `Counter`/`Histogram` objects (no custom registry) and `build_metrics_router()` defaults `target_registry` to `prometheus_client.REGISTRY`, exposed at `GET /metrics` behind `require_role("service")`.
3. **A worker-side metrics module already exists with a latent blind spot.** `backend/monitoring/metrics.py` defines `pipeline_stage_duration_seconds` / `pipeline_errors_total` on the default registry and is incremented by the coordinator (`observe_pipeline_stage` wraps every event in `handle_event`, `agent/coordinator.py:2993`). Its docstring claims the API exporter emits "a unified payload for HTTP and pipeline data" — **false across processes**; those worker increments are currently scrapeable nowhere. This plan fixes that docstring and makes them scrapeable.

**Decision:** add `GET /metrics` to the existing worker health server (`_route_request` in `agent/health.py`), returning `generate_latest(REGISTRY)` with `CONTENT_TYPE_LATEST`. Counters are defined in a new **`shared/metrics.py`** — NOT `ingestion/metrics.py` — because increments span three modules (`ingestion/` parse failures, `agent/` empty extraction, `records/` + `ingestion/` dedup), and per the 3-path architecture rule modules may only share code through `shared/` (the contracts library; `shared/logging.py` and `shared/tracing.py` are the exact precedents for cross-cutting observability there; prometheus-client is a base dependency so `shared/` stays dependency-light). Rejected alternatives: `prometheus_client.start_http_server` in the worker (second port + a daemon thread when a running asyncio HTTP server already exists), any cross-process push/aggregation (explicitly out of scope), and a custom `CollectorRegistry` (would diverge from every existing metric in the codebase).

**Per-process visibility map (informs verification):**

| Counter | Incremented in | Scrape at |
|---|---|---|
| `ingestion_documents_failed_total{stage,error_class}` | worker (parse runs in worker via `documents.uploaded` consumption) | worker `:8001/metrics` |
| `ingestion_documents_empty_extraction_total` | worker (`handle_entities_extracted`) | worker `:8001/metrics` |
| `ingestion_dedup_suppressed_total{kind="document"}` | API (`IngestionService.register_documents`, called by documents router) | API `:8000/metrics` |
| `ingestion_dedup_suppressed_total{kind="record_batch"}` | API (`RecordsService.register_records`, called by `api/routers/records.py`) | API `:8000/metrics` |

**Emission-point placements (resolved by code investigation):**

- **Failure counter** increments adjacent to each `DocumentsFailedEvent` publish. Today there is exactly one emission point: `ingestion/service.py:365` (`ingest_task`, parse failures; `DocumentParseFailure.error_type` is the exception class name — the `error_class` label). The event payload (`DocumentFailureReference`) carries neither `stage` nor `error_class`, so consumption-side counting cannot produce the required labels — emission-side is the only label-correct point. **BL-041 soft dependency (not blocking):** when BL-041 converts two more failure paths to `DocumentsFailedEvent` emissions, each new emission site adds one line — `ingestion_documents_failed_total.labels(stage=..., error_class=...).inc()` — against the counter this plan already defines. Note this in the `shared/metrics.py` docstring.
- **Empty-extraction counter** increments where empty extraction is detected: `handle_entities_extracted` in `agent/coordinator.py` computes `empty_extraction = valid_entity_count == 0` (line ~1366) and already feeds `DocumentsExtractionWarningEvent`.
- **Dedup counter** increments at the two real suppression points: (a) `records/service.py:81-95` — `was_submitted()` short-circuits an identical record batch (`duplicate=True`, no persist, no publish); (b) `ingestion/service.py` `register_documents` — an already-registered document with no recovery marker gets `should_publish = False` (content path line ~122, remote-URI path line ~159) and is never enqueued. These are different units (a batch vs. a document), so the counter carries a `kind` label (`record_batch` | `document`) — the AC-specified metric *name* is unchanged; the label prevents mixing incomparable units in one unlabeled series.

**Structured-log stage set (scoping decision):** `parse` (`ingestion/service.ingest_task`), `chunk` (`handle_documents_parsed`), `extract` (`handle_documents_chunked`), `validate` (`handle_entities_extracted`) — the four ingestion-module stages. Downstream graph/embeddings/vector-index handlers belong to other modules' flows and already have event-level `observe_pipeline_stage` timing plus `start_pipeline_span`; their per-document structured logs arrive with the full ingestion.17 story. Log emission uses structlog key-value kwargs (JSON renderer → real fields; console renderer → `key=value`), matching `shared/logging.py` conventions, on a dedicated logger `chili.ingestion.stage`.

---

## Global Constraints

- **HARD SCOPE FENCE:** NO OpenTelemetry spans, NO Grafana dashboards (module story ingestion.17, blocked on the `_observability` epic). Do not touch `shared/tracing.py`.
- **NO cross-process metric push.** Each process serves its own registry.
- `pyright` strict, zero `Any`. Run **bare** `.venv/bin/pyright` from `backend/` — `tool.pyright.include` covers test dirs, and test code must be strict-clean too. Never trigger `reportPrivateUsage` (use public `REGISTRY.get_sample_value`, never `._value.get()`).
- pytest coverage ≥ 85% per touched package (`shared`, `ingestion`, `records`, `agent`; `monitoring` gets a docstring-only change).
- `ruff`: run `.venv/bin/ruff check --no-cache .` from `backend/` (cache dir not writable in sandbox).
- All commands below run on the host venv: `cd /home/rdhagan92/chiliAI/backend` then `.venv/bin/...` (per project dev-environment convention).
- **No Docker commands in any task.** The worker container does not hot-reload; full-stack `/metrics` verification happens in the MAIN session after this plan completes (checklist at the bottom).
- No frontend or OpenAPI contract change anywhere in this plan (no Pydantic wire-model changes) → no `codegen:api` run needed.
- pyright gotcha (project memory): `@contextmanager` + `Iterator` return annotation is rejected — this plan avoids new context managers entirely (`log_stage` is a plain function).
- Branch: `feat/sprint-2026-26-ingestion-visibility`. Commit after every task. Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Task ordering: Tasks 1→2 are sequential (2 consumes 1). Tasks 3, 4, 5 each depend only on Task 1 and are day-1 independent of each other.

---

### Task 1: `shared/metrics.py` — counters + `log_stage` helper

**Files:**
- Create: `backend/shared/metrics.py`
- Create: `backend/tests/shared/test_metrics.py`
- Modify: `backend/pyproject.toml` (pyright `include` — two new file entries)

**Interfaces:**
- Produces (later tasks import these exact names from `shared.metrics`):
  - `ingestion_documents_failed_total: Counter` — labels `["stage", "error_class"]`
  - `ingestion_documents_empty_extraction_total: Counter` — no labels
  - `ingestion_dedup_suppressed_total: Counter` — labels `["kind"]`
  - `StageOutcome = Literal["success", "failed", "empty"]`
  - `def log_stage(*, stage: str, kb_id: str, source_document_id: str, started_at: float, outcome: StageOutcome) -> None` — `started_at` is a `time.perf_counter()` value captured when the stage began; the helper computes `duration_ms` and logs event `"ingestion_stage"` on logger `chili.ingestion.stage`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/shared/test_metrics.py`:

```python
"""Tests for the shared ingestion telemetry counters and stage-log helper (BL-043)."""

from __future__ import annotations

import logging
from time import perf_counter

import pytest
from prometheus_client import REGISTRY

from shared.metrics import (
    ingestion_dedup_suppressed_total,
    ingestion_documents_empty_extraction_total,
    ingestion_documents_failed_total,
    log_stage,
)


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels or {})
    return value if value is not None else 0.0


def _has_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


class TestCounters:
    def test_failed_counter_labels_stage_and_error_class(self) -> None:
        labels = {"stage": "parse", "error_class": "ValueError"}
        before = _sample("ingestion_documents_failed_total", labels)
        ingestion_documents_failed_total.labels(
            stage="parse", error_class="ValueError"
        ).inc()
        assert _sample("ingestion_documents_failed_total", labels) == before + 1.0

    def test_empty_extraction_counter_increments(self) -> None:
        before = _sample("ingestion_documents_empty_extraction_total")
        ingestion_documents_empty_extraction_total.inc()
        assert _sample("ingestion_documents_empty_extraction_total") == before + 1.0

    def test_dedup_counter_labels_kind(self) -> None:
        labels = {"kind": "document"}
        before = _sample("ingestion_dedup_suppressed_total", labels)
        ingestion_dedup_suppressed_total.labels(kind="document").inc()
        assert _sample("ingestion_dedup_suppressed_total", labels) == before + 1.0


class TestLogStage:
    def test_emits_all_bl043_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
            log_stage(
                stage="parse",
                kb_id="kb-1",
                source_document_id="doc-1",
                started_at=perf_counter(),
                outcome="success",
            )
        assert _has_field(caplog.text, "stage", "parse")
        assert _has_field(caplog.text, "kb_id", "kb-1")
        assert _has_field(caplog.text, "source_document_id", "doc-1")
        assert _has_field(caplog.text, "outcome", "success")
        assert "duration_ms" in caplog.text

    def test_failed_outcome_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
            log_stage(
                stage="chunk",
                kb_id="kb-2",
                source_document_id="doc-2",
                started_at=perf_counter(),
                outcome="failed",
            )
        assert _has_field(caplog.text, "outcome", "failed")
        assert _has_field(caplog.text, "stage", "chunk")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/shared/test_metrics.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'shared.metrics'`

- [ ] **Step 3: Write the implementation**

Create `backend/shared/metrics.py`:

```python
"""Shared ingestion telemetry: Prometheus counters and the stage-log helper (BL-043).

Counters are registered on the default ``prometheus_client`` registry. There is
no cross-process aggregation: each process serves its own ``/metrics`` endpoint
(the API gateway via ``api/middleware/metrics.py``, the pipeline worker via the
health server in ``agent/health.py``) and reports only the increments that
happened in that process.

``ingestion_documents_failed_total`` must be incremented adjacent to every
``DocumentsFailedEvent`` publish (the event payload carries neither ``stage``
nor ``error_class``, so counting at consumption cannot label correctly). The
only emission point today is ``ingestion/service.py`` (parse failures); new
emission points (e.g. BL-041) add one ``.labels(...).inc()`` line each.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Literal

from prometheus_client import Counter

from shared.logging import get_logger

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

__all__ = [
    "StageOutcome",
    "ingestion_dedup_suppressed_total",
    "ingestion_documents_empty_extraction_total",
    "ingestion_documents_failed_total",
    "log_stage",
]

StageOutcome = Literal["success", "failed", "empty"]

ingestion_documents_failed_total: Counter = Counter(
    "ingestion_documents_failed_total",
    "Documents that emitted a documents.failed event, by stage and error class.",
    ["stage", "error_class"],
)

ingestion_documents_empty_extraction_total: Counter = Counter(
    "ingestion_documents_empty_extraction_total",
    "Documents whose extraction validated to zero entities.",
)

ingestion_dedup_suppressed_total: Counter = Counter(
    "ingestion_dedup_suppressed_total",
    "Ingestion submissions suppressed by idempotent deduplication "
    "(kind=document: re-uploaded source document; kind=record_batch: "
    "identical structured-records batch).",
    ["kind"],
)

_stage_logger: BoundLogger = get_logger("chili.ingestion.stage")


def log_stage(
    *,
    stage: str,
    kb_id: str,
    source_document_id: str,
    started_at: float,
    outcome: StageOutcome,
) -> None:
    """Emit the BL-043 structured per-document stage log line.

    ``started_at`` is a ``time.perf_counter()`` value captured when the stage
    began; duration is computed here so call sites stay one line.
    """

    duration_ms = (perf_counter() - started_at) * 1000.0
    _stage_logger.info(
        "ingestion_stage",
        stage=stage,
        source_document_id=source_document_id,
        kb_id=kb_id,
        duration_ms=round(duration_ms, 3),
        outcome=outcome,
    )
```

- [ ] **Step 4: Add the two files to pyright's include list**

In `backend/pyproject.toml`, inside `[tool.pyright]` `include = [...]` (starts at line 109):
- after the entry `"records",` add a line: `    "shared/metrics.py",`
- after the entry `"tests/records",` add a line: `    "tests/shared/test_metrics.py",`

(`shared/` is not yet strict-included as a whole package; file-level include entries are the established pattern — see `"api/middleware/auth.py"` etc. Do NOT add all of `shared/` or all of `tests/shared/`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/shared/test_metrics.py -v`
Expected: 5 passed

- [ ] **Step 6: Type-check and lint**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: 0 errors, 0 warnings

- [ ] **Step 7: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/shared/metrics.py backend/tests/shared/test_metrics.py backend/pyproject.toml
git commit -m "feat(shared): add BL-043 ingestion counters and stage-log helper

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Worker `GET /metrics` on the existing health server

**Files:**
- Modify: `backend/agent/health.py` (module docstring, imports, `_handle_client`, `_route_request`, `_error_payload`)
- Modify: `backend/monitoring/metrics.py:1-6` (docstring only — fix the false "unified payload" claim)
- Test: `backend/tests/agent/test_health.py`

**Interfaces:**
- Consumes: counters from Task 1 register on the default `REGISTRY` at import.
- Produces: `GET /metrics` on the worker health server (same host/port as `/health`, default `0.0.0.0:8001`) returning `generate_latest(REGISTRY)` with content type `CONTENT_TYPE_LATEST`. No auth (matches the existing unauthenticated `/health`; the port is compose-internal — the API's `/metrics` keeps its `require_role("service")` gate unchanged).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/agent/test_health.py` (add the three imports to the existing import block at the top of the file):

```python
from monitoring.metrics import observe_pipeline_stage
from prometheus_client import CONTENT_TYPE_LATEST
from shared.metrics import ingestion_documents_failed_total
```

and append at the end of the file:

```python
async def _exercise_metrics_endpoint() -> None:
    port = _free_port()
    settings = HealthSettings(host="127.0.0.1", port=port)
    state = HealthState(settings=settings)
    # Ensure the default registry has samples from both metric families the
    # worker owns: a BL-043 counter and the pre-existing pipeline histogram.
    ingestion_documents_failed_total.labels(
        stage="parse", error_class="ProbeError"
    ).inc()
    with observe_pipeline_stage("probe.stage"):
        pass

    server = await start_health_server(state)
    try:
        status_code, body = await _http_get("127.0.0.1", port, "/metrics")
        assert status_code == 200
        text = body.decode("utf-8")
        assert "ingestion_documents_failed_total" in text
        assert 'error_class="ProbeError"' in text
        assert "pipeline_stage_duration_seconds" in text

        # Content type is the Prometheus exposition format, not JSON.
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"GET /metrics HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"
        )
        await writer.drain()
        raw = await reader.read()
        writer.close()
        await writer.wait_closed()
        assert b"Content-Type: " + CONTENT_TYPE_LATEST.encode("ascii") in raw

        # /health is unchanged by the metrics route.
        health_status, health_body = await _http_get("127.0.0.1", port, "/health")
        assert health_status == 200
        assert json.loads(health_body)["status"] == "ok"
    finally:
        server.close()
        await server.wait_closed()


def test_health_server_serves_prometheus_metrics() -> None:
    asyncio.run(_exercise_metrics_endpoint())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/agent/test_health.py::test_health_server_serves_prometheus_metrics -v`
Expected: FAIL — `assert status_code == 200` fails with `404`

- [ ] **Step 3: Implement the `/metrics` route**

In `backend/agent/health.py`:

(a) Replace the module docstring (line 1) with:

```python
"""Lightweight async health-check and metrics HTTP server for the worker process.

Serves ``GET /health`` (JSON liveness/progress payload) and ``GET /metrics``
(Prometheus exposition of the default registry). The worker increments its
pipeline metrics in-process, so this endpoint — not the API gateway's
``/metrics`` — is where worker-side counters are scraped.
"""
```

(b) Add to the imports (after `import logging`):

```python
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
```

(c) Add a module constant after `logger = logging.getLogger("chili.worker.health")`:

```python
_JSON_CONTENT_TYPE = "application/json"
```

(d) Replace the response-building block inside `_handle_client` (the lines from `response_body, status_line = _route_request(request_line, state)` through `).encode("ascii") + body_bytes`) with:

```python
        response_body, status_line, content_type = _route_request(request_line, state)
        response = (
            f"HTTP/1.1 {status_line}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(response_body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii") + response_body
```

(e) Replace `_route_request` and `_error_payload` entirely with:

```python
def _route_request(
    request_line: bytes, state: HealthState
) -> tuple[bytes, str, str]:
    """Return the response body, HTTP status line, and content type."""

    decoded_line = request_line.decode("ascii", errors="replace").strip()

    parts = decoded_line.split(" ")
    if len(parts) < 2:
        return _error_payload("Invalid request"), "400 Bad Request", _JSON_CONTENT_TYPE

    method, path = parts[0], parts[1]
    if method != "GET":
        return (
            _error_payload("Method not allowed"),
            "405 Method Not Allowed",
            _JSON_CONTENT_TYPE,
        )
    if path == "/health":
        payload = build_health_payload(state)
        return json.dumps(payload).encode("utf-8"), "200 OK", _JSON_CONTENT_TYPE
    if path == "/metrics":
        return generate_latest(REGISTRY), "200 OK", CONTENT_TYPE_LATEST
    return _error_payload("Not found"), "404 Not Found", _JSON_CONTENT_TYPE


def _error_payload(message: str) -> bytes:
    return json.dumps({"error": message}).encode("utf-8")
```

(Note: the old `try/except UnicodeDecodeError` around the decode was unreachable — `errors="replace"` never raises — and is dropped rather than kept as dead, uncoverable code.)

(f) In `backend/monitoring/metrics.py`, replace the module docstring (lines 1–6) with:

```python
"""Prometheus metrics helpers used by the worker pipeline (E10-S09).

The metrics declared here use the default ``prometheus_client`` registry.
Each process serves its own scrape endpoint for that registry: the API
gateway exposes ``GET /metrics`` (``api/middleware/metrics.py``) and the
worker exposes ``GET /metrics`` on its health server (``agent/health.py``).
Increments made in the worker process are visible only on the worker's
endpoint — there is no cross-process aggregation.
"""
```

- [ ] **Step 4: Run the full health test module (old tests must still pass)**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/agent/test_health.py -v`
Expected: all tests pass (including the pre-existing `/health`, 404, and 405 tests)

- [ ] **Step 5: Type-check and lint**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: 0 errors, 0 warnings

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/agent/health.py backend/monitoring/metrics.py backend/tests/agent/test_health.py
git commit -m "feat(agent): serve Prometheus /metrics from the worker health server

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Parse stage — structured log + failure counter at the `DocumentsFailedEvent` emission point

**Files:**
- Modify: `backend/ingestion/service.py` (imports + `ingest_task`, currently lines 287–378)
- Test: `backend/tests/ingestion/test_service.py`

**Interfaces:**
- Consumes: `log_stage`, `ingestion_documents_failed_total` from `shared.metrics` (Task 1).
- Produces: every `ingest_task` call logs `stage="parse"` with outcome `success`/`failed`; every parse failure increments `ingestion_documents_failed_total{stage="parse", error_class=<DocumentParseFailure.error_type>}` immediately before the `DocumentsFailedEvent` publish.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/ingestion/test_service.py`, add to the imports at the top:

```python
import logging

from prometheus_client import REGISTRY
```

and append at the end of the file:

```python
def _has_stage_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


def test_ingest_task_emits_parse_stage_log_with_success_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _event_bus, object_store = _service()
    storage_key = "knowledgebases/kb-1/documents/doc-1/claims.json"
    object_store.put_bytes(
        storage_key, b'{"claim_id": "42"}', media_type="application/json"
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        outcome = service.ingest_task(
            IngestionTask(
                knowledge_base_id="kb-1",
                source_document=SourceDocument(
                    id="doc-1",
                    source_type=SourceType.FILE_UPLOAD,
                    filename="claims.json",
                ),
                storage_key=storage_key,
                content_type="application/json",
            ),
            correlation_id="corr-stage-log",
        )

    assert isinstance(outcome, ParseResult)
    assert _has_stage_field(caplog.text, "stage", "parse")
    assert _has_stage_field(caplog.text, "kb_id", "kb-1")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-1")
    assert _has_stage_field(caplog.text, "outcome", "success")
    assert "duration_ms" in caplog.text


def test_ingest_task_failure_increments_failed_counter_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, event_bus, _object_store = _service()
    labels = {"stage": "parse", "error_class": "RemoteFetchError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    uploaded = DocumentsUploadedEvent(
        correlation_id="corr-failed-counter",
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-failed-counter",
                filename=None,
                content_type=None,
                storage_key=None,
                uri=None,
                document_format=None,
                size_bytes=None,
            )
        ],
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        outcomes = service.process_documents_uploaded(uploaded)

    assert isinstance(outcomes[0], DocumentParseFailure)
    assert outcomes[0].error_type == "RemoteFetchError"
    assert isinstance(event_bus.published_events[-1], DocumentsFailedEvent)
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "parse")
    assert _has_stage_field(caplog.text, "outcome", "failed")
```

(`pytest` is already imported in this file; the unresolved-format document is the same fixture the existing `test_process_documents_uploaded_publishes_failure_for_unresolved_format` uses, and its `error_type` is `"RemoteFetchError"`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/ingestion/test_service.py::test_ingest_task_emits_parse_stage_log_with_success_outcome tests/ingestion/test_service.py::test_ingest_task_failure_increments_failed_counter_and_logs -v`
Expected: 2 FAILED (no `stage=parse` in caplog; counter delta 0.0)

- [ ] **Step 3: Implement**

In `backend/ingestion/service.py`:

(a) Add imports (after `from hashlib import sha256`):

```python
from time import perf_counter
```

and (after the `from shared.protocols import ObjectStoreProtocol` import):

```python
from shared.metrics import ingestion_documents_failed_total, log_stage
```

(b) Replace the `ingest_task` method entirely with:

```python
    def ingest_task(
        self,
        task: IngestionTask,
        *,
        correlation_id: str | None = None,
    ) -> ParseResult | DocumentParseFailure:
        started_at = perf_counter()
        outcome: ParseResult | DocumentParseFailure
        if task.storage_key is not None:
            try:
                stored = self._object_store.get_bytes(task.storage_key)
            except Exception as exc:  # noqa: BLE001 - read failure becomes a typed failure
                logger.error(
                    "Failed to read source object for source_document_id=%s "
                    "storage_key=%s error_class=%s: %s",
                    task.source_document.id,
                    task.storage_key,
                    type(exc).__name__,
                    exc,
                )
                outcome = DocumentParseFailure(
                    source_document=mark_failed(mark_parsing(task.source_document), str(exc)),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            else:
                outcome = self._parser_orchestrator.safe_parse_content(
                    task.source_document,
                    stored.content,
                    content_type=stored.media_type or task.content_type,
                    filename=task.source_document.filename,
                    uri=task.source_document.uri,
                )
        else:
            outcome = self._parser_orchestrator.safe_parse_source(task.source_document)

        if isinstance(outcome, ParseResult):
            parsed_document_storage_key = self._build_parsed_storage_key(
                task.knowledge_base_id,
                outcome.parsed_document.id,
            )
            self._object_store.put_bytes(
                parsed_document_storage_key,
                outcome.parsed_document.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": task.knowledge_base_id,
                    "source_document_id": outcome.source_document.id,
                    "parsed_document_id": outcome.parsed_document.id,
                },
            )
            self._event_bus.publish(
                DocumentsParsedEvent(
                    correlation_id=correlation_id or generate_id(),
                    documents=[
                        ParsedDocumentReference(
                            knowledge_base_id=task.knowledge_base_id,
                            source_document_id=outcome.source_document.id,
                            parsed_document_id=outcome.parsed_document.id,
                            parser_name=outcome.parsed_document.parser_name,
                            parser_version=outcome.parsed_document.parser_version,
                            document_format=(
                                outcome.source_document.document_format.value
                                if outcome.source_document.document_format is not None
                                else None
                            ),
                            warning_count=len(outcome.parsed_document.warnings),
                            warning_samples=[
                                f"{warning.code}: {warning.message}"
                                for warning in outcome.parsed_document.warnings[:10]
                            ],
                            storage_key=task.storage_key,
                            parsed_document_storage_key=parsed_document_storage_key,
                        )
                    ]
                )
            )
            log_stage(
                stage="parse",
                kb_id=task.knowledge_base_id,
                source_document_id=outcome.source_document.id,
                started_at=started_at,
                outcome="success",
            )
            return outcome

        # BL-043: count at the DocumentsFailedEvent emission point so every
        # current and future emitter (e.g. BL-041's converted failure paths,
        # which add their own adjacent .inc()) is reflected in the counter.
        ingestion_documents_failed_total.labels(
            stage="parse", error_class=outcome.error_type
        ).inc()
        self._event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=correlation_id or generate_id(),
                documents=[
                    DocumentFailureReference(
                        knowledge_base_id=task.knowledge_base_id,
                        source_document_id=outcome.source_document.id,
                        error_message=outcome.error_message,
                        storage_key=task.storage_key,
                    )
                ]
            )
        )
        log_stage(
            stage="parse",
            kb_id=task.knowledge_base_id,
            source_document_id=outcome.source_document.id,
            started_at=started_at,
            outcome="failed",
        )
        return outcome
```

(The only additions vs. the current body are: `started_at = perf_counter()` at the top, the two `log_stage(...)` calls, and the `ingestion_documents_failed_total...inc()` block with its comment. Everything else is byte-identical to the existing implementation.)

- [ ] **Step 4: Run the full ingestion service test module**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/ingestion/test_service.py -v`
Expected: all tests pass (new + pre-existing)

- [ ] **Step 5: Type-check and lint**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: 0 errors, 0 warnings

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/ingestion/service.py backend/tests/ingestion/test_service.py
git commit -m "feat(ingestion): parse-stage structured logs + documents-failed counter

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Chunk/extract/validate stage logs + empty-extraction counter (worker handlers)

**Files:**
- Modify: `backend/agent/coordinator.py` — `handle_documents_parsed` (lines ~1151–1213), `handle_documents_chunked` (lines ~1224–1277), `handle_entities_extracted` (lines ~1305–1430), plus one import
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `log_stage`, `ingestion_documents_empty_extraction_total` from `shared.metrics` (Task 1). `time` is already imported in `coordinator.py` (line 17) — use `time.perf_counter()`.
- Produces: per-document `stage="chunk"|"extract"|"validate"` logs; `ingestion_documents_empty_extraction_total` incremented once per document whose validation yields zero valid entities.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/agent/test_coordinator.py`, add to the imports:

```python
import logging

from prometheus_client import REGISTRY
```

and append at the end of the file:

```python
def _has_stage_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


def test_handle_documents_parsed_emits_chunk_stage_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    parsed_document = ParsedDocument(
        id="parsed-log-1",
        source_document_id="doc-log-1",
        text_content="Claim 42 was filed by provider A.",
        parser_name="test-parser",
    )
    storage_key = "knowledgebases/kb-1/parsed/parsed-log-1.json"
    object_store.put_bytes(
        storage_key,
        parsed_document.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_documents_parsed(
            DocumentsParsedEvent(
                correlation_id="corr-chunk-log",
                documents=[
                    ParsedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-log-1",
                        parsed_document_id="parsed-log-1",
                        parser_name="test-parser",
                        storage_key="knowledgebases/kb-1/documents/doc-log-1/claims.txt",
                        parsed_document_storage_key=storage_key,
                    )
                ],
            ),
            document_chunker=chunker,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert _has_stage_field(caplog.text, "stage", "chunk")
    assert _has_stage_field(caplog.text, "kb_id", "kb-1")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-log-1")
    assert _has_stage_field(caplog.text, "outcome", "success")
    assert "duration_ms" in caplog.text


def test_handle_documents_parsed_logs_failed_outcome_before_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        with pytest.raises(ValueError):
            handle_documents_parsed(
                DocumentsParsedEvent(
                    documents=[
                        ParsedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="doc-fail-log",
                            parsed_document_id="parsed-fail-log",
                            parser_name="test",
                        )
                    ]
                ),
                document_chunker=create_document_chunker(),
                object_store=InMemoryObjectStore(),
                event_bus=InMemoryEventBus(),
            )
    assert _has_stage_field(caplog.text, "stage", "chunk")
    assert _has_stage_field(caplog.text, "outcome", "failed")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-fail-log")


def test_handle_documents_chunked_logs_empty_outcome_for_zero_candidates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunking_result = ChunkingResult(
        source_document_id="doc-empty-log",
        parsed_document_id="parsed-empty-log",
        strategy_used="StructuredRecordChunker",
        chunks=[],
    )
    chunks_storage_key = "knowledgebases/kb-1/chunks/parsed-empty-log.json"
    object_store.put_bytes(
        chunks_storage_key,
        chunking_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_documents_chunked(
            DocumentsChunkedEvent(
                documents=[
                    ChunkedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-empty-log",
                        parsed_document_id="parsed-empty-log",
                        chunk_count=0,
                        strategy="StructuredRecordChunker",
                        chunks_storage_key=chunks_storage_key,
                    )
                ]
            ),
            document_extractor=create_document_extractor([]),
            object_store=object_store,
            event_bus=event_bus,
        )

    assert _has_stage_field(caplog.text, "stage", "extract")
    assert _has_stage_field(caplog.text, "outcome", "empty")


def test_handle_entities_extracted_counts_empty_extraction_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-empty-count",
        source_document_id="doc-empty-count",
        parsed_document_id="parsed-empty-count",
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-empty-count.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    before = (
        REGISTRY.get_sample_value("ingestion_documents_empty_extraction_total") or 0.0
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_entities_extracted(
            EntitiesExtractedEvent(
                documents=[
                    ExtractedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-empty-count",
                        parsed_document_id="parsed-empty-count",
                        extraction_result_id="extract-empty-count",
                        entity_count=0,
                        relationship_count=0,
                        extraction_storage_key=extraction_storage_key,
                    )
                ]
            ),
            extraction_validator=create_extraction_validator([], []),
            object_store=object_store,
            event_bus=event_bus,
        )

    after = (
        REGISTRY.get_sample_value("ingestion_documents_empty_extraction_total") or 0.0
    )
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "validate")
    assert _has_stage_field(caplog.text, "outcome", "empty")
```

(All model/handler names used here are already imported by this test module.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/agent/test_coordinator.py -k "stage_log or empty_outcome or counts_empty or failed_outcome_before_raising" -v`
Expected: 4 FAILED (no stage fields in caplog; counter delta 0.0)

- [ ] **Step 3: Implement**

In `backend/agent/coordinator.py`:

(a) Add to the imports (next to `from shared.logging import ...`, line ~219):

```python
from shared.metrics import ingestion_documents_empty_extraction_total, log_stage
```

(b) Replace `handle_documents_parsed` entirely with:

```python
def handle_documents_parsed(
    event: DocumentsParsedEvent,
    *,
    document_chunker: DocumentChunker,
    object_store: ObjectStore,
    event_bus: EventBus,
    kb_repository: KnowledgeBaseRepository | None = None,
) -> int:
    """Chunk parsed documents and publish the next workflow event."""
    references: list[ChunkedDocumentReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        try:
            if kb_repository is not None and document.warning_count > 0:
                kb_repository.record_document_warnings(
                    document.knowledge_base_id,
                    document.source_document_id,
                    additional_count=document.warning_count,
                    reasons=list(document.warning_samples),
                )
            if document.parsed_document_storage_key is None:
                raise ValueError(
                    "DocumentsParsedEvent requires parsed_document_storage_key for chunking."
                )
            stored = object_store.get_bytes(document.parsed_document_storage_key)
            parsed_document = ParsedDocument.model_validate_json(stored.content)
            result = document_chunker.chunk_document(
                parsed_document,
                source_document_id=document.source_document_id,
            )
            chunks_storage_key = _build_chunks_storage_key(
                document.knowledge_base_id,
                document.parsed_document_id,
            )
            object_store.put_bytes(
                chunks_storage_key,
                result.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": document.knowledge_base_id,
                    SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                    "parsed_document_id": document.parsed_document_id,
                    "chunk_count": len(result.chunks),
                },
            )
            references.append(
                ChunkedDocumentReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    parsed_document_id=document.parsed_document_id,
                    chunk_count=len(result.chunks),
                    strategy=result.strategy_used,
                    storage_key=document.storage_key,
                    parsed_document_storage_key=document.parsed_document_storage_key,
                    chunks_storage_key=chunks_storage_key,
                )
            )
        except Exception:
            log_stage(
                stage="chunk",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            raise
        log_stage(
            stage="chunk",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="success" if result.chunks else "empty",
        )
    if references:
        event_bus.publish(
            DocumentsChunkedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)
```

(c) Replace `handle_documents_chunked` entirely with:

```python
def handle_documents_chunked(
    event: DocumentsChunkedEvent,
    *,
    document_extractor: DocumentExtractorProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Extract entity candidates from persisted chunks and publish the next event."""
    references: list[ExtractedDocumentReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        try:
            if document.chunks_storage_key is None:
                raise ValueError(
                    "DocumentsChunkedEvent requires chunks_storage_key for extraction."
                )
            stored = object_store.get_bytes(document.chunks_storage_key)
            chunking_result = ChunkingResult.model_validate_json(stored.content)
            extraction_result = document_extractor.extract_document(chunking_result)
            extraction_storage_key = _build_extraction_storage_key(
                document.knowledge_base_id,
                extraction_result.id,
            )
            object_store.put_bytes(
                extraction_storage_key,
                extraction_result.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": document.knowledge_base_id,
                    SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                    "parsed_document_id": document.parsed_document_id,
                    "extraction_result_id": extraction_result.id,
                    "entity_count": len(extraction_result.candidate_entities),
                    "relationship_count": len(extraction_result.candidate_relationships),
                },
            )
            references.append(
                ExtractedDocumentReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    parsed_document_id=document.parsed_document_id,
                    extraction_result_id=extraction_result.id,
                    entity_count=len(extraction_result.candidate_entities),
                    relationship_count=len(extraction_result.candidate_relationships),
                    storage_key=document.storage_key,
                    parsed_document_storage_key=document.parsed_document_storage_key,
                    chunks_storage_key=document.chunks_storage_key,
                    extraction_storage_key=extraction_storage_key,
                )
            )
        except Exception:
            log_stage(
                stage="extract",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            raise
        log_stage(
            stage="extract",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome=(
                "success"
                if extraction_result.candidate_entities
                or extraction_result.candidate_relationships
                else "empty"
            ),
        )
    if references:
        event_bus.publish(
            EntitiesExtractedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)
```

(d) Replace `handle_entities_extracted` entirely with (changes vs. current code: `started_at` capture, the `try/except` wrapper with the `failed` log, the empty-extraction counter increment after `empty_extraction = ...`, and the trailing `validate` log — everything else byte-identical):

```python
def handle_entities_extracted(
    event: EntitiesExtractedEvent,
    *,
    extraction_validator: ExtractionResultValidator,
    object_store: ObjectStore,
    event_bus: EventBus,
    kb_repository: KnowledgeBaseRepository | None = None,
) -> int:
    """Validate extracted candidates and publish runtime-ready results."""
    references: list[ValidatedDocumentReference] = []
    warning_references: list[ExtractionWarningReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        try:
            if document.extraction_storage_key is None:
                raise ValueError(
                    "EntitiesExtractedEvent requires extraction_storage_key for validation."
                )
            stored = object_store.get_bytes(document.extraction_storage_key)
            extraction_result = ExtractionResult.model_validate_json(stored.content)
            validation_report = extraction_validator.validate_extraction(extraction_result)
            validation_storage_key = _build_validation_storage_key(
                document.knowledge_base_id,
                extraction_result.id,
            )
            object_store.put_bytes(
                validation_storage_key,
                validation_report.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": document.knowledge_base_id,
                    SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                    "parsed_document_id": document.parsed_document_id,
                    "extraction_result_id": extraction_result.id,
                    "validation_report_id": validation_report.id,
                    "valid_entity_count": len(validation_report.valid_entities),
                    "valid_relationship_count": len(validation_report.valid_relationships),
                    "entity_error_count": len(validation_report.entity_errors),
                    "relationship_error_count": len(validation_report.relationship_errors),
                },
            )
            references.append(
                ValidatedDocumentReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    parsed_document_id=document.parsed_document_id,
                    extraction_result_id=document.extraction_result_id,
                    validation_report_id=validation_report.id,
                    valid_entity_count=len(validation_report.valid_entities),
                    valid_relationship_count=len(validation_report.valid_relationships),
                    entity_error_count=len(validation_report.entity_errors),
                    relationship_error_count=len(validation_report.relationship_errors),
                    storage_key=document.storage_key,
                    parsed_document_storage_key=document.parsed_document_storage_key,
                    chunks_storage_key=document.chunks_storage_key,
                    extraction_storage_key=document.extraction_storage_key,
                    validation_storage_key=validation_storage_key,
                )
            )

            valid_entity_count = len(validation_report.valid_entities)
            dropped_entity_count = len(validation_report.entity_errors)
            dropped_relationship_count = len(validation_report.relationship_errors)
            stripped_property_count = len(validation_report.warnings)
            extraction_stage_warnings = list(extraction_result.warnings)
            empty_extraction = valid_entity_count == 0
            if empty_extraction:
                ingestion_documents_empty_extraction_total.inc()
            if (
                empty_extraction
                or dropped_entity_count
                or dropped_relationship_count
                or stripped_property_count
                or extraction_stage_warnings
            ):
                logger.warning(
                    "ingestion extraction warning stage=validate knowledge_base_id=%s "
                    "source_document_id=%s valid_entities=%d dropped_entities=%d "
                    "dropped_relationships=%d stripped_properties=%d empty=%s",
                    document.knowledge_base_id,
                    document.source_document_id,
                    valid_entity_count,
                    dropped_entity_count,
                    dropped_relationship_count,
                    stripped_property_count,
                    empty_extraction,
                )
                sample_reasons = _collect_extraction_warning_reasons(
                    validation_report, extraction_stage_warnings
                )
                warning_references.append(
                    ExtractionWarningReference(
                        knowledge_base_id=document.knowledge_base_id,
                        source_document_id=document.source_document_id,
                        valid_entity_count=valid_entity_count,
                        valid_relationship_count=len(validation_report.valid_relationships),
                        dropped_entity_count=dropped_entity_count,
                        dropped_relationship_count=dropped_relationship_count,
                        stripped_property_count=stripped_property_count,
                        empty_extraction=empty_extraction,
                        sample_reasons=sample_reasons,
                        validation_storage_key=validation_storage_key,
                    )
                )
                if kb_repository is not None:
                    warning_total = (
                        dropped_entity_count
                        + dropped_relationship_count
                        + stripped_property_count
                        + len(extraction_stage_warnings)
                    ) or 1  # an unexplained empty extraction still counts once
                    kb_repository.record_document_warnings(
                        document.knowledge_base_id,
                        document.source_document_id,
                        additional_count=warning_total,
                        reasons=sample_reasons,
                    )
        except Exception:
            log_stage(
                stage="validate",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            raise
        log_stage(
            stage="validate",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="empty" if empty_extraction else "success",
        )
    if references:
        event_bus.publish(
            EntitiesValidatedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    if warning_references:
        event_bus.publish(
            DocumentsExtractionWarningEvent(
                correlation_id=event.correlation_id,
                documents=warning_references,
            )
        )
    return len(references)
```

(`empty_extraction` is assigned unconditionally inside the `try`, and the `except` re-raises, so the trailing `log_stage` only runs on the success path where it is bound — pyright accepts this.)

- [ ] **Step 4: Run the coordinator test module**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/agent/test_coordinator.py -v`
Expected: all tests pass (new + pre-existing, including `test_handle_entities_extracted_emits_extraction_warning_for_empty_document` and the missing-storage-key ValueError tests)

- [ ] **Step 5: Type-check and lint**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: 0 errors, 0 warnings

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "feat(agent): chunk/extract/validate stage logs + empty-extraction counter

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Dedup-suppressed counter at both suppression points

**Files:**
- Modify: `backend/records/service.py` (import + one increment in `register_records`)
- Modify: `backend/ingestion/service.py` (extend the Task 3 import + one increment in `register_documents`)
- Test: `backend/tests/records/test_service.py`, `backend/tests/ingestion/test_service.py`

**Interfaces:**
- Consumes: `ingestion_dedup_suppressed_total` from `shared.metrics` (Task 1).
- Produces: `{kind="record_batch"}` +1 per suppressed identical record batch; `{kind="document"}` +1 per suppressed already-registered document submission. Both run in the API process (documents/records routers) → visible on the API's `/metrics`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/records/test_service.py`, add to the imports:

```python
from prometheus_client import REGISTRY
```

and append at the end of the file:

```python
def test_register_records_duplicate_increments_dedup_counter() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(
        store, event_bus=bus, records_config=_records_config()
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "c-dedup-1", "amount": "10"}],
        source_type="api_push",
    )
    labels = {"kind": "record_batch"}

    first = service.register_records("kb-dedup", submission)
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    second = service.register_records("kb-dedup", submission)

    assert first.duplicate is False
    assert second.duplicate is True
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0
```

In `backend/tests/ingestion/test_service.py` (imports already extended in Task 3), append at the end of the file:

```python
def test_register_documents_duplicate_increments_dedup_counter() -> None:
    service, _event_bus, _object_store = _service()
    submission = DocumentSubmission(
        filename="claims.json",
        content=b'{"claim_id": "dedup-counter"}',
        content_type="application/json",
    )
    labels = {"kind": "document"}

    first = service.register_documents("kb-dedup", [submission])
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    second = service.register_documents("kb-dedup", [submission])

    assert first[0].enqueued is True
    assert second[0].enqueued is False
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/records/test_service.py::test_register_records_duplicate_increments_dedup_counter tests/ingestion/test_service.py::test_register_documents_duplicate_increments_dedup_counter -v`
Expected: 2 FAILED (counter delta 0.0)

- [ ] **Step 3: Implement**

(a) In `backend/records/service.py`, add the import (after `from records.validation import validate_rows_partition`):

```python
from shared.metrics import ingestion_dedup_suppressed_total
```

and change the duplicate branch in `register_records` from:

```python
        if self._store.was_submitted(
            knowledge_base_id=knowledge_base_id, submission_hash=submission_hash
        ):
            # Identical batch already registered — no-op (no persist, no publish).
            return RecordIngestReceipt(
```

to:

```python
        if self._store.was_submitted(
            knowledge_base_id=knowledge_base_id, submission_hash=submission_hash
        ):
            # Identical batch already registered — no-op (no persist, no publish).
            ingestion_dedup_suppressed_total.labels(kind="record_batch").inc()
            return RecordIngestReceipt(
```

(b) In `backend/ingestion/service.py`, extend the Task 3 import line to:

```python
from shared.metrics import (
    ingestion_dedup_suppressed_total,
    ingestion_documents_failed_total,
    log_stage,
)
```

and inside `register_documents`, directly before the line `if should_publish:` (the one preceding `document_references.append(`), insert at the same indentation:

```python
            if not should_publish:
                # Suppressed by idempotent dedup: content already registered
                # (no recovery marker) or remote-URI marker already present.
                ingestion_dedup_suppressed_total.labels(kind="document").inc()
```

- [ ] **Step 4: Run both test modules**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/records/test_service.py tests/ingestion/test_service.py -v`
Expected: all tests pass — including the pre-existing dedup tests (`test_register_records_dedupes_identical_resubmission`, `test_register_documents_deduplicates_repeated_content`, `test_register_documents_deduplicates_repeated_remote_uri`, `test_register_documents_republishes_duplicate_with_recovery_marker`)

- [ ] **Step 5: Type-check and lint**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: 0 errors, 0 warnings

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/records/service.py backend/ingestion/service.py backend/tests/records/test_service.py backend/tests/ingestion/test_service.py
git commit -m "feat(records,ingestion): count dedup-suppressed submissions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation + full quality gates

**Files:**
- Modify: `backend/agent/README.md`, `backend/ingestion/README.md`, `backend/README.md`, `docs/architecture.md`
- Check (update only if they mention metrics/observability and now contradict): `.github/copilot-instructions.md`, `.github/instructions/*.md`, `backend/records/` has no README (skip)

- [ ] **Step 1: Update `backend/agent/README.md`**

Read the file; in the section describing the worker health endpoint (search for `health`), extend it with:

> The health server also serves `GET /metrics` (Prometheus text exposition of the default `prometheus_client` registry) on the same port (default `8001`). Worker-side counters — `pipeline_stage_duration_seconds`, `pipeline_errors_total` (`monitoring/metrics.py`), `ingestion_documents_failed_total`, `ingestion_documents_empty_extraction_total` (`shared/metrics.py`) — are scraped here, not from the API gateway's `/metrics`: each process exposes only its own registry (no cross-process aggregation). Like `/health`, the endpoint is unauthenticated and compose-internal.

- [ ] **Step 2: Update `backend/ingestion/README.md`**

Read the file; add under the service/observability description:

> **Stage telemetry (BL-043):** each pipeline stage emits a structured `ingestion_stage` log line (logger `chili.ingestion.stage`) with fields `stage=` (`parse`|`chunk`|`extract`|`validate`), `source_document_id=`, `kb_id=`, `duration_ms=`, `outcome=` (`success`|`failed`|`empty`). `parse` is logged in `ingestion/service.py`; `chunk`/`extract`/`validate` in the worker handlers (`agent/coordinator.py`). Parse failures increment `ingestion_documents_failed_total{stage,error_class}` adjacent to the `DocumentsFailedEvent` publish — any new emission point of that event must add the same one-line increment. Dedup suppressions (document re-upload, identical record batch) increment `ingestion_dedup_suppressed_total{kind}`. Counters live in `shared/metrics.py`.

- [ ] **Step 3: Update `backend/README.md` and `docs/architecture.md`**

Read each; in the observability/monitoring subsection of both, record the two facts that changed the design:
1. The worker now exposes `GET /metrics` on its health server (port 8001) — the API's `/metrics` and the worker's `/metrics` are separate registries in separate processes; scrape both.
2. `shared/metrics.py` is the home for counters incremented from more than one module (contracts-library path; precedent: `shared/logging.py`, `shared/tracing.py`).

Keep edits surgical — do not restructure either document.

- [ ] **Step 4: Full quality gates (all must be green)**

```bash
cd /home/rdhagan92/chiliAI/backend
.venv/bin/python -m pytest --cov -q
.venv/bin/pyright
.venv/bin/ruff check --no-cache .
```

Expected: pytest fully green with coverage ≥ 85% for `shared`, `ingestion`, `records`, `agent`; pyright 0 errors; ruff clean. If any pre-existing failure surfaces, diagnose and fix it before finishing (project rule: no known-red handoffs).

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/agent/README.md backend/ingestion/README.md backend/README.md docs/architecture.md
git commit -m "docs: record worker /metrics endpoint and BL-043 ingestion telemetry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## MAIN-SESSION verification (NOT an executor task — requires Docker)

After all tasks land, the main session verifies against the full running stack (`make dev`); the worker container does not hot-reload, so rebuild/restart it first:

1. Upload a document that fails parsing (e.g. an extensionless file with no content type) via the API; upload a valid document twice; push an identical records batch twice.
2. `docker compose -f docker-compose.dev.yaml exec chili-worker curl -s localhost:8001/metrics` → expect `ingestion_documents_failed_total{error_class="...",stage="parse"}`, `ingestion_documents_empty_extraction_total`, `pipeline_stage_duration_seconds`.
3. `curl -s -H "Authorization: Bearer <service-token>" localhost:8000/metrics` → expect `ingestion_dedup_suppressed_total{kind="document"}` and `{kind="record_batch"}`.
4. Worker logs (`docker compose logs chili-worker`) → expect `ingestion_stage` lines with `stage=`, `source_document_id=`, `kb_id=`, `duration_ms=`, `outcome=` for parse/chunk/extract/validate.
5. If the worker's port 8001 should be scraped from the host in dev, add the port mapping to `docker-compose.dev.yaml` in the main session (deliberately excluded from this plan's tasks).

## Self-review checklist (performed)

- AC1 (structured stage logs, five fields, three outcomes): Tasks 3 + 4; field names match the AC exactly (`kb_id`, not `knowledge_base_id`).
- AC2 (three counters, exact names/labels): Task 1 defines; Tasks 3/4/5 increment; Task 2 makes worker-side ones scrapeable. `{kind}` label on the dedup counter is a documented, name-preserving addition.
- AC3 (scope fence): no OTel, no Grafana, no dashboards, no push anywhere in the plan; `shared/tracing.py` untouched.
- Type consistency: `log_stage(*, stage, kb_id, source_document_id, started_at, outcome)` used identically at all six call sites; counter names/labels identical across definition, increments, and test assertions.
- BL-041 soft dependency documented at the counter definition and at the parse-stage increment (non-blocking).
