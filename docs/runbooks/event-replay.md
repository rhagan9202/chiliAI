# Runbook: Event dead-letter inspection & replay (BL-023)

> This is the repo's first operator runbook. It covers the durable DLQ ledger
> and the `/events/dlq` operator API — see `backend/events/README.md` for the
> module-level design, and `docs/architecture.md` §6.9 for the architectural
> summary.

## Symptom

One or more of:

- `pipeline_errors_total` (worker `:8001/metrics`) climbing.
- Worker logs showing `"Handler exhausted retries; routing to DLQ"`
  (`agent/coordinator.py::run_handler_with_retry`).
- A document or workflow stuck — no forward progress, no error surfaced to
  the user.
- The worker `/health` endpoint reporting `"degraded"` with a nonzero
  `events_dead_lettered`.

## What "dead-lettered" means here

When a pipeline handler raises past its retry budget, `run_handler_with_retry`
does two things:

1. Publishes the original event + error context to the Redis Streams
   `{stream}.dlq` stream (`event_bus.publish_to_dlq`) — this is the ACK-safe
   transport archive. It is **capped** (`stream_maxlen`) and has no
   query/filter/replay surface of its own.
2. Persists a durable `DlqRecord` row to the `event_dlq` Postgres table (or an
   in-memory store if no database is configured) — this is the record you
   actually work from as an operator. Step 2 is best-effort: if it fails, the
   Redis entry from step 1 is still there as a fallback, and the original
   handler failure is never masked by a persistence failure.

**The `event_dlq` table is the operational source of truth. The `.dlq` Redis
stream is a raw, capped, non-queryable archive of the same events** — use it
only if you need to reconstruct history predating the durable table, or if
the durable persist itself failed (rare, logged when it happens).

## Prerequisites for the commands below

- `make dev` running (API on `:8000`, worker on `:8001`), on this branch.
- Auth is disabled by default in dev, which makes every route pass
  unauthenticated as the anonymous `viewer` role. The `/events/dlq` routes are
  gated `analyst` (read) / `admin` (replay, discard) — to exercise the
  mutation routes locally, bring the stack up with the anonymous role
  elevated:

  ```bash
  CHILI_DEV_ANONYMOUS_ROLE=admin docker compose -f docker-compose.dev.yaml up -d --build
  # or, from the repo root Makefile equivalent:
  CHILI_DEV_ANONYMOUS_ROLE=admin make dev
  ```

  `admin` also satisfies the `analyst`-gated read routes (role hierarchy).
  `CHILI_DEV_ANONYMOUS_ROLE` is ignored under `CHILI_ENV=production` (see
  `backend/api/middleware/auth.py::build_anonymous_user`) — this is a
  dev-only convenience, never a production auth bypass.
- **The API and worker must be pointed at the same Postgres backend** for the
  API to see records the worker wrote — the dev compose stack does this by
  default. Under the in-memory DLQ store (no database configured), the API
  and worker each keep a private, in-process ledger and will never agree with
  each other; that configuration is fine for unit tests, not for operating
  against a real incident.

## Triage

1. **List pending records:**

   ```bash
   curl -s "http://localhost:8000/events/dlq?status=pending&limit=50" | jq
   ```

   Response shape (`DlqRecordListResponse`):

   ```json
   {
     "items": [
       {
         "dlq_id": "dlq_...",
         "event_type": "documents.uploaded",
         "correlation_id": "corr_...",
         "payload": { "event_type": "documents.uploaded", "event_body": "{...}" },
         "error_message": "...",
         "error_traceback": "Traceback (most recent call last):\n...",
         "retry_count": 3,
         "failed_at": "2026-07-15T12:00:00Z",
         "status": "pending",
         "replayed_at": null,
         "created_at": "2026-07-15T12:00:00Z"
       }
     ],
     "total": 1
   }
   ```

   `payload` is exactly what `events.codec.encode_event` produced at capture
   time: `event_type` plus `event_body` (the event's JSON-serialized model).
   You can filter by `event_type` too: `?event_type=documents.uploaded`.

2. **Inspect one record's traceback:**

   ```bash
   curl -s "http://localhost:8000/events/dlq/<dlq_id>" | jq '.error_traceback'
   ```

3. **Correlate with worker logs and workflow state** via `correlation_id`
   (every event and every workflow run carries one):

   ```bash
   docker compose -f docker-compose.dev.yaml logs worker | grep '<correlation_id>'
   curl -s "http://localhost:8000/workflows?correlation_id=<correlation_id>" | jq
   ```

   (The Redis stream message id is *not* stored on the `DlqRecord` — by the
   time the wrapper persists the record, the delivery has already been
   ACKed/exhausted at the transport layer, so there is no live stream
   position to link back to. `correlation_id` is the durable join key across
   the DLQ record, worker logs, and workflow runs.)

## Decide: replay or discard

- **Root cause understood and fixed** (bad data, a since-patched bug, a
  transient outage that has cleared) → **replay**.
- **Poison message** (malformed payload that will never succeed, a
  since-retired event type/handler, or a duplicate you've already handled
  another way) → **discard**. Discard is **terminal** — there is no
  "un-discard." The raw entry still exists in the Redis `.dlq` stream if you
  ever need to recover the original payload by hand.

### Replay

```bash
curl -s -X POST "http://localhost:8000/events/dlq/<dlq_id>/replay" | jq
```

What happens: the stored `payload` is decoded back into the original typed
event (`events.codec.decode_event`) and re-published on that event's normal
stream through the configured `EventBus` — it goes through the **ordinary**
dispatch path, not a special replay lane. That means:

- Per-document failure isolation (BL-041/BL-017) still applies.
- Status-projection idempotency still applies — a successful replay of an
  already-completed step is a safe no-op, not a duplicate.
- **If the underlying cause is not actually fixed, the replayed event will
  dead-letter again — as a brand-new `DlqRecord` with a new `dlq_id`.** The
  original record is marked `replayed` regardless of whether the replay
  ultimately succeeds; "replayed" means "re-driven," not "succeeded." Check
  `GET /events/dlq?status=pending` again after a replay-of-an-unfixed-cause
  and expect to see a new pending record for the same underlying problem —
  this is the normal "replay-of-unfixed-event dead-letters again" loop, not a
  bug.

Responses: `200` with the updated record (`status: "replayed"`); `404`
unknown `dlq_id`; `409` if the record is not `pending` (already
replayed/discarded, or another operator won a concurrent replay/discard —
see "Concurrent replay/discard" below); `422` if the stored payload no longer
decodes against the current event registry (schema/codec drift since
capture) — the record is left `pending` so you can discard it or, if a fix
ships for the decode issue itself, retry later.

### Discard

```bash
curl -s -X POST "http://localhost:8000/events/dlq/<dlq_id>/discard" | jq
```

`200` with `status: "discarded"`; `404` unknown; `409` if not `pending`.

## Concurrent replay/discard (by design, not a bug)

`replay` publishes the event **before** it compare-and-swaps the record to
`replayed`. If two operators race — replay + replay, or replay + discard, on
the same `dlq_id` — it is possible for the event to be published even though
only one of the two calls wins the status transition (the loser gets a
`409`). This is an accepted tradeoff, not an oversight:

- The alternative order (CAS to `replayed` first, publish second) would risk
  a record marked `replayed` with **no event ever published** — if the
  process crashes, or the publish call itself fails, between the two steps.
  That is a silent data-loss window with no operator-visible signal.
- The chosen order can at worst double-publish an event under a race. Every
  pipeline handler downstream is idempotent by construction — BL-041's
  document-status projection is monotonic (older/duplicate transitions are
  no-ops) and BL-017's graph upserts are replay-stable (an identical replay
  leaves version and properties byte-stable). A harmless extra publish is
  strictly preferable to a silently lost one.

