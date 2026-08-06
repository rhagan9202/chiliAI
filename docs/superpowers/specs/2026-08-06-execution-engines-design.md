# Execution Engines: Score-All, Connector Sync, Workflow Runs

**Date:** 2026-08-06
**Status:** design approved; implementation not started
**Scope:** three executors + the shared seam they run on
**Closes:** the executor gaps in `SAFE-CMS-002`, `SAFE-CMS-014`, `SAFE-CMS-015`, `SAFE-CMS-017`

## 1. Problem

Three subsystems expose an API that persists a `queued` record which **nothing ever executes**:

| Subsystem | Entry point | What happens | What never happens |
|---|---|---|---|
| Score-all | `POST /knowledgebases/{kb}/score-runs` | `ScoreRun` + `ScoreBatch` rows created, `ScoreRunStatusChangedEvent` published | no consumer; batches stay `queued`, `scored_entities` stays 0 |
| Workflows | `POST …/workflow-definitions/{id}/versions/{v}/run` | `WorkflowRun` saved `QUEUED`, run request audited | no event published, no consumer; steps never run |
| Connectors | `POST …/connectors/{id}/sync-runs` | `ConnectorSyncRun` created `queued` | no source adapter, no consumer; no data moves |

An operator gets HTTP 200 in every case. `replay_failed_batches` always raises, because no batch can reach `failed`. `ScoreBatch.attempts` is dead config.

Two of the three are also not durable: `get_score_run_repository` and `get_connector_repository` return in-memory adapters unconditionally (`backend/api/dependencies.py:2708,2745`) with no migration, so state is process-lifetime. An executor over process-lifetime state is pointless — persistence is a prerequisite, not a follow-up.

## 2. What already exists (verified against code, 2026-08-06)

The substrate is mature and is **not** being rebuilt:

- Redis Streams with consumer groups; `reclaim_stale_pending` implements XPENDING/XCLAIM recovery of events orphaned by a crashed worker.
- `run_handler_with_retry` (`agent/coordinator.py:4189`): exponential backoff, `retry_policy.max_retries`, per-stage overrides, DLQ publish on exhaustion, then a durable `DlqRecord`. **`policy.fatal_exception_types` short-circuits retry** — that is how an executor signals "this will never succeed, dead-letter now".
- `WorkflowEventTracker`: `begin_event` gating, `fail_event`, `is_run_cancelled`, and `reconcile_stale_runs` (`agent/workflow_tracking.py:198`) which fails `QUEUED`/`RUNNING` runs older than `CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS`.
- Config hot-swap happens **between** drain iterations only, so an in-flight event completes with the dependencies it started with.

Per-subsystem, more exists than the audit implied:

- **`assess_entities`** (`agent/coordinator.py:3026`) already scores a list of entities, tolerates entities below the signal floor, publishes `RiskScoredEvent`, and persists to `risk_score_history` under a **deterministic request id** — so re-running a batch is already idempotent at the scoring layer.
- **`ScoreRunService.score_request_id(run_id, batch_number, entity_id)`** exists with **zero production callers**. It is the intended seam.
- `ScoreRun`/`ScoreBatch` carry status, counters, `attempts`, `idempotency_key`, `replay_of_run_id`, timestamps.
- `ConnectorSyncRun` carries `counters` (pulled/accepted/quarantined/failed), `source_cursor`, `ingest_correlation_id`, `error_message`.
- `WorkflowRetryPolicy` (`max_attempts`) and `WorkflowFailureMode` (`fail_workflow`/`continue`/`require_approval`) are **typed models**, not strings. Only `WorkflowStepDefinition.condition: str | None` is unparsed.

Gaps that are real:

- `CapabilityRegistryService` has **no `execute()`**. It can `register`, `get`, `list_capabilities`, `authorize`, and construct success/failure envelopes. Nothing dispatches.
- `connectors/adapters/` contains `in_memory.py`, a **repository** — there is no source adapter for any of `filesystem | object_store | http`.
- **`WorkflowStepState` has no attempts field** — only `step_name`, `status`, `metadata` (`agent/models.py:91`). Per-step retry needs a model change or must live in `metadata`.

