# SAFE-CMS-009 Audit Ledger Implementation Plan

## Context

SAFE-CMS-009 adds an immutable audit ledger for material analyst, system, and agent actions. The canonical backlog owner is `docs/backlog/_security.md` story `_security.06`; `docs/backlog/_observability.md` explicitly drops its duplicate audit-log story in favor of `_security.06`.

## Guardrails

- Keep audit writes append-only. No update/delete API in the service contract.
- Do not block primary product flows on audit sink failures; capture failures for later retry/inspection.
- Redact or summarize before/after payloads. Do not persist credentials, tokens, cookies, or raw secrets.
- Keep the first slice backend-only and domain-neutral. CMS labels belong in callers, not the auditlog core.
- Prefer typed Pydantic models, repository protocols, and adapters that match existing module structure.

## Task 1: Auditlog Domain Contract And In-Memory Store

**Files:**
- Create: `backend/auditlog/__init__.py`
- Create: `backend/auditlog/models.py`
- Create: `backend/auditlog/protocols.py`
- Create: `backend/auditlog/adapters/__init__.py`
- Create: `backend/auditlog/adapters/in_memory.py`
- Create: `backend/auditlog/service.py`
- Create: `backend/tests/auditlog/__init__.py`
- Create: `backend/tests/auditlog/test_service.py`

- [x] Add `AuditEvent`, `AuditEventCreate`, `AuditEventQuery`, and `AuditEventPage` models.
- [x] Add append-only `AuditLogRepository` protocol and an in-memory adapter for tests/dev.
- [x] Add `AuditLogService` with record/list methods, filter semantics, pagination, and failure isolation.
- [x] Verify with focused auditlog tests and pyright/ruff for the new module.

**Notes:**
- RED: `uv run --project backend pytest backend/tests/auditlog/test_service.py -q` failed during collection because `auditlog` did not exist.
- Added typed audit event create/stored/query/page/failure models, append-only repository protocol, defensive-copy in-memory adapter, and `AuditLogService.record/list_events`.
- Audit write failures are captured in a bounded in-memory buffer and return `None` without raising into the primary caller.
- GREEN:
  - `uv run --project backend pytest backend/tests/auditlog/test_service.py -q`: 6 passed.
  - `uv run --project backend pyright auditlog tests/auditlog`: 0 errors.
  - `uv run --project backend ruff check --no-cache auditlog tests/auditlog`: passed.

## Task 2: Query API And Dependency Wiring

**Files:**
- Modify: `backend/api/dependencies.py`
- Create: `backend/api/routers/audit.py`
- Modify: `backend/api/app.py`
- Modify: `backend/api/contracts.py`
- Create/modify: `backend/tests/api/test_audit_router.py`

- [x] Register `GET /audit/events` with admin-only access and filters for KB/tenant, actor, action prefix, resource, time range, and pagination.
- [x] Return typed response contracts and prove wrong-scope events are not returned.
- [x] Export OpenAPI and regenerate frontend contracts.

