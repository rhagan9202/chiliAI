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

- [ ] Register `GET /audit/events` with admin-only access and filters for KB/tenant, actor, action prefix, resource, time range, and pagination.
- [ ] Return typed response contracts and prove wrong-scope events are not returned.
- [ ] Export OpenAPI and regenerate frontend contracts.

## Task 3: Durable Postgres Adapter

**Files:**
- Create: `backend/auditlog/adapters/postgres.py`
- Create: `backend/database/migrations/versions/<next>_audit_log.py`
- Modify: `backend/database/migrations/snapshots/head.sql`
- Create: `backend/tests/auditlog/test_postgres_store.py`

- [ ] Add `audit_log` table and indexes on `(tenant_id, occurred_at DESC)`, `(knowledge_base_id, occurred_at DESC)`, and `(actor_user_id, occurred_at DESC)`.
- [ ] Store `before`, `after`, and `metadata` as JSON payload summaries.
- [ ] Verify persistence and query ordering through the Postgres adapter tests.

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