## 3. Architecture

### 3.1 The seam

A new `backend/execution/` module owns executor dispatch. The worker keeps consume/reclaim/retry/DLQ/ack/cancellation and gains one delegation point.

```
drain_ingestion_events
  └─ run_handler_with_retry(_run_handler)      unchanged: retry, DLQ, ack
       ├─ handle_event(...)                     unchanged: 14 pipeline branches
       └─ execution.dispatch(delivery, deps)    new
            ├─ analytics/score_runs/executor.py
            ├─ connectors/executor.py
            └─ workflow_definitions/executor.py
```

`execution/registry.py` maps `event_type → handler`. Handlers take `(event, ExecutionDeps)` — one frozen dataclass — rather than the ~40 hand-forwarded kwargs `handle_event` takes today. `ExecutionDeps` is **derived from the existing `WorkerDependencies`** (45 fields), so wiring has one source and no second adapter-construction path appears.

Rationale: `agent/coordinator.py` is 4,723 lines and `handle_event` is a 14-branch `isinstance` chain. Adding three executors there would push it past 5,500 lines and `WorkerDependencies` past 55 fields, worsening the exact structure the 2026-08-06 audit flagged.

**Hard constraint — executors must not fork retry/DLQ semantics.** An executor raises; the existing wrapper decides retry vs dead-letter. An executor that catches its own exceptions and returns normally silently breaks the DLQ contract and makes a failure invisible. Use `fatal_exception_types` on the stage policy for "never retry this".

### 3.2 Unit of work

One event per **batch / step / page**. Retry, DLQ and cancellation then inherit per-event semantics for free, and the granularity matches the replayable unit the data models already describe.

| | Score-all | Connectors | Workflows |
|---|---|---|---|
| Unit | `ScoreBatch` | source page | step |
| Event | `score.batch.queued` | `connector.page.queued` | `workflow.step.queued` |
| Attempt counter | `ScoreBatch.attempts` ✅ | `ConnectorSyncRun.counters` | **none — see §6.3** |
| Resume cursor | `batch_number` | `source_cursor` ✅ | `step_id` |
| Idempotency key | `score_request_id()` ✅ | `ingest_correlation_id` ✅ | `run_id + step_id` |

Each handler: **claim unit → check run not cancelled → do work → update counters → enqueue next unit → terminal-state the run when none remain.**

### 3.3 Chain integrity

Chaining is the failure mode this design accepts and must mitigate: a dropped link stalls a run with no error. Mitigation is the existing reconciler — `reconcile_stale_runs` extended to score runs and connector syncs, failing a run that has no in-flight unit, no terminal state, and no progress within `max_age_seconds`. Without this, a lost event is an indefinitely `running` run.

## 4. Per-subsystem design

### 4.1 Score-all (smallest gap)

**Prerequisites:** Postgres `score_runs` + `score_batches` tables and a `PostgresScoreRunRepository`. The repository protocol and models already exist; only the adapter, migration and DI branch are missing.

**Executor:** consumes `score.batch.queued` → loads the batch → `assess_entities(risk_service, kb, batch.entity_ids, correlation_id=score_request_id(...))` → updates `scored_entities`/`failed_entities` → marks the batch `completed` → enqueues the next `queued` batch → when none remain, marks the run `completed`.

**Enumeration moves out of the request handler.** Today `POST /score-runs` does `entity_ids = [e.id for e in graph_repository.get_entities(kb)]` synchronously (`api/routers/score_runs.py:98`) and materializes the whole list into batch rows — risk R2 from the surge's own register, unmitigated. The run is created with `total_entities=0` and a cursor; the executor pages entities and creates batches as it goes.

### 4.2 Connector sync

**Prerequisites:** Postgres `connectors` + `connector_sync_runs` tables and adapter; **one** source adapter. Ship `filesystem` first — `object_store` and `http` are separate stories, and `source_type` must reject unimplemented values rather than accepting them silently.

