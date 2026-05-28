# events backlog

> **Scope:** Redis Streams event bus, consumer groups, DLQ ops, schema versioning, replay, retention, tenancy, multi-region, delivery guarantees, catalog discipline.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story events.01: Reclaim stale pending entries with XPENDING/XCLAIM

**ID:** events.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_multitenancy.11, _security.05, _security.06, api.05, events.07, vectorstore.09]
**Estimated size:** L

**As a** platform operator,
**I need** stale pending Redis Stream entries to be auto-reclaimed by a healthy consumer,
**so that** a worker crash mid-handler does not strand events in the consumer-group pending list forever.

### Current State
- `RedisStreamsEventBus.consume` only issues `XREADGROUP ">"` (`backend/events/adapters/redis_streams.py:72-82`), which returns only never-delivered entries.
- `RedisStreamsEventBus.ack` carries an explicit `TODO(production): Add XPENDING/XCLAIM for reprocessing stale messages` (`backend/events/adapters/redis_streams.py:99`).
- `InMemoryEventBus` tracks `delivered` per entry but does not model the Redis Streams Pending Entries List (PEL), so the in-memory adapter cannot exercise reclaim semantics (`backend/events/adapters/in_memory.py:13-77`).
- The agent worker's retry/DLQ wrapper (`backend/agent/coordinator.py:2345-2412 run_handler_with_retry`) only protects in-flight handler invocations; once the process exits abnormally, the entry stays pending.

### Acceptance Criteria
- [ ] `RedisStreamsEventBus.consume` polls XPENDING for entries idle longer than a configurable `min_idle_ms` and reclaims them via XCLAIM before reading new entries with `>`, so a healthy consumer recovers crashed-peer deliveries.
- [ ] A new `EventBusSettings.claim_min_idle_ms: int = 60000` field is wired through `events/runtime.py` and reflected in `EventBus.consume` (default off when 0, on otherwise); the field is documented in `backend/events/__init__.py` module docstring.
- [ ] Reclaimed entries surface to the caller as `EventDelivery` instances with the original `event_id`/`stream`/`consumer_group`, identical to first-time deliveries, so handlers do not need to differentiate.
- [ ] `RedisStreamsEventBus` exposes a typed counter for reclaim attempts and successes (or a callback hook) suitable for binding to a Prometheus counter in a follow-up observability story.
- [ ] The XPENDING/XCLAIM TODO comment is removed from `backend/events/adapters/redis_streams.py:99` and replaced with a one-line reference to this story's design note.
- [ ] `tests/events/test_redis_streams.py` adds an integration test (marked `@pytest.mark.integration`) that publishes an event, simulates a crashed consumer by reading without ack from one consumer name, then verifies a second consumer name reclaims the entry after `min_idle_ms`.
- [ ] `pyright --strict` clean on `backend/events/`.
- [ ] Backend coverage for `backend/events/` stays ≥ 85%.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pytest -m integration tests/events/test_redis_streams.py -q` against a local Redis (`make dev` provides one) and confirm the reclaim test passes.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: with `make dev` up, publish a test event, send `XINFO PENDING <stream> <group>` after killing a worker, wait `min_idle_ms`, then run a worker and confirm the entry leaves the PEL.

### Code touch points
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/runtime.py` (modify — add `claim_min_idle_ms` setting)
- `backend/events/protocols.py` (modify — extend `consume` docstring if signature unchanged)
- `backend/tests/events/test_redis_streams.py` (modify)

---

## Story events.02: Trim Redis streams with MAXLEN/XTRIM retention

**ID:** events.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_observability.09, api.07, graph.03, ingestion.05, monitoring.01, monitoring.02, rag.02]
**Estimated size:** M

**As a** platform operator,
**I need** every Redis stream to enforce a bounded length or age,
**so that** event volume cannot exhaust Redis memory and retention is an explicit, observable contract instead of an accident.

### Current State
- `RedisStreamsEventBus.publish` invokes `xadd(stream, encode_event(event))` with no `maxlen=`/`minid=` argument (`backend/events/adapters/redis_streams.py:39-43`).
- The TODO at `backend/events/adapters/redis_streams.py:38` reads `Add MAXLEN/XTRIM to prevent unbounded stream growth`.
- DLQ streams (`<stream>.dlq` at `backend/events/adapters/redis_streams.py:120`) suffer the same gap.
- `EventBusSettings` (`backend/events/runtime.py:14-32`) has no retention fields.
- The event catalog (`docs/ledger/event-catalog.md`) documents publishers/consumers but not per-event retention bounds.

