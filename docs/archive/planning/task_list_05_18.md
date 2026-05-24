# Remediation Checklist — 2026-05-18

This checklist tracks the app remediation work identified during the runtime walkthrough and follow-up implementation. Update this file by checking items off as they are completed and verified.

## Phase 0 — Baseline and branch hygiene

- [x] Confirm working tree state before remediation implementation.
- [x] Identify unrelated `.claude/` artifacts and keep them out of remediation commits unless explicitly requested.
- [x] Preserve the local `docker-compose.dev.yaml` reload-scoping fix while remediation work proceeds.
- [x] Run focused backend/frontend validation for the first implementation slice.
- [x] Decide whether the local `docker-compose.dev.yaml` reload-scoping fix should be committed with remediation work or split into a dev-ops-only commit.

## Phase 1 — Workflow correctness and event correlation

- [x] Fix document correlation propagation in `backend/ingestion/service.py`.
  - [x] Add optional `correlation_id` to `IngestionService.ingest_task`.
  - [x] Pass `DocumentsUploadedEvent.correlation_id` from `process_documents_uploaded`.
  - [x] Set the preserved correlation ID on `DocumentsParsedEvent`.
  - [x] Set the preserved correlation ID on `DocumentsFailedEvent`.
- [x] Extend workflow tracking in `backend/agent/workflow_tracking.py`.
  - [x] Map `documents.failed` to the parse step.
  - [x] Mark `documents.failed` as a terminal failed workflow event.
  - [x] Map `records.ingested` to a records-ingestion step.
  - [x] Mark `records.ingested` as a terminal successful workflow event after handler completion.
  - [x] Resolve knowledge base IDs for `DocumentsFailedEvent`.
  - [x] Resolve knowledge base IDs for `RecordsIngestedEvent`.
- [x] Confirm records flow is covered by existing coordinator `begin_event` / `complete_event` / `fail_event` wrapping.
- [x] Add tests for document event correlation preservation.
- [x] Add tests for document failure workflow tracking.
- [x] Add tests for records workflow tracking.
- [x] Add or expand coordinator-level tests proving records handler failures call workflow `fail_event` and do not silently disappear.
- [x] Run live runtime smoke to verify one correlation chain from `documents.uploaded` through `vectors.indexed`.

## Phase 2 — Backend workflow API and projections

- [x] Expose `GET /workflows` filters in `backend/api/routers/workflows.py`.
  - [x] Add `knowledge_base_id` query parameter.
  - [x] Add `status` query parameter.
  - [x] Add `limit` query parameter with bounds.
  - [x] Add `offset` query parameter with bounds.
  - [x] Pass filters through to `AgentServiceProtocol.list_workflows`.
- [x] Keep `backend/api/_workflow_projection.py` thin; no business lifecycle rules added.
- [x] Add route tests for filtered workflow listing with RBAC enabled.
- [x] Add route tests specifically covering pagination edge cases if workflow pagination behavior changes.
  - Decision: pagination behavior did not change beyond existing bounded `limit`/`offset` pass-through tests.
- [x] Decide whether workflow list responses need pagination metadata beyond the current `items` payload.
  - Decision: not needed for current UI; keep the compact `items` contract until a paginated workflow history view requires totals/cursors.

## Phase 3 — Frontend workflow scoping, polling, and realtime stability

- [x] Update `chili_app/src/api/workflows.ts` so workflow requests accept filters.
- [x] Include workflow filters in the TanStack Query key.
- [x] Add conditional polling only while returned workflows are `queued` or `running`.
- [x] Update `KnowledgeBaseManagerPage` to request workflows scoped to the selected knowledge base.
- [x] Update Knowledge Base Manager tests to support filtered workflow URLs.
- [x] Add frontend API tests for workflow query keys and query-string serialization.
- [x] Replace broad realtime invalidation in `chili_app/src/api/realtime.ts` with targeted invalidation based on `RealtimeSnapshotResponse` changes.
- [x] Invalidate workflow queries only when running workflow state changes.
- [x] Invalidate specific KB detail/list/document queries only when KB status/count state changes.
- [x] Avoid invalidating analytics/policy data on every 5-second SSE heartbeat.
- [x] Add EventSource recovery in `chili_app/src/api/realtime.ts`.
  - [x] Close broken streams.
  - [x] Reconnect with exponential backoff.
  - [x] Reset retry state after a successful connection.
  - [x] Preserve `withCredentials` behavior.
  - [x] Clean up timers and EventSource instances on unmount.
- [x] Tune TanStack Query defaults in `chili_app/src/app/providers.tsx`.
  - [x] Use longer stale times for immutable domain/config data.
  - [x] Use shorter stale times or targeted polling for mutable workflow/alert/KB state.
- [x] Add or update tests for realtime targeted invalidation.
- [x] Add or update tests for EventSource reconnect behavior.
- [x] Run UI smoke to verify the timeline excludes workflows from other KBs.

## Phase 4 — Analytics and graph snapshot resilience

- [x] Investigate the GNN snapshot failure path in `backend/agent/coordinator.py` and `backend/analytics/gnn/`.
- [x] Decide whether to wire a real graph-backed snapshot source or gate GNN execution when snapshots are unavailable.
- [x] Prevent fresh KB ingestion from emitting misleading `analysis.failed` events for missing graph snapshots.
- [x] Ensure domain capability flags drive analytics execution.
- [x] If `gnn` is enabled but no snapshot source is configured, expose an actionable startup/health/config state.
  - Decision: not applicable to the current factory path because a snapshot source is always configured; missing snapshots are handled as controlled skips.