**Executor:** consumes `connector.page.queued` → reads one page from the source adapter at `source_cursor` → validates rows against the feed schema → quarantines invalid rows → persists accepted rows → publishes **the same `RecordsIngestedEvent` the manual path publishes** (`records/service.py:110`, `correlation_id`, `knowledge_base_id`, `feed_name`, `record_type`, `record_count`, only when `accepted > 0`) → advances `source_cursor` → enqueues the next page.

**Ordering rule:** `source_cursor` advances **only after** the ingest event is durably published. Advancing first means a crash between persist and publish skips those records forever.

**Scheduling is out of scope.** `interval`/`cron` modes stay unimplemented; manual trigger only. `ConnectorScheduleMode` must reject the unimplemented values at config load rather than storing a mode nothing honours.

### 4.3 Workflow runs (largest gap)

**Prerequisites:**

1. **`CapabilityRegistryService.execute()`** — dispatch by capability id to a registered executor callable, returning the existing `CapabilityExecutionEnvelope`.
2. **Fail-closed `authorize()`.** Today it fails open three ways:
   - `domain_name=None` skips the domain check (`capabilities/service.py:78`)
   - `environment_tag=None` skips the environment check (`:89`)
   - empty `required_roles` returns `True` for everyone — in **two** functions, `_roles_can_access` (`:190`) and `_role_can_access` (`:201`). Both must change; fixing one leaves the bypass reachable through the other.

   All become live bypasses the moment a dispatcher exists. Each becomes a denial, and the dispatcher always passes full context (kb, domain, environment, roles). Needs one negative test per branch — four branches, not three.
3. **A safe `condition` evaluator.** `condition` is a free string. `eval()` is a remote-code-execution surface in a user-authored workflow engine. Use a restricted comparison grammar over previous step outputs — no attribute access, no calls.
4. **Server-side approval gating.** `requires_human_approval` is read only at authoring time and in the UI. The executor must halt the run at an approval step and refuse to proceed without a recorded approval.

**Executor:** consumes `workflow.step.queued` → evaluates `condition` (skip if false) → if `requires_human_approval` and unapproved, park the run `awaiting_approval` → `capability_registry.execute(...)` with full context → apply `on_failure` (`fail_workflow` / `continue` / `require_approval`) → record the step → enqueue the next step.

**Every capability execution writes an audit event.** `CapabilityPermission.requires_audit` and `CapabilityExecutionEnvelope.audit_required` are currently read by nothing outside tests. The dispatcher is where that flag becomes real.

## 5. Events

New types in `backend/events/types.py`, added to `AnyEvent`, the codec, and `WORKER_EVENT_TYPES`:

| Event | Carries |
|---|---|
| `score.batch.queued` | `run_id`, `batch_id`, `knowledge_base_id`, `batch_number` |
| `connector.page.queued` | `connector_id`, `run_id`, `knowledge_base_id`, `cursor` |
| `workflow.step.queued` | `workflow_id`, `definition_id`, `version`, `step_id`, `knowledge_base_id` |

Each carries only identifiers — the executor reloads state from its repository. Payloads must not carry mutable state, or a redelivered event resurrects a stale snapshot.

`docs/ledger/event-catalog.md` must be updated in the same change; it was already 4 members stale before this work.

## 6. Edge cases the implementation must handle

Each needs a test.

### 6.1 Two replay paths can double-execute
`replay_failed_batches` (API) and DLQ replay (`POST /events/dlq/{id}/replay`) can both re-drive the same batch. `score_request_id` makes the *scoring* idempotent, but counter updates are not — a replayed batch would double-count `scored_entities` and can trip the model validator. **Counter updates must be derived from batch state, not incremented blindly.**

### 6.2 Counter validator can reject a valid update
`ScoreRun` validates `scored_entities + failed_entities <= total_entities`. If entities are deleted mid-run, or `total_entities` is computed before enumeration completes, a legitimate update raises `ValidationError` and the handler dead-letters on correct behaviour. Reconcile counts against batch state and clamp, or make `total_entities` authoritative only at completion.

### 6.3 Workflow step retry has nowhere to record attempts
`WorkflowStepState` has no `attempts` field, but `WorkflowRetryPolicy.max_attempts` exists per step. Either extend the model (migration) or store attempts in `WorkflowStepState.metadata`. **Decide explicitly** — silently not enforcing `max_attempts` would repeat the "config that nothing reads" pattern.