### Acceptance Criteria
- [ ] `EventBusSettings` gains `stream_maxlen: int | None = None` and `stream_maxlen_approximate: bool = True` fields, wired through `load_event_bus_settings()` from `CHILI_EVENT_STREAM_MAXLEN` / `CHILI_EVENT_STREAM_MAXLEN_APPROXIMATE`.
- [ ] `RedisStreamsEventBus.__init__` accepts the resolved retention configuration and applies `maxlen=`/`approximate=` on every `xadd` (both main and DLQ streams) when `stream_maxlen` is set; behaviour is unchanged when `None`.
- [ ] A per-event-type override map (`stream_maxlen_overrides: dict[str, int]`) is supported in `EventBusSettings` so high-volume streams (e.g. `pipeline.progress`) can have tighter bounds than low-volume lifecycle streams (e.g. `kb.create`).
- [ ] DLQ streams use a separately configurable `dlq_stream_maxlen` (or default to `10 * stream_maxlen`) so DLQ history outlives the source stream.
- [ ] `docs/ledger/event-catalog.md` gains a "Retention" column per event with a default bound and per-event overrides recorded.
- [ ] The TODO at `backend/events/adapters/redis_streams.py:38` is removed.
- [ ] Unit tests in `tests/events/test_redis_streams.py` assert `xadd` is invoked with the expected `maxlen` argument when settings populate it, and without it when settings leave it `None`.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: with `make dev` up and `CHILI_EVENT_STREAM_MAXLEN=1000` set, publish 1200 events and confirm `XLEN chili.<event_type>` is approximately 1000.

### Code touch points
- `backend/events/runtime.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/tests/events/test_redis_streams.py` (modify)
- `docs/ledger/event-catalog.md` (modify)

---

## Story events.03: Version the event envelope and enforce compatibility rules

**ID:** events.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** [events.04, events.14]
**Estimated size:** L

**As a** backend engineer modifying an event payload,
**I need** a documented schema-version policy and a codec that validates `schema_version` on decode,
**so that** rolling deployments can run mixed producer/consumer versions without silent payload misinterpretation.

### Current State
- `EventBase.schema_version: int = 1` exists (`backend/events/types.py:20`) and the round-trip test at `backend/tests/events/test_types.py` accepts a `schema_version=2` payload without checks.
- `codec.decode_event` (`backend/events/codec.py:87-111`) reads `event_type`/`event_body` but never inspects or validates `schema_version`.
- The TODO at `backend/events/codec.py:44-47` explicitly asks for "schema_version field to serialized payloads for backward-compatible deserialization across deployments."
- No document describes when to bump the version, what counts as additive vs. breaking, or how to register a v2 model alongside v1.

### Acceptance Criteria
- [ ] `encode_event` writes `schema_version` as a top-level transport field (in addition to keeping it in the JSON body) so consumers can route without parsing the body.
- [ ] `decode_event` reads transport-level `schema_version`, compares it to the registered model's current version, and dispatches via a per-event-type version registry; an unknown version raises a typed `UnsupportedEventSchemaVersionError` with `event_type` and `schema_version` fields.
- [ ] A new `events/versioning.py` module documents the compatibility policy in its module docstring: additive optional fields = no bump, removed/renamed/required-added fields = bump, and registers `(event_type, schema_version) → model_class`.
- [ ] `EVENT_TYPE_REGISTRY` gains a per-version dimension (`dict[str, dict[int, type[EventBase]]]`) or is replaced by the new registry without breaking callers; `AnyEvent` continues to alias the current versions.
- [ ] `docs/ledger/event-catalog.md` gains a "Schema versions" section that lists every event's current version and a per-event change log; a doctring in `backend/events/types.py` cross-references the policy.
- [ ] Tests cover: (a) round-trip of a `schema_version=1` payload; (b) decode of an unknown `schema_version` raises the typed error; (c) registering and decoding a deliberate `schema_version=2` model for one event type.
- [ ] `pyright --strict` clean on `backend/events/`.

