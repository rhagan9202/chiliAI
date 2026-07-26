# Sprint 2026-30 — KB Lifecycle Controls & Operations (KBM-007..014) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver safe lifecycle controls for Knowledge Base data: explicit delete modes, deep cleanup, batch rollback, rebuild orchestration, and production-grade telemetry/runbooks for KB operations.

**Architecture:** Keep deletion/rebuild contracts typed and explicit at API boundary; route all long-running actions through existing workflow orchestration; reflect backend state transitions in frontend timeline/rebuild controls.

**Tech Stack:** FastAPI/Pydantic, workflow coordinator + Redis Streams, React 19 + TypeScript, TanStack Query, pytest, Vitest/Playwright.

**Open issue source (pushed 2026-07-26):**
- [#37 KBM-007](https://github.com/rhagan9202/chiliAI/issues/37) — Delete modes API contract
- [#38 KBM-008](https://github.com/rhagan9202/chiliAI/issues/38) — Deep cleanup for document delete
- [#39 KBM-009](https://github.com/rhagan9202/chiliAI/issues/39) — Records rollback/delete by ingest batch
- [#40 KBM-010](https://github.com/rhagan9202/chiliAI/issues/40) — Destructive action confirmation UX
- [#41 KBM-011](https://github.com/rhagan9202/chiliAI/issues/41) — Rebuild KB state API + orchestration
- [#42 KBM-012](https://github.com/rhagan9202/chiliAI/issues/42) — Frontend rebuild controls + timeline integration
- [#43 KBM-013](https://github.com/rhagan9202/chiliAI/issues/43) — UX + operational telemetry
- [#44 KBM-014](https://github.com/rhagan9202/chiliAI/issues/44) — Docs/runbooks updates

---

## File Structure (expected)

- Modify: backend KB/ingestion delete + rollback service paths and API routers
- Modify: workflow orchestration surfaces for rebuild requests/state
- Modify: [chili_app/src/pages/KnowledgeBaseManagerPage.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/KnowledgeBaseManagerPage.tsx) and timeline/review components for destructive-confirm + rebuild UX
- Modify: analytics/monitoring hooks and structured logging for operation telemetry
- Modify docs: operator runbooks + KB management docs under [docs/](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/docs)

## Task 1 — KBM-007: Delete modes contract (`source_only` vs `source_and_derived`)

- [ ] Add typed request/response models for delete mode selection with clear invariants.
- [ ] Enforce mode validation at API boundary with explicit error responses for unsupported combinations.
- [ ] Add contract tests and regenerate OpenAPI + frontend contracts when models change.
- [ ] Verify default behavior is backward-safe and explicit (no silent mode assumptions).

## Task 2 — KBM-008 + KBM-009: Deep cleanup + ingest-batch rollback

- [ ] Implement source + derived artifact cleanup path for `source_and_derived`.
- [ ] Implement ingest-batch scoped rollback/delete semantics for records using receipt/correlation identifiers.
- [ ] Ensure graph/vector/storage/database cleanup consistency and idempotent retries.
- [ ] Add integration tests covering partial-failure behavior and recovery.

## Task 3 — KBM-010: Destructive action confirmation UX

- [ ] Add explicit destructive confirmation UX with blast-radius copy tied to selected delete mode.
- [ ] Require user acknowledgement before execution; disable action while request in-flight.
- [ ] Surface backend outcome details (success/failure scope) in timeline/toast state.
- [ ] Add frontend tests for confirmation gating and copy correctness.

## Task 4 — KBM-011 + KBM-012: Rebuild state API + frontend timeline integration

- [ ] Add rebuild state API/workflow trigger with durable status tracking.
- [ ] Expose rebuild controls in KB Manager with proper capability/availability gating.
- [ ] Integrate rebuild lifecycle into run timeline (queued/running/completed/failed with timestamps).
- [ ] Add backend orchestration tests + frontend interaction tests.

## Task 5 — KBM-013 + KBM-014: Telemetry instrumentation + runbooks/docs

- [ ] Instrument UX telemetry for delete/rebuild user actions and outcome visibility.
- [ ] Instrument operational telemetry (workflow latency, failure rate, cleanup scope counters).
- [ ] Update operator runbooks and troubleshooting docs with delete mode/rebuild playbooks.
- [ ] Add documentation acceptance checklist and link all new observability signals.

## Success Criteria

- [ ] Issues [#37](https://github.com/rhagan9202/chiliAI/issues/37) through [#44](https://github.com/rhagan9202/chiliAI/issues/44) are implemented and linked by commits/PR.
- [ ] Delete actions are mode-explicit, confirmed by user, and verifiably safe.
- [ ] Rebuild actions are fully orchestrated and visible in timeline UX.
- [ ] Telemetry + runbooks are sufficient for operator diagnosis without reading source.
- [ ] Frontend and backend gates pass for touched areas.

## Out of Scope for Sprint 30

- New domain-pack semantics or cross-domain schema expansion
- Non-KB Manager UI redesign work outside lifecycle controls
- Analytics model changes not required for delete/rebuild lifecycle integrity
