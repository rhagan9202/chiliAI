# BL-023 — Event replay operationalization (design)

> Status: approved by product owner 2026-07-15 (two scope rulings recorded below).
> Sprint: 2026-27. Module stories: `events.10` (DLQ persistence) + the DLQ-replay half of the events replay surface — `docs/backlog/events.md`. Requirements: REQ-WORKFLOW-005, REQ-NFR-DR-003.

## Problem

Exhausted handler retries route events to Redis `.dlq` streams with full error metadata (`redis_streams.py::publish_to_dlq`; wrapper at `agent/coordinator.py:3655`), but there is no durable operational record (the in-memory adapter keeps a Python list; Redis streams are capped by `stream_maxlen` and are transport, not a ledger), no way to list/inspect dead-lettered events, no way to re-drive one, and no operator runbook (`docs/runbooks/` does not exist). 3 of 6 BL-023 acceptance items were already shipped (xautoclaim reclaim, DLQ stream publish, retry/DLQ wrapper); this design covers the remaining three.

## Product-owner rulings (2026-07-15)

1. **Replay surface = API routes** on the existing `/events` router (not an operator script) — gateway auth/DI, curl-able from the runbook, future admin-UI hook. Contracts regenerated; no frontend UI work.
2. **Roles: admin replays/discards, analyst reads.** Re-driving or discarding mutates pipeline state; inspection is diagnostic.

## Design

### 1. Durable DLQ records

- `DlqRecordStore` protocol in `backend/events/protocols.py`; adapters in `backend/events/adapters/` (`InMemoryDlqRecordStore`, `PostgresDlqRecordStore`) following the `SourceDocumentStatusStore` exemplar (BL-041).
- Table `event_dlq`, Alembic migration `0010_event_dlq` — **`snapshots/head.sql` refreshed in the same commit** (BL-042 standing rule). Columns: `dlq_id` (text PK, generated id), `event_type` (text), `correlation_id` (text), `payload` (JSONB — the codec-encoded event exactly as `encode_event` produces it), `error_message` (text), `error_traceback` (text), `retry_count` (int), `failed_at` (timestamptz), `status` (text: `pending` | `replayed` | `discarded`), `replayed_at` (timestamptz null), `created_at` (timestamptz default now). Index on `(status, created_at DESC)` for the listing path.
- **Writer**: the worker's retry-exhaustion path (`run_handler_with_retry`) persists the record **alongside** the existing `publish_to_dlq` stream write. The stream remains the raw transport archive; the table is the operational source of truth. A store failure there is logged and swallowed — it must not mask the original handler error, and the Redis DLQ entry still exists as fallback.
- Store protocol surface: `persist(record)`, `list(status=None, event_type=None, limit, offset) -> (items, total)`, `get(dlq_id)`, `mark_replayed(dlq_id)` / `mark_discarded(dlq_id)` — the mark operations are compare-and-set on `status='pending'` and return the updated record or `None` (already-transitioned ⇒ API 409).
- **Linkage**: records carry `correlation_id` (from the event) — enough to correlate with worker logs, workflow runs, and document status rows. The Redis stream message id is not available at the wrapper (delivery already acked/exhausted); not stored.

### 2. Replay surface (API)

On the existing `/events` router (`api/routers/events.py`):

- `GET /events/dlq` — paginated list (limit/offset), filters `status`, `event_type`; **analyst** (viewer excluded: tracebacks may leak internals). Summary shape (no traceback).
- `GET /events/dlq/{dlq_id}` — full record including traceback; **analyst**.
- `POST /events/dlq/{dlq_id}/replay` — **admin**. Decodes `payload` via the normal codec (`decode_event`) and publishes on the event's regular stream via the injected `EventBus`; the worker consumes it through the ordinary dispatch path (status-projection idempotency, BL-041/BL-017 per-document isolation, and the retry/DLQ wrapper all apply as-is — a still-broken event will dead-letter again as a NEW record). On success: CAS to `status=replayed` + `replayed_at`. Non-`pending` record ⇒ 409. Decode failure (codec drift since capture) ⇒ 422 with the decode error, record left `pending`.
- `POST /events/dlq/{dlq_id}/discard` — **admin**; CAS to `discarded`; 409 if not pending.
- Pydantic request/response models in `events/service_models.py` (or the router's existing model home — follow the module's convention); OpenAPI exported + `npm run codegen:api` (CI contract job enforces).

### 3. Redaction — explicitly skipped (deviation from events.10 AC)

events.10's AC says "redacted according to existing event logging conventions" — no such conventions exist in the repo, and event payloads are reference-shaped by construction (IDs, storage keys, counts; never document content or credentials — verified across `events/types.py`). No redaction machinery ships in v1. If a future event type carries sensitive fields, redaction is that event's design concern. Recorded in the story annotation.

### 4. Operator runbook

`docs/runbooks/event-replay.md` — the repo's first runbook (new directory):
- Symptom: `pipeline_errors_total` climbing / "Handler exhausted retries" worker logs / stuck documents.
- Triage: list pending records via `GET /events/dlq`, inspect the traceback via `GET /events/dlq/{id}`, correlate with worker logs and `GET /workflows` via `correlation_id`.
- Decide: fix the root cause then **replay**; **discard** poison messages (with the caveat that discard is terminal and the Redis `.dlq` stream retains the raw entry).
- curl examples for all four routes (with the dev anonymous-role note).
- What replay does NOT do: no bulk replay, no automatic retry storms — one manual re-drive per invocation; a failed replay dead-letters as a new record.
- Relationship between the `event_dlq` table and `.dlq` Redis streams.

### 5. Wiring

- Worker: `build_worker_dependencies` constructs the store (Postgres when a database is configured, else in-memory — the `build_document_status_store` selection pattern) and threads it to `run_handler_with_retry` call sites via the existing dependency bundle.
- API: `get_dlq_record_store` in `api/dependencies.py` (same backend selection); routes take it via DI along with the existing `EventBus` dependency.
- API and worker must share the Postgres backend for the surface to see worker-written records — same cross-process constraint as the BL-041 status store; documented in the runbook and `events/README.md` (create if the module lacks one — check).

### 6. Testing

- Unit: both store adapters (persist, list pagination/filters, get, CAS transitions incl. already-transitioned `None`); retry-wrapper persistence on exhaustion + store-failure-does-not-mask-original-error; route tests (list/get/replay/discard, role gates 403s, 404 unknown id, 409 non-pending, 422 undecodable payload).
- Integration (`-m integration`): Postgres adapter against the live DB; migration `0010` replay through the BL-042 gate (`make migrate-check` green with refreshed snapshot).
- **Live verification (in-sprint per R-5, controller-run)**: force a poison event through the running stack → DLQ record appears via the API; replay it unfixed → it dead-letters again as a new record; discard the original; then a fixable case: replay after correcting the cause → pipeline completes. Role gates spot-checked live (viewer 403 on list; analyst 403 on replay).

## Code touch points

`backend/events/protocols.py`, `backend/events/adapters/{in_memory,postgres_dlq}.py` (new adapter file or extend in_memory — follow module layout), `backend/events/service_models.py` (or router-local models per convention), `backend/database/migrations/versions/0010_event_dlq.py` + `snapshots/head.sql`, `backend/agent/coordinator.py` (wrapper + worker wiring), `backend/api/dependencies.py`, `backend/api/routers/events.py`, `chili_app/openapi.json` + generated schema (codegen), `docs/runbooks/event-replay.md` (new), `backend/events/README.md` (new or update), `docs/backlog/events.md` (events.10 closeout + replay annotation), planning backlog + sprint file.