### Verification
- Run `cd backend && pytest tests/events/test_codec.py tests/events/test_types.py -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: encode a v1 event, hand-edit transport payload to `schema_version=99`, confirm `decode_event` raises `UnsupportedEventSchemaVersionError`.

### Code touch points
- `backend/events/codec.py` (modify)
- `backend/events/types.py` (modify — docstring + EventBase versioning hook)
- `backend/events/versioning.py` (new)
- `backend/events/exceptions.py` (new — or extend if existing)
- `backend/tests/events/test_codec.py` (modify)
- `docs/ledger/event-catalog.md` (modify)

---

## Story events.04: Auto-register event subclasses in EVENT_TYPE_REGISTRY

**ID:** events.04
**Status:** planned
**Prerequisites:** [events.03]
**Unblocks:** [agent.12, analytics.21, analytics.24, analytics.25, config.05, events.08, events.10, ingestion.18]
**Estimated size:** M

**As a** backend engineer adding a new event type,
**I need** new `EventBase` subclasses to register themselves automatically,
**so that** a single `class FooEvent(EventBase)` declaration is sufficient and there is no second hand-maintained `EVENT_TYPE_REGISTRY` literal to forget.

### Current State
- `EVENT_TYPE_REGISTRY` in `backend/events/codec.py:43-76` is a hand-maintained literal with one line per event type.
- The TODO at `backend/events/codec.py:44-47` calls for "auto-discovery from `EventBase` subclasses (use `__init_subclass__` or a class decorator)".
- `AnyEvent` in `backend/events/types.py:410-439` is also a hand-maintained union.
- Adding a new event today requires touching `types.py`, `codec.py`, and the `AnyEvent` union; missing any one causes a silent deserialization failure (`backend/events/codec.py:98-100`).

### Acceptance Criteria
- [ ] `EventBase.__init_subclass__` (or an equivalent class decorator) inspects the subclass's `event_type: Literal[...]` field and registers `(event_type, schema_version)` into the version registry from events.03 automatically.
- [ ] `EVENT_TYPE_REGISTRY` becomes a read-only view onto the auto-built registry, or is removed entirely and `decode_event` reads the new registry directly.
- [ ] Duplicate registrations (same `(event_type, schema_version)` from two classes) raise a clear `DuplicateEventTypeError` at import time, not at runtime.
- [ ] An optional `AnyEvent` type alias is preserved for static typing; a unit test cross-checks the alias contains every auto-registered class so a missing union entry is caught in CI.
- [ ] The TODO at `backend/events/codec.py:44-47` is removed; module docstring documents the auto-registration contract.
- [ ] Tests cover: (a) declaring a new `EventBase` subclass in the test file auto-registers it; (b) duplicate registration raises; (c) `AnyEvent` includes every registered model.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: add a throwaway `class FooEvent(EventBase): event_type: Literal["foo"] = "foo"` in a REPL and confirm `decode_event` round-trips it without editing `codec.py`.

### Code touch points
- `backend/events/types.py` (modify — `__init_subclass__` hook)
- `backend/events/codec.py` (modify)
- `backend/events/versioning.py` (modify)
- `backend/tests/events/test_codec.py` (modify)

---

## Story events.05: Propagate W3C Trace Context across stream events

**ID:** events.05
**Status:** planned
**Prerequisites:** [_observability.03]
**Unblocks:** [agent.09, api.05, api.20, monitoring.01, rag.13]
**Estimated size:** L

**As a** platform operator triaging a slow ingestion pipeline,
**I need** a producer span's W3C `traceparent` to flow through the event envelope into the consumer span,
**so that** Jaeger/Tempo shows a single end-to-end trace from the API request through every worker stage.

### Current State
- `EventBase` carries only `correlation_id` (`backend/events/types.py:14-20`); there is no `traceparent`/`tracestate` field.
- `shared/tracing.py:103` accepts a `correlation_id` attribute but exposes no inject/extract helpers for OTel context.
- `codec.encode_event` (`backend/events/codec.py:79-84`) emits only `event_type` + `event_body` on the wire.
- Architecture §11.3 requires "trace ID embedded in event metadata" for end-to-end pipeline traces.
- Cross-cutting prereq `_observability.03` adds the inject/extract helpers to `shared/tracing.py`.

### Acceptance Criteria
- [ ] `EventBase` gains optional `traceparent: str | None = None` and `tracestate: str | None = None` fields, persisted in the JSON body and exposed as transport-level fields by `encode_event`.
- [ ] A producer-side helper (in `events/tracing.py` or `events/codec.py`) injects the current OTel span context into a fresh event before publish; call sites that already have a span (API routers, coordinator handlers) use it.
- [ ] `RedisStreamsEventBus.publish` and `InMemoryEventBus.publish` either accept a pre-stamped event or auto-stamp from the current OTel context if the fields are unset, so producers do not have to remember.
- [ ] On consume, a helper extracts the trace context from the delivery and starts a consumer span linked to the producer's span; the coordinator's `run_handler_with_retry` (`backend/agent/coordinator.py:2345-2412`) uses it before invoking the handler.
- [ ] If `traceparent` is malformed or missing, the consumer span is started fresh and a structured log records the gap (no exception).
- [ ] `docs/ledger/event-catalog.md` notes that every event envelope carries optional W3C trace context.
- [ ] Tests cover: producer-side injection, consumer-side extraction, missing-context fallback.

### Verification
- Run `cd backend && pytest tests/events tests/agent -q`.
- Run `cd backend && pyright` and `ruff check backend/events backend/agent`.
- Manual: with `make dev` up, trigger a `POST /knowledgebases` request that publishes `kb.create`, then inspect Jaeger/Tempo (or stdout span exporter) to confirm the API request span and the worker handler span share a `trace_id`.

### Code touch points
- `backend/events/types.py` (modify — add `traceparent`/`tracestate`)
- `backend/events/codec.py` (modify — transport-level fields)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/adapters/in_memory.py` (modify)
- `backend/events/tracing.py` (new)
- `backend/agent/coordinator.py` (modify — extract on consume)
- `backend/tests/events/test_codec.py` (modify)
- `docs/ledger/event-catalog.md` (modify)

---

## Story events.06: Wire publisher retry/backoff and connection health on the Redis adapter

**ID:** events.06
**Status:** planned
**Prerequisites:** []
**Unblocks:** [agent.07, api.19, events.09, events.13, frontend.07]
**Estimated size:** L

**As a** backend engineer publishing events from an API route,
**I need** the Redis Streams publisher to retry transient connection errors with backoff and verify Redis health on startup,
**so that** a brief Redis blip does not silently drop critical pipeline events.