### 6.4 Duplicate delivery
Redis Streams is at-least-once. Every handler must tolerate the same unit being delivered twice, including after a reclaim.

### 6.5 Config hot-swap mid-run
Dependencies rebuild between drains, so a run started under pack A can finish under pack B — with a `catalog_version` that no longer matches the active config. Record the version at run creation and either pin it or fail the run loudly on mismatch; do not let it silently change meaning.

### 6.6 Connector partial-page failure
Covered by the ordering rule in §4.2. The test must kill the executor between persist and publish and assert no records are skipped.

### 6.7 Cancellation mid-run
`is_run_cancelled` is checked per event. Each handler must check **before** doing work and stop enqueueing successors, so a cancel lands within one unit rather than at the end of the run.

### 6.8 Approval parking is not a failure
A workflow parked at an approval step must not be reaped by `reconcile_stale_runs` as a stalled run. `awaiting_approval` must be excluded from staleness, or an approval left overnight fails the run.

## 7. Testing

- **Unit** per executor against in-memory repositories: happy path, duplicate delivery, cancellation, terminal failure, chain-enqueue.
- **Repository/migration tests** for the two new Postgres adapters, matching the existing pattern — and using `Path(__file__).resolve().parents[2]`, not a cwd-relative path (five surge tests shipped unrunnable that way).
- **Negative security tests** for the dispatcher: unregistered capability, wrong role, wrong domain, wrong environment, empty `required_roles`, and a step requiring approval without one. Each must assert denial, not merely that the happy path works.
- **Integration** against the live stack: start a score-all on the TN subset and assert it reaches `completed` with `scored_entities == total_entities`; kill the worker mid-run and assert reclaim resumes it.
- Coverage ≥ 85% per package, per the project standard.

## 8. Sequencing

Three stories, in dependency order:

1. **Score-all** — proves the `execution/` seam with the smallest gap. Persistence + executor + enumeration move.
2. **Connectors** — reuses the seam end-to-end; adds persistence, the filesystem source adapter, and ingest-event parity.
3. **Workflows** — last, because it needs the fail-closed `authorize()` rework, `execute()`, the condition evaluator and approval gating, and benefits from the seam being settled.

Each gets its own implementation plan and ships independently.

## 9. Out of scope

Named so they are not assumed delivered: connector scheduling (`interval`/`cron`); `object_store` and `http` source adapters; a workflow authoring UI; parallel step execution (steps run sequentially); and the governance eval runner, which is a separate gap.

## 10. Decisions taken

These were open during design and are settled here so implementation does not have to guess. Each is a judgement call, flagged for override.

**D1 — Workflow step attempts (§6.3): extend `WorkflowStepState` with `attempts: int = 0`.**
`metadata` is a `dict[str, MetadataValue]` with no schema, so a counter there is invisible to type checking and to anyone reading the model. `WorkflowStepState` is stored inside `WorkflowRun`, which the run store persists as a whole — so this is a model change, not a table migration, and existing rows deserialize with the default. The alternative — leaving `max_attempts` unenforced — would reproduce the "config nothing reads" pattern this work exists to remove.

**D2 — `total_entities` (§6.2): authoritative only at completion.**
Because §4.1 moves enumeration into the executor, the true total is not known when the run is created. The run starts at `total_entities=0`; each batch creation increments it; the terminal transition reconciles it against summed batch state. The `scored + failed <= total` validator therefore holds throughout instead of being tripped by a legitimate mid-run update. Counter updates are **derived from batch state, not incremented** (§6.1), which makes them idempotent under replay.

**D3 — Concurrent score-all runs for one KB: rejected with 409.**
`start_score_all` already supports `idempotency_key`; this extends it to refuse a new run while one is `queued` or `running` for the same KB. Two concurrent runs would race on `risk_projections` with last-write-wins and make `scored_entities` meaningless across runs. Replay of a failed run is unaffected — it targets an existing terminal run rather than starting a new one.

## 11. Open questions

None blocking. D1–D3 above are the calls that were open; raise them if any is wrong before implementation starts.
