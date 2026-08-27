# events

Event bus abstraction for backend orchestration: typed event envelopes, a
transport protocol with in-memory and Redis Streams adapters, and — since
BL-023 — a durable, queryable dead-letter ledger with an operator replay
surface. `events/` is dependency-light infrastructure (analogous to
`database/`): no domain logic, no business logic. Every event carries
`event_id`, `correlation_id`, and `created_at` for tracing.

## Layout

| File | Responsibility |
|------|----------------|
| `types.py` | `EventBase` + every concrete event model (`DocumentsUploadedEvent`, `KnowledgeBaseCreatedEvent`, ...); `AnyEvent` is the hand-maintained union of all of them. |
| `codec.py` | `encode_event`/`decode_event` — transport (de)serialization. `EVENT_TYPE_REGISTRY` maps `event_type` string → model class. |
| `protocols.py` | `EventBus` protocol (`publish`, `consume`, `reclaim_stale_pending`, `ack`, `publish_to_dlq`) and `DlqRecordStore` protocol (BL-023). `DlqErrorInfo`/`DlqEntry` dataclasses carry captured failure context. |
| `dlq_models.py` | `DlqRecord` (the durable dead-letter row), `DlqRecordStatus` (`pending`/`replayed`/`discarded`), `DlqRecordListResponse` (BL-023). |
| `runtime.py` | `EventBusSettings` (env-driven), `create_event_bus()` factory selecting in-memory vs. `redis` backend. |
| `exceptions.py` | `EventsError` / `DlqPersistenceError`. |
| `adapters/in_memory.py` | `InMemoryEventBus` — process-local transport for tests/dev; does not model the Redis Streams Pending Entries List. |
| `adapters/redis_streams.py` | `RedisStreamsEventBus` — `XADD`/`XREADGROUP`/`XACK`/`XAUTOCLAIM` over a real Redis instance; also owns `publish_to_dlq` (writes to the `{stream}.dlq` stream, capped by `EventBusSettings.stream_maxlen`). |
| `adapters/dlq_in_memory.py` | `InMemoryDlqRecordStore` — process-local `DlqRecordStore` for tests/local dev. |
| `adapters/dlq_postgres.py` | `PostgresDlqRecordStore` — Postgres-backed `DlqRecordStore` over the `event_dlq` table (migration `0010_event_dlq`, `backend/database/`). |

## Event bus (transport)

`create_event_bus()` (`runtime.py`) selects the adapter from
`EventBusSettings.backend` (`CHILI_EVENT_BUS_BACKEND`, `in-memory` default,
`redis` for the dev/prod stack). Publishers call `EventBus.publish`; the
worker (`agent/coordinator.py`) consumes via `EventBus.consume` inside a
retry/DLQ wrapper (`run_handler_with_retry`) that reclaims stale pending
entries (`reclaim_stale_pending`, `XAUTOCLAIM`) before reading new ones.

On retry exhaustion, `run_handler_with_retry` calls `event_bus.publish_to_dlq`,
which writes the encoded event plus error context to the Redis `{stream}.dlq`
stream (transport-level, capped by `stream_maxlen` — an archive, not a
ledger). Since BL-023 it *also* persists a `DlqRecord` through the injected
`DlqRecordStore` — see below.

## Durable DLQ records + operator replay (BL-023)

The Redis `.dlq` stream is transport, not an operational record: it is capped,
has no query/filter surface, and nothing marks an entry as "handled." The
`event_dlq` Postgres table (or the in-memory adapter, for tests/no-database
dev) is the durable source of truth an operator actually works from — see
[`docs/runbooks/event-replay.md`](../../docs/runbooks/event-replay.md) for the
operator playbook and curl examples.

**Writer.** `run_handler_with_retry` (`agent/coordinator.py`), after a
successful `publish_to_dlq`, persists a `DlqRecord` (`dlq_id`, `event_type`,
`correlation_id`, the codec-encoded `payload` — exactly what `encode_event`
produces, i.e. `{"event_type": ..., "event_body": <json>}` — `error_message`,
`error_traceback`, `retry_count`, `failed_at`) through
`WorkerDependencies.dlq_record_store`. This is **best-effort**: a store
failure is logged and swallowed, never propagated — it must not mask the
original handler error, and the Redis DLQ entry still exists as a fallback
record either way. `build_dlq_record_store` (`agent/coordinator.py`) selects
`PostgresDlqRecordStore` when a database connection provider is configured,
else `InMemoryDlqRecordStore` — the same selection rule as
`build_document_status_store` (BL-041).

**Second writer: undecodable messages.** `RedisStreamsEventBus` dead-letters a
message it cannot decode, via the same two surfaces, and acks it. Decoding used
to happen inline while building the delivery list, so one unregistered
`event_type` or a body that no longer validated took its whole `XREADGROUP`
batch down with it: the exception escaped before `run_handler_with_retry`, so
the retry/DLQ machinery never ran, nothing in the batch was acked, and with
`reclaim_min_idle_ms` unset (the default at the time) `>` never redelivers.
Measured on a live stack, one poison message stranded four good events
alongside it with `/events/dlq` still reporting `total: 0`.