### Current State
- `RedisStreamsEventBus.publish` is a bare `xadd` with no retry, timeout, or backoff (`backend/events/adapters/redis_streams.py:36-44`).
- The TODO at `backend/events/adapters/redis_streams.py:37` enumerates "connection error handling with retry and backoff".
- `runtime.create_event_bus` (`backend/events/runtime.py:48-60`) constructs the client without a `PING` health check; misconfigured `REDIS_URL` only surfaces on the first publish.
- The TODO at `backend/events/runtime.py:50-53` also lists TLS/auth (`rediss://`, password, client certs) and connection-pool configuration as production gaps.

### Acceptance Criteria
- [ ] `RedisStreamsEventBus` accepts retry policy parameters (`max_attempts: int = 3`, `initial_backoff_ms: int = 50`, `max_backoff_ms: int = 1000`) or wraps publish in a `tenacity`-style retry loop with exponential backoff + jitter for `ConnectionError`/`TimeoutError` exceptions only (not `ResponseError`).
- [ ] `publish` enforces a configurable per-call timeout via `socket_timeout` on the Redis client; the default and override land in `EventBusSettings`.
- [ ] `create_event_bus` issues a `client.ping()` on construction and raises a typed `EventBusUnavailableError` if Redis is unreachable, so misconfiguration surfaces at startup.
- [ ] `EventBusSettings` gains `redis_socket_timeout_seconds`, `redis_connect_timeout_seconds`, `redis_max_connections`, and supports `rediss://` URIs and password/AUTH via `REDIS_PASSWORD` env var.
- [ ] When publish retries are exhausted, the original exception is re-raised with a typed `EventBusPublishError` wrapper carrying `event_type`, `attempt_count`, and `last_error`; callers (API routers, coordinator handlers) can catch one class.
- [ ] The TODOs at `backend/events/adapters/redis_streams.py:37-38` and `backend/events/runtime.py:50-53` are reduced to references to follow-up stories (e.g. retention is events.02, mTLS is _security.05).
- [ ] Tests cover: transient `ConnectionError` is retried and eventually succeeds; `ResponseError` is not retried; startup `PING` failure raises `EventBusUnavailableError`.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pytest -m integration tests/events/test_redis_streams.py -q` against `make dev`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: stop Redis, restart the API, confirm startup fails fast with `EventBusUnavailableError`; restart Redis, confirm the API comes up cleanly.

### Code touch points
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/runtime.py` (modify)
- `backend/events/exceptions.py` (new)
- `backend/tests/events/test_redis_streams.py` (modify)

---

## Story events.07: Make the in-memory adapter mirror Redis Streams semantics

**ID:** events.07
**Status:** planned
**Prerequisites:** [events.01]
**Unblocks:** [agent.08, monitoring.08]
**Estimated size:** M

**As a** backend engineer writing integration tests for consumer-group behaviour,
**I need** the in-memory adapter to model consumer groups, pending entries, and reclaim semantics,
**so that** tests for fan-out, multi-consumer ordering, and stale-claim recovery do not require a running Redis.

### Current State
- `InMemoryEventBus.ensure_consumer_group` is a no-op (`backend/events/adapters/in_memory.py:37-45`) with a `TODO(production)` to mirror Redis Streams semantics.
- The queue model tracks a single `delivered: bool` per entry (`backend/events/adapters/in_memory.py:13-77`); there is no per-consumer-group state and no Pending Entries List.
- `consume` returns matching entries without enforcing consumer-group fan-out (each group should see every entry exactly once, with PEL until ack).
- `tests/events/test_in_memory.py` (72 lines) only exercises basic publish/consume/ack and DLQ write.

### Acceptance Criteria
- [ ] `InMemoryEventBus` tracks state as `{(stream, consumer_group): {entry_id: PendingEntry(consumer_name, delivered_at, ack_count)}}` so each consumer group has independent PEL and offset.
- [ ] `consume` returns each entry exactly once per consumer group (matches Redis `XREADGROUP ">"`); a second group reading the same event types sees the same entries.
- [ ] Re-consuming with the same consumer name without ack returns the entry from the PEL on the next call (mirrors Redis behaviour when consumer reconnects).
- [ ] `consume` supports the same `claim_min_idle_ms` semantics from events.01: a different consumer name reclaims pending entries older than the threshold.
- [ ] `ack` removes entries from the PEL only for the matching `(stream, consumer_group)`; an unack'd entry stays visible to its group via reclaim.
- [ ] The TODO at `backend/events/adapters/in_memory.py:43` is removed.
- [ ] New tests in `tests/events/test_in_memory.py` cover: two consumer groups each get every event; reclaim across consumer names; per-group offset isolation.