**Notes:**
- RED: `uv run --project backend pytest backend/tests/api/test_audit_router.py -q` failed with `404` because `/audit/events` did not exist.
- Added `AuditEventResponse`/`AuditEventListResponse`, per-app `get_audit_log_service`, `get_audit_event_list_payload`, and `backend/api/routers/audit.py` registered from `create_app()`.
- RED: tightened filter coverage showed `from`/`to` query params were ignored until the dependency accepted them as aliases for the domain query time range.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_audit_router.py backend/tests/auditlog/test_service.py -q`: 9 passed.
  - `uv run --project backend pyright api/routers/audit.py api/dependencies.py api/contracts.py auditlog tests/api/test_audit_router.py tests/auditlog`: 0 errors.
  - `uv run --project backend ruff check --no-cache api/routers/audit.py api/dependencies.py api/contracts.py auditlog tests/api/test_audit_router.py tests/auditlog`: passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `git diff --check`: passed.

## Task 3: Durable Postgres Adapter

**Files:**
- Create: `backend/auditlog/adapters/postgres.py`
- Create: `backend/database/migrations/versions/<next>_audit_log.py`
- Modify: `backend/database/migrations/snapshots/head.sql`
- Create: `backend/tests/auditlog/test_postgres_store.py`

- [x] Add `audit_log` table and indexes on `(tenant_id, occurred_at DESC)`, `(knowledge_base_id, occurred_at DESC)`, and `(actor_user_id, occurred_at DESC)`.
- [x] Store `before`, `after`, and `metadata` as JSON payload summaries.
- [x] Verify persistence and query ordering through the Postgres adapter tests.

**Notes:**
- RED: `uv run --project backend pytest backend/tests/auditlog/test_postgres_store.py` failed during collection with `ModuleNotFoundError: No module named 'auditlog.adapters.postgres'`.
- Added append-only `PostgresAuditLogRepository`, `AuditLogPersistenceError`, migration `0016_audit_log`, regenerated `backend/database/migrations/snapshots/head.sql`, and switched `get_audit_log_service` to choose Postgres when a connection provider is configured.
- Added `audit_log_service` to the config-derived app-state purge list so domain/database-backend swaps cannot retain a stale audit repository.
- GREEN:
  - `uv run --project backend pytest backend/tests/auditlog/test_postgres_store.py`: 3 passed after starting the dev Postgres service.
  - `scripts/ci_migration_check.sh --update-snapshot`: passed and rewrote `head.sql`.
  - `scripts/ci_migration_check.sh`: passed; migration replay clean and schema matched `head.sql`.
  - `uv run --project backend pytest backend/tests/auditlog/test_postgres_store.py backend/tests/api/test_audit_router.py backend/tests/api/test_dependencies.py::test_get_audit_log_service_uses_postgres_when_provider_non_null backend/tests/api/test_dependencies.py::test_get_audit_log_service_returns_in_memory_when_provider_is_none backend/tests/api/test_dependency_swap.py::test_reset_with_app_purges_config_derived_state_and_rebuilds_api_state backend/tests/api/test_dependency_swap.py::test_reset_clears_every_registered_singleton`: 10 passed.
  - `uv run --project backend ruff check backend/auditlog backend/api/dependencies.py backend/tests/auditlog/test_postgres_store.py backend/tests/api/test_dependencies.py backend/tests/api/test_dependency_swap.py backend/database/migrations/versions/0016_audit_log.py`: passed.
  - `uv run --project backend pyright backend/auditlog backend/api/dependencies.py backend/tests/auditlog/test_postgres_store.py backend/tests/api/test_dependencies.py backend/tests/api/test_dependency_swap.py`: 0 errors.

## Task 4: Mutation Source Hooks

**Files:**
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/routers/auth.py`
- Modify: `backend/api/routers/knowledgebases.py`
- Modify: `backend/api/routers/alerts.py`
- Modify: `backend/api/routers/cases.py`
- Modify: `backend/api/routers/evidence.py`
- Create/modify focused API tests.

- [ ] Record audit events for alert acknowledgement, case create/promote/update/feedback/attach, KB delete, auth login/logout/callback outcomes, and evidence mutations where current endpoints exist.
- [ ] Preserve primary response behavior when audit recording fails; expose failure counters/buffer status.

**Notes:**
- Partial case-mutation slice complete: create, update, feedback, promote, and attach-alert routes now emit summarized `case.*` audit events with actor, KB scope, before/after summaries, and no raw analyst notes.
- Audit failures remain non-blocking for case mutations through `AuditLogService.record()` failure capture.
- RED: `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_create_update_and_feedback_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_promote_and_attach_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_mutation_still_succeeds_when_audit_sink_fails` failed with empty audit event pages and zero failed-write count.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_create_update_and_feedback_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_promote_and_attach_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_mutation_still_succeeds_when_audit_sink_fails`: 3 passed.
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py backend/tests/api/test_policy_registry.py backend/tests/api/test_audit_router.py`: 24 passed.
  - `uv run --project backend ruff check backend/api/routers/cases.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: passed.
  - `uv run --project backend pyright backend/api/routers/cases.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed with no tracked OpenAPI diff.

## Task 5: Dossier/Cockpit Audit Timeline And Export

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Create/modify: `chili_app/src/api/audit.ts`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: investigation cockpit page/components as needed.
- Create/modify Vitest and Playwright coverage.

- [ ] Add compact audit timeline panels in the case dossier and cockpit.
- [ ] Include audit slices in exports without leaking secrets.
- [ ] Verify browser flow and frontend build.

## Review Gates

- Review after Task 1 before API/migration work.
- Review after Task 3 before wiring broad mutation hooks.
- Review after Task 5 before backlog status changes.

## Definition Of Done

- Material actions emit audit events through a typed service API.
- Audit event writing is failure-visible and does not corrupt primary transactions.
- Ledger queries are KB/tenant scoped and permission checked.
- Exports include audit provenance without leaking credentials/secrets.
- Focused auditlog/API tests, migration tests, frontend tests, browser flow, pyright/ruff/lint/build, backlog consistency, and whitespace checks pass.
