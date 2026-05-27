# Production Readiness Remediation Design

Date: 2026-05-27

## Goal

Remediate the confirmed live-data bugs and adjacent production-readiness gaps
without rewriting chiliAI's architecture. The remediation establishes a narrow
production-readiness spine: KB-scoped live projections, correct workflow
terminal states, durable mutation boundaries, clearer frontend state, and
verification gates that exercise the full stack with ingested and stored data.

## Scope

This design covers:

- Analytics detail and dashboard projection correctness.
- Workflow lifecycle correctness, including zero-vector and stale workflows.
- Records and ingestion mutation guardrails.
- A first Redis Streams recovery slice.
- Frontend routing, role, mobile layout, and live-state UX cleanup.
- Backend, frontend, E2E, and generated-contract verification gates.

This design does not include full multitenancy, workflow audit-history storage,
DLQ management UI, storage streaming, or a complete observability platform.
Those remain backlog items and should build on the boundaries tightened here.

## Architectural Principles

The implementation must follow the existing project architecture:

- Backend OpenAPI is the HTTP contract source of truth.
- Feature modules own domain logic behind protocol boundaries.
- The FastAPI gateway adapts service/domain models into public API DTOs.
- The agent coordinator owns cross-module workflow orchestration.
- Frontend API types come from generated OpenAPI schema aliases.
- Runtime domain behavior remains driven by `/config/domain` and
  `/config/features`, not hard-coded frontend entity unions.

## Recommended Approach

Use a production-readiness spine delivered in dependency order. Each phase must
produce a working, testable improvement and avoid broad rewrites.

Rejected alternatives:

- Patch-only stabilization would fix immediate UI errors but leave the workflow,
  event, and mutation gaps that caused misleading state.
- A full platform-hardening epic would include tenant isolation, audit-grade
  workflow history, DLQ replay UI, async workflow APIs, and storage streaming.
  That is too broad for one implementation cycle.

## API Contract And Live Projections

Analytics detail endpoints must become KB-scoped public contracts. The backend
should add explicit request/query handling for `kb_id` on entity risk and
timeseries detail routes. Invalid or missing KB scope returns `422`. A missing
entity in the selected KB returns `404`. An existing entity without analytics
data returns a typed unavailable payload instead of raising an unhandled
exception.

Dashboard overview must stop mixing seeded `ApiState` data with live routes.
The overview projection should derive from the same live sources used by the
rest of the API:

- alert counts from the alert projection repository
- case counts from the live case source currently exposed by the API
- entity counts from KB-scoped graph metrics or KB summary projection
- high-risk counts from the live risk projection when available

The initial implementation may return unavailable/zero values for projections
that do not yet have live data, but it must not silently fall back to seeded
Medicare demo entities for live KB views.

`ApiState` can remain for explicitly local/demo-only surfaces during transition,
but frontend-consumed production routes must not depend on hard-coded `kb-1`
state.

## Workflow Lifecycle

Workflow lifecycle truth remains in the agent module behind
`WorkflowRunStoreProtocol`. The tracker should recognize `kb.ready` as a
tracked workflow event and terminal success state. This makes the normal
vector-index path and the zero-entity/zero-vector path converge on the same
completed workflow projection.

The tracker should also support stale-run reconciliation. A run is stale when
it is queued or running, its last update is older than a configured threshold,
and there is no evidence of pending work that can still complete it. The first
implementation should avoid a new status enum unless it is low-risk. If adding
`stale` is too invasive, mark the run `failed` with metadata:

```json
{
  "reason": "stale_workflow_reconciled"
}
```

Workflow timeline projections should expose enough metadata for the frontend to
distinguish queued, running, completed with vectors, completed with zero
entities/vectors, failed, and stale/reconciled states.

## Mutation And Event Durability

Ingestion currently writes object-store content before publishing
`documents.uploaded`. If publish fails after storage succeeds, the system needs
a recovery record rather than a stranded object. Add a narrow retry/outbox
marker that includes KB ID, source document ID, storage key, content hash,
correlation ID, event type, and failure reason. The recovery worker or admin
command can replay or clean up those markers.

Records API push must enforce the same safety checks as file upload:

- KB exists or the route returns `404`.
- KB is not pending cleanup.
- KB has no active queued/running workflow.
- Invalid feed and row validation behavior remains unchanged.

Duplicate structured-record submissions should not re-emit expensive downstream
work when the store accepts no new records or detects unchanged content. The
handler may remain idempotent, but the service should avoid unnecessary Flow 1
fan-out when there is nothing new to process.

Redis Streams should receive a first production-hardening slice:

- configurable `MAXLEN`/trim policy on publish
- stale pending detection and reclaim through `XPENDING` plus `XAUTOCLAIM` or
  `XCLAIM`
- DLQ publication after retry exhaustion
- structured retry/DLQ metadata with event type, correlation ID, KB ID, retry
  count, and error summary

This slice is intentionally smaller than a full DLQ replay product.

## Frontend UX And State

Investigation Workbench must include selected KB scope in analytics calls and
query keys. Analytics requests should be disabled until both KB ID and entity ID
exist. Missing analytics data should render a normal unavailable state without
console 500s, while the graph and entity detail remain usable.

Knowledge Base navigation should use `/knowledge-bases` as the canonical route.
Any stale `/knowledgebases` links must be removed or redirected. The KB workflow
timeline should distinguish empty extraction success from stuck work.

Dashboard copy and metrics should reflect live projections. Alert counts must
agree with `/alerts`; seeded/demo user-facing language should be removed.

RAG Chat copy should describe the actual configured retrieval/provider state.
When no context is retrieved, the UI should show a clear no-context state. When
the external LLM provider is unavailable, the UI should disclose fallback or
provider-unavailable status rather than implying successful live retrieval.

Role-gated redirects should keep config-driven access control but surface a
small notice when the selected role cannot access the requested page.

Mobile layout must remove horizontal overflow in the app shell and
Investigation Workbench. The sidebar, AI panel, graph canvas, toolbar controls,
and cards need responsive constraints that fit a 390px viewport without body
horizontal scrolling.

SSE reconnect behavior should invalidate baseline KB, workflow, alerts, and
dashboard queries after a meaningful disconnect. Normal KB/workflow events
should keep scoped invalidation where possible.

## Error Handling

The API should turn expected missing-data cases into typed responses:

- `422` for invalid/missing required scope
- `404` for missing selected resources
- `409` for KB busy or pending cleanup mutation attempts
- `200` with an unavailable payload for existing resources whose optional
  analytics/RAG projection is not ready
- `500` only for unexpected infrastructure or programming errors

Frontend pages should render page-local operational states instead of relying
on global error boundaries for recoverable conditions.

## Testing

Backend tests must cover:

- analytics detail routes require `kb_id`
- analytics detail routes do not read hard-coded `kb-1`
- existing entity without analytics data returns unavailable state
- missing selected entity returns `404`
- dashboard overview agrees with alert projection counts
- `kb.ready` marks workflow runs completed
- zero-vector workflow completes
- stale workflow reconciliation marks reason metadata
- records push rejects missing, busy, and pending-cleanup KBs
- duplicate unchanged records avoid duplicate downstream event emission
- Redis stream trim configuration is applied
- stale pending messages can be reclaimed
- retry exhaustion publishes DLQ entries with useful metadata

Frontend tests must cover:

- investigation analytics URLs and query keys include KB ID
- analytics unavailable state renders without throwing
- stale `/knowledgebases` links are removed or redirected
- role redirect notice appears
- mobile investigation view has no horizontal overflow at 390px
- dashboard and RAG user-facing copy no longer mention seeded/demo behavior

Generated-contract checks must export backend OpenAPI, regenerate frontend
schema, and fail CI when committed schema output drifts.

Full-stack E2E smoke must exercise live data:

- create a KB
- upload a real document
- wait for workflow completion
- verify stored document metadata
- verify graph entities and relationships when extractable
- verify vector collection when vectors exist
- verify a zero-entity document completes cleanly
- open Investigation Workbench and confirm no analytics 500s
- verify dashboard and alerts agree

## Rollout Plan

1. Analytics contract and frontend KB-scoped query fix.
2. Workflow `kb.ready` completion and stale-run reconciliation.
3. Records and ingestion mutation guardrails.
4. Redis Streams recovery slice.
5. Dashboard, RAG, route, role, and mobile UX cleanup.
6. E2E smoke and CI gates.

Each phase should merge independently and reduce user-visible breakage on its
own.

## Acceptance Criteria

- Live ingested entities no longer cause analytics detail 500s.
- A zero-entity/zero-vector workflow reaches a terminal completed state.
- Dashboard alert counts agree with `/alerts`.
- Records API push cannot mutate a missing, busy, or cleanup-pending KB.
- Ingestion publish failures after storage create a retry/outbox marker.
- Redis stream growth is bounded and stale pending messages can be reclaimed.
- Frontend has no internal stale `/knowledgebases` links.
- Investigation Workbench has no horizontal body overflow at 390px width.
- Analyst-facing copy no longer describes live surfaces as seeded/demo.
- Full-stack smoke verifies live ingestion, persistence, graph/vector state,
  zero-entity completion, and no Investigation analytics 500s.