### Verification
- Run `cd backend && pytest tests/events/test_in_memory.py -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: in a Python REPL, instantiate `InMemoryEventBus`, publish 3 events, consume with two distinct `consumer_group` names, confirm both groups receive all 3.

### Code touch points
- `backend/events/adapters/in_memory.py` (modify)
- `backend/tests/events/test_in_memory.py` (modify)

---

## Story events.08: CI check that every produced event is documented in the catalog

**ID:** events.08
**Status:** planned
**Prerequisites:** [events.04, _cicd.11]
**Unblocks:** []
**Estimated size:** M

**As a** reviewer of a PR that adds a new event type,
**I need** CI to fail if `docs/ledger/event-catalog.md`, the codec registry, and the `AnyEvent` union diverge from `backend/events/types.py`,
**so that** the documented event surface never silently drifts behind the code.

### Current State
- `docs/ledger/event-catalog.md` is hand-maintained against `backend/events/types.py` (see "Generated: 2026-05-22" note at the top of the file).
- After events.04 lands, the codec registry and `AnyEvent` union are auto-derived from subclasses, but the catalog markdown is still human-edited.
- Nothing in `.github/workflows/ci.yml` runs a drift check; a missing catalog entry today only surfaces via reviewer attention.
- The backlog-consistency CI step from `_cicd.11` provides a precedent for scripts that gate `docs/` content.

### Acceptance Criteria
- [ ] A new `scripts/event_catalog_check.py` script (or `pytest` collection test, see open question) inspects every `EventBase` subclass and asserts: (a) the catalog markdown contains a row referencing the `event_type` literal; (b) every catalog row resolves to a registered subclass; (c) the documented `schema_version` matches the model.
- [ ] The script exits non-zero on drift with a human-readable diff (`+ EventName: event_type` missing in catalog, etc.).
- [ ] CI invokes the script on every PR that touches `backend/events/` or `docs/ledger/event-catalog.md`; the step runs alongside the backlog-consistency check added by `_cicd.11`.
- [ ] The script has unit tests in `tests/scripts/test_event_catalog_check.py` covering: matching set passes; missing catalog row fails; orphaned catalog row fails; version mismatch fails.
- [ ] `docs/ledger/event-catalog.md` header is updated to remove the manual "Generated" timestamp and replaced with a "Verified by CI" note pointing at the script.
- [ ] Coverage on `scripts/event_catalog_check.py` ≥ 85%.

### Verification
- Run `python scripts/event_catalog_check.py` locally on a clean tree — exits 0.
- Hand-edit `event-catalog.md` to remove one row, rerun the script, confirm exit non-zero and clear diff.
- Run `cd backend && pytest tests/scripts/test_event_catalog_check.py -q`.
- Inspect `.github/workflows/ci.yml` and confirm the step gates on `paths:` for `backend/events/` and `docs/ledger/event-catalog.md`.

### Code touch points
- `scripts/event_catalog_check.py` (new)
- `tests/scripts/test_event_catalog_check.py` (new)
- `.github/workflows/ci.yml` (modify)
- `docs/ledger/event-catalog.md` (modify — header)

---

## Story events.09: Replay tool for re-processing events from a stream position

**ID:** events.09
**Status:** planned
**Prerequisites:** [events.06]
**Unblocks:** [events.10]
**Estimated size:** L

**As a** platform operator recovering from an incident,
**I need** a CLI that re-reads Redis Stream entries from a given position and either re-publishes them or invokes a handler directly,
**so that** I can backfill, replay missed deliveries, or re-process events without resetting a consumer group by hand.

### Current State
- There is no script under `scripts/` for replaying Redis stream entries (no `XRANGE`/`XREVRANGE` consumer exists outside the live consumer loop).
- The only retry path is the in-flight one in `backend/agent/coordinator.py:2345-2412 run_handler_with_retry`, which routes to DLQ on retry exhaustion rather than replaying earlier entries.
- DLQ replay is intentionally split into events.10; this story covers the live-stream replay surface.
- `backend/events/adapters/redis_streams.py` exposes no `range`-style reader on the protocol.

### Acceptance Criteria
- [ ] A new `scripts/replay_events.py` accepts `--stream`, `--start-id`, `--end-id` (default `+`), `--event-types`, `--dry-run`, and `--mode {republish, invoke}` flags; mode `republish` calls `EventBus.publish` for each entry, mode `invoke` calls the configured coordinator handler directly.
- [ ] The script uses the existing `EventBus` factory (`backend/events/runtime.py:48`) for transport so it honors the same retry/backoff/TLS settings landed in events.06.
- [ ] An `EventBus.range` (or `RedisStreamsEventBus.range`) method is added that wraps `XRANGE` and decodes each entry via `codec.decode_event`; type is `Iterator[EventDelivery]`.
- [ ] `--dry-run` lists matching entries with `event_id`, `event_type`, and `correlation_id` without re-publishing or invoking.
- [ ] Replay is idempotent against handlers that follow the project's upsert conventions (raw_records `content_hash`, `(entity_id, metric_name, observed_at)`); a docstring/README cross-references events.14 for non-idempotent handlers.
- [ ] The script ships with operator docs in `docs/wiki/` or a `scripts/README.md` explaining safe-use patterns (always start with `--dry-run`, double-check `--end-id`, prefer `republish` over `invoke` for production).
- [ ] Tests in `tests/scripts/test_replay_events.py` cover dry-run output, republish mode invokes `publish` once per entry, invoke mode dispatches to the right handler, type filter respected.

### Verification
- Run `cd backend && pytest tests/scripts/test_replay_events.py -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: with `make dev` up, publish 5 events, run `python scripts/replay_events.py --stream chili.kb.create --dry-run` and confirm 5 entries are listed; run with `--mode republish` and confirm the consumer processes them again.

