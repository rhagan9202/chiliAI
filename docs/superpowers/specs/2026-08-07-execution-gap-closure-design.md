# Execution Gap Closure — Design

**Date:** 2026-08-07
**Status:** approved (design decisions D1–D3 settled with the product owner)
**Follows:** `2026-08-06-execution-engines-design.md` (score-all, connector sync, workflow run executors — all three merged to prod)

## 1. Why this exists

The three execution engines shipped. This closes the gaps they left, plus five
more found by auditing the code around them.

The engines were built to fix one defect class: **an API returns 200, writes a
row, and nothing ever executes it.** Closing that in three places surfaced the
same shape in five more, and a second, related class:

> **Identifier drift** — the thing that *declares* a feature and the thing that
> *implements* it use different names, so both halves exist and neither works.

Four instances found: a capability adapter whose id no manifest declares
(`analytics.peer_analysis`), a manifest whose module does not exist
(`evidence.packs`), an event type with no producer (`alert.created`), and — fixed
during the workflow executor work — a built-in capability list naming
`human.approval`, which has no manifest.

Neither class is caught by unit tests, because both halves are individually
correct. They are caught by running the thing.

## 2. Gaps

Severity is "what does a user experience", not "how hard is the fix".

### Tier 1 — Work is accepted and silently never done

| ID | Gap | Evidence |
|---|---|---|
| **G1** | A run parked on a human approval gate is **permanently stuck**. Nothing writes `approved.<step_id>`; and even if it did, the parking event was already acked, so no event exists to resume from. `AWAITING_APPROVAL` is (correctly) excluded from stale reconciliation, so it is never reaped either. | `workflow_definitions/executor.py:123,384`; ack is unconditional in `agent/coordinator.py` `_drain_once` |
| **G5** | `POST /score-runs/{id}/replay` returns 200 with queued batches and **executes nothing**. `replay_failed_batches` publishes `ScoreRunStatusChangedEvent` — a notification the worker does not consume — but never `ScoreBatchQueuedEvent`. | `analytics/score_runs/service.py:185-216`. Live-confirmed 2026-08-07: replayed run stayed `queued`, `scored=0`, indefinitely. |
| **G4** | Connector sync runs have **no reconciler**, and `ConnectorRepositoryProtocol` has no stale-scan method. A run whose page event is lost stays `running` forever. Score runs and pipeline runs both have one. | `connectors/`, `agent/coordinator.py` reconciliation tick |

G1 and G5 are the same defect the execution-engines effort existed to remove,
surviving on the *resume* and *replay* paths rather than the start path. Both
were verified on the start path and neither on its sibling.

### Tier 2 — An implementation exists but cannot be reached

| ID | Gap | Evidence |
|---|---|---|
| **G10** | `analytics/peerstats/capability.py` is a complete workflow-facing adapter under id `analytics.peer_analysis`. **No manifest declares that id.** The registry declares `analytics.peer_context`, which **no adapter implements.** Two halves of one feature under different names. | `analytics/peerstats/capability.py:13`; `capabilities/registry.py:74` |
| **G3** | Four of five registered capabilities have no bound executor and report `capability_not_executable`. Three have real backing services (`rag/`, `analytics/peerstats/`, `cases/`). | `capabilities/builtin_executors.py` binds only `connector.sync.status` |
| **G7** | `evidence.checklist.generate` declares `module="evidence.packs"`, which **does not exist** (real module: `analytics/explainability/`). `module` is not cosmetic — it is a filter in the browse API and is returned to clients. | `capabilities/registry.py:180`; `capabilities/service.py:327`; `api/routers/capabilities.py:106` |

### Tier 3 — Unbounded reads

| ID | Gap | Evidence |
|---|---|---|
| **G6** | `GraphRepository.get_entities` has **no LIMIT at all** — it materialises every entity in a knowledge base in one query. A paginated `get_entities_by_type(kb, type, limit, offset)` already exists, so the shape is established. Two callers: score-run enumeration and the GNN snapshot source. | `graph/adapters/neo4j_adapter.py:556` vs `:779` |

### Tier 4 — Surfaces that exist but do nothing

| ID | Gap | Evidence |
|---|---|---|
| **G8** | The WebSocket alert stream **has no producer**. `AlertCreatedEvent` is never constructed outside a test, and the hub documents this itself: *"does not subscribe to Redis Streams — the event bus bridge is added in Epic 8."* The route accepts subscribers, applies severity filters, and emits nothing. | `api/routers/ws.py:88,212`; `events/types.py:428` |
| **G2** | The dashboard does not count or filter `awaiting_approval`, so a parked run is invisible in its tiles. (`RunTimeline` was fixed when the status was added; `DashboardPage` was not.) | `chili_app/src/pages/DashboardPage.tsx:174-180` |
| **G9** | `CapabilityExecutor` is `Mapping -> Mapping` with no context argument, so the calling actor rides in the business payload. Separately, the two existing adapters authorize *internally*, a second calling convention parallel to `execute()` that causes double authorization. | `capabilities/executors.py`; `workflow_definitions/rag_adapter.py`; `connectors/status_adapter.py` |

### Confirmed *not* broken

Stated because the pattern invites suspicion of every similar surface:

- **Scorecard `/runs`** computes synchronously in the request and works.
- **DLQ replay** genuinely republishes the original event.
- **`get_entities_by_type`** is real pagination (`ORDER BY entity_id`, `SKIP`/`LIMIT`).

## 3. Design decisions

### D1 — Approval is an endpoint that republishes

`POST /knowledgebases/{kb}/workflows/{run_id}/steps/{step_id}/approve`

1. records the approver and timestamp on the run,
2. **publishes `workflow.step.queued` for that step**, and
3. writes a `workflow.step.approved` audit record.

A sibling `/reject` fails the run with the reason recorded.

Republishing from the endpoint is what makes the resume work. The alternative —
recording the decision and letting a reconciler sweep pick it up — was rejected:
it adds latency equal to the tick interval and introduces a second thing that
can stall, to solve a problem the request path can solve directly.

**Approval must be a distinct role from the requester.** A gate an actor can
satisfy for their own run is not a gate; the endpoint requires `supervisor`
(the role that already approves definitions and governance baselines) and
rejects self-approval.

### D2 — Bind the three capabilities that have services; do not invent the fourth

`rag.query`, `analytics.peer_context` and `case.note.draft` get bound executors.
`evidence.checklist.generate` keeps reporting `capability_not_executable` — but
its **phantom module reference is corrected**, because a browse API filter that
names a non-existent module is wrong regardless of whether the capability runs.

`analytics.peer_context` resolves G10 by binding the **existing**
`peerstats/capability.py` adapter to the manifest's id. The id on the adapter
(`analytics.peer_analysis`) is the one that changes, because the manifest id is
the published contract — workflow definitions reference it, and the browse API
returns it.

### D3 — Fix the drift class, not just the instances

Each drift instance gets a **coherence test** that fails when the two halves
disagree, not merely a corrected value:

| Drift | Coherence test |
|---|---|
| adapter id vs manifest id | every bound executor id is a registered manifest id (exists); **every manifest names a module that imports** (new) |
| event type vs producer | every non-notification event type has a producer, or is explicitly listed as notification-only |
| built-in capability list vs registry | derived, not written twice (done 2026-08-07) |
| run status vs API projection | exhaustive map that raises on an unmapped status (done 2026-08-07) |

The corrected value fixes today. The coherence test is what stops it recurring,
and the recurrence is the actual problem — four instances of one mistake.

## 4. Verification doctrine

This section is the most important artifact here. Across the three execution
engines, **eleven defects passed a green unit suite and were caught by running
the code.** Every plan below inherits these rules.

### 4.1 A test that cannot fail is not a test

Before trusting a guard, **break the thing it guards and watch it fail.** The
registration guard in `tests/execution/` was verified this way; the projection
map was not, and shipped a lie. Where a plan adds a guard, it also specifies the
mutation that must make it red.

### 4.2 In-process tests cannot discover unreachability

A test that imports the executor and calls it directly can never find that
nothing reaches it. These defects were all invisible in-process:

- an executor registry that no module populated (`dispatch` returned 0 forever)
- a chain that advances itself but that nothing starts (twice: connector pages,
  workflow steps — and again here, in score-run replay)
- a run status the worker sets and the API mistranslates

Every plan ends with a live-stack task: real API, real worker, real Redis,
real Postgres, over HTTP.

### 4.3 Verify the sibling path

G5 exists because `start_run` was verified and `replay` was not, in the same
module, in the same week. When a plan touches one entry point, it enumerates
the others that reach the same machinery and verifies each.

### 4.4 Assert the observable, not the internal

`AWAITING_APPROVAL` was correct in the run store and wrong in the API for the
entire life of the feature, because every test asserted the stored run. Where a
state is user-visible, tests assert the **projection a client receives**, not
the record behind it.

### 4.5 Frontend contract changes are not verified until the bundle builds

`tsc --noEmit`, `eslint` and `vitest` all passed on a change that broke
`npm run build`. Only `tsc -b` checks the referenced project configuration.
Any task that regenerates contracts runs the full build.

## 5. Plans

| Plan | Covers | Gate |
|---|---|---|
| `2026-08-07-approval-and-replay-resume.md` | G1, G5, G4 | A parked run resumes; a replayed run executes; a stalled connector run terminates |
| `2026-08-07-capability-reachability.md` | G10, G3, G7, G9 | Every capability a workflow may reference either runs or says why not |
| `2026-08-07-bounded-reads-and-dead-surfaces.md` | G6, G8, G2 | No unbounded entity read; no surface that accepts input and emits nothing |

Plan 1 is independent. Plan 2 depends on Plan 1 only for the approval path
(`case.note.draft` is approval-gated, so it cannot be verified end to end until
approval resumes work). Plan 3 is independent of both.

## 6. Out of scope

- **An evidence-checklist capability implementation.** Writing a capability body
  is different work from making the engine run one. It stays registered and
  explicitly unimplemented.
- **Keyset pagination for graph reads.** G6 adds a bounded page using the
  existing `SKIP`/`LIMIT` shape. Deep pagination is O(offset) in Neo4j; a cursor
  is a later optimisation, recorded rather than smuggled in.
- **Retiring the adapter calling convention.** G9 widens the executor signature
  so context stops riding in the payload. Collapsing `rag_adapter` and
  `status_adapter` into it is a follow-up, not a prerequisite.