In practice: don't coordinate replay/discard of the same record from two
terminals at once on purpose, but if it happens, nothing is unsafe — one call
wins, the other gets a clean `409`, and the event was published at least
once, never zero times.

## What replay does NOT do

- **No bulk replay.** One `POST .../replay` re-drives exactly one record.
  There is no "replay all pending" endpoint — this is deliberate, to avoid an
  automatic retry storm re-triggering the same root cause across every
  dead-lettered event at once.
- **No automatic retry.** A dead-lettered record stays `pending` forever
  until an operator acts on it (replay or discard) — nothing re-drives it on
  a timer.
- **Not a bulk data-repair tool.** Replay re-publishes the *original* event
  payload unmodified; it cannot patch the payload before re-publishing. If
  the event's data itself was wrong (not just a transient environment issue),
  fix the root cause at the source (re-upload the document, correct the
  upstream feed row, etc.) rather than trying to "fix" the dead-lettered
  event in place.

## Role gates

| Route | Method | Role |
|---|---|---|
| `/events/dlq` | GET | `analyst` |
| `/events/dlq/{id}` | GET | `analyst` |
| `/events/dlq/{id}/replay` | POST | `admin` |
| `/events/dlq/{id}/discard` | POST | `admin` |

Reads are `analyst`-gated (not `viewer`) because tracebacks can leak internal
paths/stack detail. Mutations are `admin`-gated because they change pipeline
state (re-driving a pipeline stage, or terminally discarding a record).

## `event_dlq` table vs. `.dlq` Redis streams — summary

| | `event_dlq` (Postgres) | `{stream}.dlq` (Redis Streams) |
|---|---|---|
| Durability | Durable, unbounded (until an operator acts) | Capped (`stream_maxlen`); oldest entries evicted |
| Queryable | Yes — filter by `status`/`event_type`, paginated | No — raw stream, `XRANGE` only |
| Mutable state | Yes — `pending` → `replayed`/`discarded`, CAS-guarded | No — append-only transport log |
| Operator surface | `GET/POST /events/dlq*` | None (would need direct Redis access) |
| Written by | `run_handler_with_retry`, best-effort, after the stream write succeeds | `run_handler_with_retry`, always, on retry exhaustion |
| Role | Operational source of truth | Raw forensic archive / fallback if the table write fails |

## Fixable-case walkthrough (end-to-end)

1. A poison event dead-letters — confirm via `GET /events/dlq?status=pending`.
2. Inspect the traceback (`GET /events/dlq/{id}`) and correlate with worker
   logs (`correlation_id`) to find the root cause.
3. Fix the root cause (patch the handler, repair the upstream data, restore a
   dependency).
4. Replay: `POST /events/dlq/{id}/replay`.
5. Confirm forward progress: the pipeline completes (workflow status
   transitions, document status projection advances,
   `pipeline_errors_total` stops climbing, no new pending record appears for
   that `correlation_id`).

If step 3 was skipped or incomplete, step 5 instead shows a **new** pending
`DlqRecord` — go back to step 2.

## Live verification status

The end-to-end walkthrough above (force a poison event → appears in
`GET /events/dlq` → replay-while-still-broken dead-letters again as a new
record → discard the new record → fix the cause → replay → pipeline
completes; role gates spot-checked: viewer 403 on list, analyst 403 on
replay) is **pending** — the controller runs it in-session immediately after
this commit, against the full `make dev` stack restarted onto this branch.
This runbook describes the intended and code-verified behavior; it does not
itself constitute that live-verification pass.