**Since 2026-08-26 `reclaim_min_idle_ms` defaults to 60 000 ms** (see
`DEFAULT_RECLAIM_MIN_IDLE_MS` in `events/runtime.py`), so pending-entry
recovery is opt-out rather than opt-in. `reclaim_stale_pending` is the only
`XAUTOCLAIM` in the tree and it no-ops while the setting is `None`, which meant
every shipped configuration silently dropped whatever a crashed worker had
in flight — the only downstream signal was stale reconciliation failing the run
an hour later. The value must stay above the longest stage so a slow-but-alive
worker is never stolen from. Set `CHILI_EVENT_RECLAIM_MIN_IDLE_MS=0` to opt out
deliberately; `.env.example` and both compose files now set it explicitly.

A message that cannot be decoded cannot succeed on redelivery either, so it is
recorded and acked rather than left pending forever where nothing surfaces it.
The bus therefore takes an optional `dlq_record_store`; `create_event_bus`
accepts it and the worker passes one (publish-only callers such as the API do
not need it, since only consumers decode). `event_type` falls back to
`"unknown"` and `correlation_id` to the Redis message id, because an
undecodable body may carry neither.

**Persist semantics.** `DlqRecordStore.persist` is an **upsert keyed on
`dlq_id`**, not an append — a repeat `persist()` for an id already stored
replaces the row rather than duplicating it. It also carries a
**terminal-state guard**: once a record's `status` is `replayed` or
`discarded`, a later `persist()` for that id is a no-op — the stored record is
returned unchanged, never reverted back to `pending`. The in-memory adapter
checks this in Python; the Postgres adapter enforces it in SQL via a `CASE
WHEN event_dlq.status = 'pending' THEN EXCLUDED.<col> ELSE event_dlq.<col>
END` guard on every updated column of the `ON CONFLICT ... DO UPDATE` clause.
This matters in practice mainly for double-invocation safety of the writer
itself; the mark-transition methods below are the actual operator-facing state
machine.

**Reader/mutator API.** `api/routers/events.py` exposes the operator surface
on the existing `/events` router (DI via `api/dependencies.get_dlq_record_store`,
selecting the same Postgres-vs-in-memory backend):

- `GET /events/dlq` — paginated list (`limit`/`offset`, `status`/`event_type`
  filters), newest-first (`created_at DESC, dlq_id DESC` on both adapters).
  Returns full `DlqRecord`s (including `error_traceback`) — there is no
  separate summary shape; analysts read tracebacks directly by ruling.
  **`analyst`**-gated (viewer excluded: tracebacks may leak internals).
- `GET /events/dlq/{dlq_id}` — single record, 404 unknown. **`analyst`**-gated.
- `POST /events/dlq/{dlq_id}/replay` — decodes `record.payload` via
  `events.codec.decode_event` and re-publishes it on the event's regular
  stream through the injected `EventBus`, then CAS-transitions the record to
  `replayed` (`DlqRecordStore.mark_replayed`, which only succeeds from
  `pending`). 404 unknown id, 409 non-pending (or the concurrent-transition
  race between `get` and the CAS), 422 when the stored payload no longer
  decodes against the current event registry (codec/schema drift) — the
  record is left `pending` so an operator can retry after a fix or discard it.
  **`admin`**-gated: re-driving an event mutates pipeline state.
- `POST /events/dlq/{dlq_id}/discard` — CAS to `discarded`
  (`mark_discarded`); 404/409 the same way. **`admin`**-gated.

**Publish-before-CAS ordering (accepted design tradeoff).** `replay` publishes
the event *before* it CASes the record to `replayed`. Two concurrent operator
actions on the same record (replay+replay, or replay+discard) can therefore
both reach the publish step before either CAS lands — one operator gets a 200,
the loser gets a 409, but the event was published exactly once per *winning*
call, and never zero times. The alternative order (CAS first, publish second)
would risk the opposite failure: a record marked `replayed` with **no** event
ever published, if the process crashes or the publish call fails between the
two steps — a silent, undetectable data-loss window. This is accepted by
design because every pipeline handler downstream is idempotent by
construction (BL-041's monotonic status projection, BL-017's replay-stable
graph upserts), so an extra, harmless re-publish is always safe. See the
runbook for the operator-facing version of this note.

**Cross-process constraint.** The API and worker containers must share the
**same** Postgres backend for the API surface to see worker-written records —
identical to the BL-041 `document_status_store` constraint. Under the
in-memory adapter (no database configured), each process has its own private
ledger and the API will never see records the worker wrote — this is a
local-dev/test convenience only, not a deployable configuration for this
feature.

## Redaction (events.10 AC — deliberately not implemented)

`docs/backlog/events.md` story `events.10` calls for payload redaction
"according to existing event logging conventions." No such conventions exist
anywhere in the repo, and event payloads are reference-shaped by construction
— IDs, storage keys, counts; never document content or credentials (verified
across every model in `types.py`). No redaction machinery ships. If a future
event type ever carries a sensitive field, redaction is that event type's
design concern, not a blanket DLQ-layer transform.

## Tenancy note (events.11, not yet implemented)

Stream names (`EventBusSettings.stream_name`) and the `event_dlq` table carry
no tenant segment today — see `docs/backlog/events.md` story `events.11` for
the planned stream-per-tenant strategy.