### Code touch points
- `scripts/replay_events.py` (new)
- `backend/events/protocols.py` (modify — add `range` method)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/adapters/in_memory.py` (modify)
- `backend/tests/scripts/test_replay_events.py` (new)
- `scripts/README.md` (new or modify)

---

## Story events.10: Persist event dead-letter queue records

**ID:** events.10
**Status:** planned
**Prerequisites:** [events.04, events.09]
**Unblocks:** [events.15, ingestion.28]
**Estimated size:** L

### Narrative
As an operator,
I want failed event deliveries to be persisted in a dead-letter queue,
so that transient and poison-message failures can be inspected after the fact.

### Current State
Event publishing and retry behavior exist, but failed events are not exposed as durable operational records.

### Acceptance Criteria
- [ ] Event bus records exhausted delivery failures with event payload, handler, error, attempt count, and timestamps.
- [ ] Repository/API read paths list and fetch DLQ records with pagination.
- [ ] Sensitive payload fields are redacted according to existing event logging conventions.
- [ ] DLQ records are linked to original event IDs where available.

### Verification
- [ ] Unit tests force handler failures and confirm DLQ persistence.
- [ ] API tests cover listing and retrieving DLQ records.

### Code touch points
- `backend/app/events/**`
- `backend/app/api/**`
- `backend/tests/**`

---
## Story events.11: Tenant-aware stream-naming strategy

**ID:** events.11
**Status:** planned
**Prerequisites:** [_multitenancy.01]
**Unblocks:** [_multitenancy.11]
**Estimated size:** L

**As a** platform engineer enabling multi-tenancy,
**I need** a documented and enforced tenant-segmentation strategy for streams and consumer groups,
**so that** one tenant's events cannot be consumed by another tenant's worker and the `_multitenancy.md` adapter-layer promise is honored on the event bus.

### Current State
- `EventBusSettings.stream_name` returns `"{prefix}.{event_type}"` with no tenant segment (`backend/events/runtime.py:30-32`).
- Architecture §12.3 promises per-tenant data separation "at the adapter layer"; today every tenant shares one stream per event type with no enforcement.
- `_multitenancy.01` introduces the `TenantId` type; `_multitenancy.11` is the cross-cutting story that calls out the events stream-naming gap; this story owns the concrete events-module implementation.
- The open question in `docs/backlog/_epics_drafts/events.md` calls out stream-per-tenant vs. envelope-tenant-id-with-filter — a decision is required before the implementation can land.

### Acceptance Criteria
- [ ] A short ADR-style note in `backend/events/README.md` (new) records the chosen strategy: stream-per-tenant (preferred), envelope-with-filter (fallback), or hybrid; the note cites the open-question resolution.
- [ ] `EventBusSettings.stream_name` accepts an optional `tenant_id: str | None` argument and returns `"{prefix}.t.{tenant_id}.{event_type}"` when set; the `prefix` segment remains for cross-tenant ops streams.
- [ ] All call sites that publish or consume events (API routers, `agent/coordinator.py`, scripts from events.09) resolve the current `TenantId` from the contextvar landed in `_multitenancy.04` and pass it to `stream_name`.
- [ ] Consumer-group names are tenant-suffixed (e.g. `chili-workers.t.{tenant_id}`) so a worker can be pinned to a single tenant; multi-tenant workers must declare the tenant set explicitly.
- [ ] The `EventBus.consume` path rejects (with a typed `CrossTenantConsumeError`) any attempt to read a stream whose tenant segment does not match the active context, providing defense in depth against the "envelope-with-filter" failure mode.
- [ ] Tests cover: stream name includes tenant when context is set, falls back to non-tenant naming when context absent (legacy), cross-tenant consume raises.
- [ ] `docs/ledger/event-catalog.md` notes that stream names are tenant-prefixed in multi-tenant deployments.

### Verification
- Run `cd backend && pytest tests/events tests/api -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: with two tenants seeded, publish a `kb.create` as tenant A; `XLEN chili.t.B.kb.create` returns 0; `XLEN chili.t.A.kb.create` returns 1.

### Code touch points
- `backend/events/runtime.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/adapters/in_memory.py` (modify)
- `backend/events/exceptions.py` (modify — `CrossTenantConsumeError`)
- `backend/events/README.md` (new)
- `backend/agent/coordinator.py` (modify)
- `backend/api/routers/*.py` (modify — pass tenant context)
- `backend/tests/events/` (modify)
- `docs/ledger/event-catalog.md` (modify)

---

## Story events.12: Multi-region replication strategy for the event bus

**ID:** events.12
**Status:** planned
**Prerequisites:** [_infra.06]
**Unblocks:** []
**Estimated size:** L

**As a** platform architect planning beyond a single-region deployment,
**I need** a documented and codified multi-region replication strategy for the event bus,
**so that** consumer-group semantics, ordering, and cross-region failover are explicit decisions rather than emergent behaviour.

### Current State
- Redis Streams is a single-instance Redis primitive; neither `backend/events/runtime.py` nor `docker-compose.dev.yaml` references Redis Sentinel, Redis Cluster, or cross-region replication.
- Architecture §14.2 lists CI/CD geo-distribution as future work but no equivalent statement exists for the event bus.
- `_infra.06` provides production persistent-volume strategy for stateful services (Neo4j, Qdrant, MinIO, Postgres); Redis HA topology should land alongside it.
- The open question in `docs/backlog/_epics_drafts/events.md` (stay on Redis Streams vs. migrate to Redpanda/Kafka) must be resolved by this story.

### Acceptance Criteria
- [ ] A new design document `docs/superpowers/specs/2026-XX-XX-event-bus-multi-region.md` records the decision: (a) Sentinel HA single-region, (b) Redis Cluster cross-AZ, (c) active-active via Kafka/Redpanda migration, or (d) accept single-region with documented RPO/RTO; the spec cites architecture §14.2.
- [ ] `EventBusSettings` gains fields required by the chosen strategy: Sentinel master/sentinels list, cluster nodes, or substrate-selector (`backend: Literal["in-memory", "redis", "redis-sentinel", "redis-cluster", "kafka"]`); only adapters that exist actually become legal values per the project's "no Literal without adapter" rule (see CLAUDE.md §"External systems live behind protocols + adapters").
- [ ] If Sentinel is chosen, `RedisStreamsEventBus` is updated to use `redis.sentinel.Sentinel` and `create_event_bus` accepts a sentinel topology; the in-memory adapter is unaffected.
- [ ] If migration to Kafka/Redpanda is chosen, this story splits into a follow-up implementation story and lands the decision + interface contract only.
- [ ] `infra/helm/chili/values.yaml` and `_infra.06` Helm bits gain the replication topology values; the chart-test CI from `_cicd` validates rendering.
- [ ] `docs/ledger/event-catalog.md` and `backend/events/README.md` (from events.11) cross-reference the chosen strategy and its per-event guarantees.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Run `helm lint infra/helm/chili` and `helm template infra/helm/chili --values infra/helm/chili/values-prod.yaml` — confirms the new replication values render.
- Manual: stand up a Sentinel topology in `make dev`, kill the master, confirm `chili-worker` continues consuming after promotion.

### Code touch points
- `docs/superpowers/specs/2026-XX-XX-event-bus-multi-region.md` (new)
- `backend/events/runtime.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify or replace based on decision)
- `infra/helm/chili/values.yaml` (modify)
- `infra/helm/chili/templates/` (modify)
- `backend/events/README.md` (modify)
- `docs/architecture.md` (modify — §14.2 cross-reference)

---

## Story events.13: Document and codify producer delivery guarantees

**ID:** events.13
**Status:** planned
**Prerequisites:** [events.06]
**Unblocks:** []
**Estimated size:** M

**As a** backend engineer adopting a new event,
**I need** the publish path's delivery contract (at-least-once vs. at-most-once, replication-ack semantics) to be documented and per-event-type-overridable,
**so that** handlers can be designed against an explicit guarantee rather than an unstated one.

### Current State
- `RedisStreamsEventBus.publish` returns the `xadd` message ID but has no confirmation hook (`backend/events/adapters/redis_streams.py:36-44`).
- There is no `WAIT`/replication acknowledgement and the in-memory adapter returns a synthetic ID (`backend/events/adapters/in_memory.py:30-35`).
- The codebase has no "at-least-once vs. at-most-once" statement; `docs/ledger/event-catalog.md` does not capture per-event delivery expectations.
- Once events.06 lands publisher retry, the guarantee becomes "at-least-once on persistent failure, single-replica on success"; this story codifies it.

### Acceptance Criteria
- [ ] A new section in `backend/events/README.md` (from events.11) titled "Delivery guarantees" describes the platform default ("at-least-once, durable to the local Redis replica") and the conditions under which a stronger or weaker guarantee applies.
- [ ] `EventBusSettings` gains `publish_wait_replicas: int = 0` and `publish_wait_timeout_ms: int = 0`; non-zero values cause `RedisStreamsEventBus.publish` to issue `WAIT n timeout` after `xadd` and raise `EventBusReplicationTimeout` on under-replication.
- [ ] `docs/ledger/event-catalog.md` gains a "Delivery guarantee" column per event with the platform default plus per-event overrides (e.g. `alerts.created` may opt into `wait_replicas=1`).
- [ ] Architecture §11.3 (or a new §11.5) is updated to state the platform default and link to the events README.
- [ ] Tests cover: default behaviour (`WAIT` not called); `publish_wait_replicas>0` invokes `WAIT`; replication timeout raises the typed error.

### Verification
- Run `cd backend && pytest tests/events -q`.
- Run `cd backend && pyright` and `ruff check backend/events`.
- Manual: with a single-replica Redis and `publish_wait_replicas=2`, publish an event, confirm `EventBusReplicationTimeout` is raised after the timeout.

### Code touch points
- `backend/events/runtime.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/exceptions.py` (modify)
- `backend/events/README.md` (modify)
- `backend/tests/events/test_redis_streams.py` (modify)
- `docs/ledger/event-catalog.md` (modify)
- `docs/architecture.md` (modify)

---

## Story events.14: Idempotency-key support on the event envelope

**ID:** events.14
**Status:** planned
**Prerequisites:** [events.03]
**Unblocks:** []
**Estimated size:** L

**As a** handler author writing a non-idempotent consumer,
**I need** an envelope-level idempotency key and a shared dedup store,
**so that** a re-delivered event (via reclaim, replay, or DLQ retry) cannot cause double-writes for handlers that are not naturally idempotent on a domain key.

### Current State
- `EventBase` carries no `idempotency_key` field (`backend/events/types.py:14-20`).
- Handlers in `agent/coordinator.py` rely on downstream upsert keys (raw_records `content_hash`, `(entity_id, metric_name, observed_at)`) for replay safety; see comments at `backend/agent/coordinator.py:1487`, `:1545`, `:1616`, `:1716`.
- The monitoring dedup window (`backend/monitoring/service.py:79`) operates on alert candidates, not on raw event deliveries; a re-delivered `RiskScoredEvent` can still double-write downstream rows when handlers do not own a natural upsert key.
- No per-event-type dedup table exists.

### Acceptance Criteria
- [ ] `EventBase` gains optional `idempotency_key: str | None = None`, persisted and round-tripped by `codec.encode_event`/`decode_event`; existing events default to `None` and behaviour is unchanged.
- [ ] Producers that need dedup (e.g. records ingestion, monitoring alert pipeline, risk scoring) set `idempotency_key` deterministically from the domain payload (documented per-event in `event-catalog.md`).
- [ ] A new `events.dedup.DedupStore` protocol with Redis and in-memory adapters exposes `seen(key: str, ttl_seconds: int) -> bool`; `True` means the key has been seen within the TTL and the handler should skip.
- [ ] The coordinator's `run_handler_with_retry` (`backend/agent/coordinator.py:2345-2412`) consults the dedup store before dispatch when `idempotency_key` is set; duplicates are ack'd without re-running the handler and a structured log records the skip.
- [ ] Per-event-type opt-in/opt-out configuration lives in `EventBusSettings` (default opt-out so existing handlers retain their current behaviour); events that opt in document their idempotency-key derivation in the catalog.
- [ ] Tests cover: encode/decode preserves `idempotency_key`; dispatcher skips duplicates; dedup store TTL expires correctly; multi-handler subscribers each get the event once on first delivery and skip on re-delivery.
- [ ] `docs/ledger/event-catalog.md` gains an "Idempotency key" column per event identifying the derivation source.

### Verification
- Run `cd backend && pytest tests/events tests/agent -q`.
- Run `cd backend && pyright` and `ruff check backend/events backend/agent`.
- Manual: publish the same `risk.scored` event twice (same `idempotency_key`), confirm the handler runs once and the second delivery logs a `dedup_skip` line.

### Code touch points
- `backend/events/types.py` (modify)
- `backend/events/codec.py` (modify)
- `backend/events/dedup.py` (new)
- `backend/events/runtime.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/tests/events/` (modify)
- `backend/tests/agent/test_coordinator.py` (modify)
- `docs/ledger/event-catalog.md` (modify)

## Story events.15: Add DLQ replay and purge APIs

**ID:** events.15
**Status:** planned
**Prerequisites:** [events.10]
**Unblocks:** [events.16]
**Estimated size:** L

### Narrative
As an operator,
I want to replay or purge dead-lettered events,
so that recoverable failures can be retried and obsolete records can be cleared safely.

### Acceptance Criteria
- [ ] API supports replaying selected DLQ records back through the event bus.
- [ ] API supports purging selected or expired DLQ records with authorization checks.
- [ ] Replay preserves correlation IDs and records the replay attempt outcome.

### Verification
- [ ] API tests cover replay success, replay failure, purge, and authorization rejection.
- [ ] Event bus tests prove replayed events use normal handler dispatch.

### Code touch points
- `backend/app/events/**`
- `backend/app/api/**`
- `backend/tests/**`

---

## Story events.16: Add DLQ operations UI hooks and audit coverage

**ID:** events.16
**Status:** planned
**Prerequisites:** [events.15]
**Unblocks:** [api.25, monitoring.07, monitoring.16]
**Estimated size:** M

### Narrative
As an operator,
I want DLQ actions to be observable and auditable,
so that replay and purge operations can be reviewed after incident response.

### Acceptance Criteria
- [ ] DLQ replay and purge emit audit events with actor, record IDs, and outcomes.
- [ ] API responses include enough metadata for an operations UI to render status and errors.
- [ ] Tests cover audit records for successful and failed DLQ actions.

### Verification
- [ ] Run API tests that assert audit records for replay and purge actions.
- [ ] Confirm operations documentation describes the DLQ action lifecycle.

### Code touch points
- `backend/app/events/**`
- `backend/app/monitoring/**`
- `docs/wiki/modules/events.md`

---