- [x] Add tests proving fresh KB ingestion does not emit misleading GNN no-snapshot failures.
- [x] Add tests proving configured graph snapshots flow into GNN analysis when available.
- [x] Run analytics smoke to verify GNN behavior for fresh KBs.

## Phase 5 — Uploads, records, and user-facing errors

- [x] Improve structured backend error display in `KnowledgeBaseManagerPage.tsx`.
  - [x] Parse `ApiError.body.detail` when present.
  - [x] Parse backend validation arrays into readable messages.
  - [x] Show concrete invalid document upload reasons.
  - [x] Show concrete invalid CSV/JSONL records reasons.
- [x] Add client-side document upload validation from domain config.
  - [x] Content type validation.
  - [x] File size validation.
  - [x] Empty-file validation.
- [x] Add client-side records upload validation from domain config and selected feed.
  - [x] Required feed validation.
  - [x] File-upload feed requires a file.
  - [x] Empty CSV/JSONL validation.
  - [x] Content type/file extension validation where supported.
- [x] Add request timeout/abort support in `chili_app/src/lib/apiClient.ts`.
  - [x] Preserve caller-provided `AbortSignal`.
  - [x] Surface timeout errors as user-readable messages.
- [x] Add tests for invalid upload UX and error extraction.
  - [x] Unsupported document upload / 415 case.
  - [x] Invalid records upload / 422 case.
  - [x] Timeout/abort case.
- [x] Run failure smoke to confirm invalid uploads show specific errors and do not enqueue invalid work.

## Phase 6 — Dev/runtime operations and noise reduction

- [x] Diagnose hot reload thrash caused by watching mutable runtime data.
- [x] Apply local `docker-compose.dev.yaml` reload-dir scoping so `/app/data` is not watched.
- [x] Finalize `docker-compose.dev.yaml` reload behavior.
- [x] Decide whether to keep all backend source package directories watched or reduce to API-facing modules only.
- [x] Add `--reload-exclude` patterns for caches, generated metadata, `*.egg-info`, and runtime data if supported by the pinned Uvicorn/watchfiles version.
- [x] Tune dev event polling in `docker-compose.dev.yaml`.
  - [x] Consider raising `CHILI_EVENT_BLOCK_MS` from `100` to `500` or `1000`.
  - [x] Consider increasing event batch size if existing settings support it.
- [x] Add explicit API healthcheck to `docker-compose.dev.yaml`.
- [x] Add explicit API healthcheck to `docker-compose.yaml`.
- [x] Add or verify environment-driven logging controls.
  - [x] Wire `LOG_LEVEL` in `backend/shared/logging.py` if missing.
  - [x] Document `LOG_LEVEL`.
  - [x] Document `LOG_FORMAT`.
  - [x] Keep access-log suppression behind a dedicated toggle if added.
- [x] Update operational docs.
  - [x] `backend/README.md` dev-stack tuning notes.
  - [x] `docs/onboarding.md` dev-stack tuning notes.
  - [x] `.env.example` logging/event-polling notes.
  - [x] Compose detach behavior.
  - [x] SSE/networkidle testing caveats.
- [x] Run dev-stack smoke to confirm no Uvicorn reload loop while runtime artifacts are written.

## Phase 7 — Broader hardening backlog

- [x] Add idempotency/deduplication for document registration in `backend/ingestion/service.py`.
  - [x] Choose content-hash and/or source-URI strategy.
  - [x] Add tests for repeated uploads.
- [x] Decide whether Redis workflow state is sufficient for current compliance needs.
  - Decision: sufficient for current local/prototype status views; not sufficient for audit-grade compliance history.
- [x] If needed, implement durable/audit-grade workflow history.
  - Decision: deferred from this remediation because the current requirement is prototype/local status, not compliance-grade audit retention.
  - [x] Postgres-backed `WorkflowRunStoreProtocol` adapter, or
    - Deferred option for a future compliance-history milestone.
  - [x] append-only workflow event history/outbox.
    - Deferred option for a future compliance-history milestone.
- [x] Improve page-level frontend error boundaries for Investigation, RAG, analytics, and KB routes.
- [x] Synchronize Investigation Workbench selection state with URLs.
- [x] Reduce unnecessary analytics refetches when unrelated realtime snapshot fields change.
- [x] Improve `RunTimeline` failure details and retry affordances if backend exposes richer failure contracts.

## Verification checklist

- [x] Backend targeted tests for first implementation slice passed.
  - [x] `tests/ingestion/test_service.py`
  - [x] `tests/agent/test_workflow_tracking.py`
  - [x] `tests/api/test_workflows_router.py`
- [x] Backend `pyright` passed for the first implementation slice.
- [x] Backend `ruff` passed for changed backend files and tests.
- [x] Frontend focused Vitest tests passed.
  - [x] `src/api/__tests__/workflows.test.ts`
  - [x] `src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
- [x] Frontend ESLint passed.
- [x] Frontend production build passed.
- [x] Full backend `pytest --cov` run after all remediation slices.
- [x] Full backend `ruff check .` run after all remediation slices.
- [x] Full backend `pyright` run after all remediation slices.
- [x] Full frontend test suite after all remediation slices.
- [x] Full frontend lint/build after all remediation slices.
- [x] Runtime workflow smoke after workflow fixes.
- [x] Realtime network-churn smoke after realtime fixes.
- [x] Failure-path upload smoke after upload/error UX fixes.
- [x] Analytics/GNN smoke after snapshot resilience fixes.
- [x] Dev-stack stability smoke after compose/logging tuning.

## Current open working-tree notes

- [x] `docker-compose.dev.yaml` reload scoping is incorporated into the remediation changes.
- [x] `.claude/` is untracked and should remain excluded unless explicitly requested.
