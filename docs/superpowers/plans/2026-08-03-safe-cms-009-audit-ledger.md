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

- [x] Record audit events for alert acknowledgement, case create/promote/update/feedback/attach, KB delete, auth login/logout/callback outcomes, and evidence mutations where current endpoints exist.
- [x] Preserve primary response behavior when audit recording fails; expose failure counters/buffer status.

**Notes:**
- Audit status slice complete: added admin-gated `GET /audit/status` with `failed_write_count` and bounded recent write-failure descriptors from `AuditLogService.write_failures`.
- RED: `uv run --project backend pytest backend/tests/api/test_audit_router.py::test_audit_status_exposes_write_failure_buffer` failed with 404.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_audit_router.py::test_audit_status_exposes_write_failure_buffer`: 1 passed.
  - `uv run --project backend pytest backend/tests/api/test_audit_router.py backend/tests/api/test_dependencies.py::test_get_audit_log_service_returns_in_memory_when_provider_is_none backend/tests/api/test_policy_registry.py`: 11 passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/audit.py backend/tests/api/test_audit_router.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/routers/audit.py backend/tests/api/test_audit_router.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed and updated the tracked OpenAPI contract for `/audit/status`.
- Partial auth-outcome slice complete: login start, callback success/failure, and logout now emit sanitized `auth.*` audit events under tenant `platform`; events capture actor when known and omit OIDC code/state, tokens, and raw session ids.
- Auth audit failures remain non-blocking through `AuditLogService.record()` failure capture.
- RED: `uv run --project backend pytest backend/tests/api/test_auth_router.py::test_login_records_audit_event backend/tests/api/test_auth_router.py::test_auth_login_still_redirects_when_audit_sink_fails backend/tests/api/test_auth_router.py::test_callback_exchanges_code_and_creates_session_cookie backend/tests/api/test_auth_router.py::test_callback_rejects_unknown_state backend/tests/api/test_auth_router.py::test_logout_clears_cookie_and_session` failed with empty audit event pages and zero failed-write count.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_auth_router.py::test_login_records_audit_event backend/tests/api/test_auth_router.py::test_auth_login_still_redirects_when_audit_sink_fails backend/tests/api/test_auth_router.py::test_callback_exchanges_code_and_creates_session_cookie backend/tests/api/test_auth_router.py::test_callback_rejects_unknown_state backend/tests/api/test_auth_router.py::test_logout_clears_cookie_and_session`: 5 passed.
  - `uv run --project backend pytest backend/tests/api/test_auth_router.py backend/tests/api/test_audit_router.py backend/tests/api/test_dependencies.py::test_get_audit_log_service_returns_in_memory_when_provider_is_none backend/tests/api/test_policy_registry.py`: 32 passed.
  - `uv run --project backend ruff check backend/api/dependencies.py backend/api/routers/auth.py backend/tests/api/test_auth_router.py`: passed.
  - `uv run --project backend pyright backend/api/dependencies.py backend/api/routers/auth.py backend/tests/api/test_auth_router.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed with no tracked OpenAPI diff.
- Partial KB-mutation slice complete: knowledge base create and delete routes now emit summarized `knowledge_base.*` audit events with actor, tenant/KB scope, before/after summaries, and cleanup status metadata. A 207 partial cleanup records a failure outcome with `failure_reason="cleanup_pending"` while omitting raw cascade error text from metadata.
- Evidence router currently exposes read-only GET endpoints only, so no evidence mutation hooks were added in this slice.
- RED: `uv run --project backend pytest backend/tests/api/test_knowledgebases_router.py::test_create_knowledge_base_records_audit_event backend/tests/api/test_knowledgebases_router.py::test_delete_knowledge_base_records_audit_event backend/tests/api/test_knowledgebases_router.py::test_knowledge_base_mutation_still_succeeds_when_audit_sink_fails` failed with empty audit event pages and zero failed-write count.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_knowledgebases_router.py::test_create_knowledge_base_records_audit_event backend/tests/api/test_knowledgebases_router.py::test_delete_knowledge_base_records_audit_event backend/tests/api/test_knowledgebases_router.py::test_knowledge_base_mutation_still_succeeds_when_audit_sink_fails`: 3 passed.
  - `uv run --project backend pytest backend/tests/api/test_kb_delete_cascade.py::test_delete_kb_returns_207_on_partial_failure`: 1 passed.
  - `uv run --project backend pytest backend/tests/api/test_knowledgebases_router.py backend/tests/api/test_kb_delete_cascade.py backend/tests/api/test_policy_registry.py backend/tests/api/test_audit_router.py`: 62 passed.
  - `uv run --project backend ruff check backend/api/dependencies.py backend/api/routers/knowledgebases.py backend/tests/api/test_knowledgebases_router.py backend/tests/api/test_kb_delete_cascade.py`: passed.
  - `uv run --project backend pyright backend/api/dependencies.py backend/api/routers/knowledgebases.py backend/tests/api/test_knowledgebases_router.py backend/tests/api/test_kb_delete_cascade.py`: 0 errors.
- Partial case-mutation slice complete: create, update, feedback, promote, and attach-alert routes now emit summarized `case.*` audit events with actor, KB scope, before/after summaries, and no raw analyst notes.
- Audit failures remain non-blocking for case mutations through `AuditLogService.record()` failure capture.
- RED: `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_create_update_and_feedback_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_promote_and_attach_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_mutation_still_succeeds_when_audit_sink_fails` failed with empty audit event pages and zero failed-write count.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_create_update_and_feedback_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_promote_and_attach_record_audit_events backend/tests/api/test_phase5_stateful_routes.py::test_case_mutation_still_succeeds_when_audit_sink_fails`: 3 passed.
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py backend/tests/api/test_policy_registry.py backend/tests/api/test_audit_router.py`: 24 passed.
  - `uv run --project backend ruff check backend/api/routers/cases.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: passed.
  - `uv run --project backend pyright backend/api/routers/cases.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed with no tracked OpenAPI diff.
- Partial alert-mutation slice complete: acknowledge, assignment, single status update, and bulk status update routes now emit summarized `alert.*` audit events for successful mutations only; skipped/invalid bulk rows do not emit ledger events.
- Alert audit summaries avoid raw alert reasoning and raw operator reason text; metadata stores entity id, severity, and reason-present/bulk flags.
- RED: `uv run --project backend pytest backend/tests/api/test_read_model_routers.py::test_acknowledge_alert_records_audit_ledger_event backend/tests/api/test_read_model_routers.py::test_assign_and_status_update_record_audit_ledger_events backend/tests/api/test_read_model_routers.py::test_bulk_alert_status_records_audit_only_for_updated_alerts backend/tests/api/test_read_model_routers.py::test_alert_mutation_still_succeeds_when_audit_sink_fails` failed with empty audit pages and zero failed-write count.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_read_model_routers.py::test_acknowledge_alert_records_audit_ledger_event backend/tests/api/test_read_model_routers.py::test_assign_and_status_update_record_audit_ledger_events backend/tests/api/test_read_model_routers.py::test_bulk_alert_status_records_audit_only_for_updated_alerts backend/tests/api/test_read_model_routers.py::test_alert_mutation_still_succeeds_when_audit_sink_fails`: 4 passed.
  - `uv run --project backend pytest backend/tests/api/test_read_model_routers.py backend/tests/api/test_policy_registry.py backend/tests/api/test_audit_router.py`: 44 passed after starting dev Postgres for the route integration test.
  - `uv run --project backend ruff check backend/api/routers/alerts.py backend/api/dependencies.py backend/tests/api/test_read_model_routers.py`: passed.
  - `uv run --project backend pyright backend/api/routers/alerts.py backend/api/dependencies.py backend/tests/api/test_read_model_routers.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed with no tracked OpenAPI diff.

## Task 5: Dossier/Cockpit Audit Timeline And Export

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Create/modify: `chili_app/src/api/audit.ts`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: investigation cockpit page/components as needed.
- Create/modify Vitest and Playwright coverage.

- [x] Add compact audit timeline panels in the case dossier and cockpit.
- [x] Include audit slices in exports without leaking secrets.
- [x] Verify browser flow and frontend build.

**Notes:**
- Dossier/export slice complete: case dossier payloads now include the latest case-scoped audit events, Markdown/JSON exports include audit provenance, and audit serialization exposes action/actor/outcome metadata without raw analyst notes.
- Case Management and Investigation Workbench now render compact audit trail panels from the dossier projection; the cockpit panel is gated by validated explicit case context.
- RED:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json`: failed with missing `audit_events` and missing Markdown `## Audit Trail`.
  - `npx vitest run src/pages/__tests__/CaseManagementPage.test.tsx -t "renders a case dossier with evidence, chronology, decisions, and export actions"`: failed because the dossier UI did not render `Audit trail`.
  - `npx vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx -t "renders a compact redacted audit trail for the explicit cockpit case"`: failed because the workbench never called `useCaseDossier`.
- Browser verification initially exposed stale e2e drift: `e2e/investigation-workbench.spec.ts` still asserted retired `entity_type_code`/`Primary Taxonomy` labels even though the active `medicare_fraud.yaml` provider shape is `NPI`, `Provider Name`, `Specialty`, and `State`; the spec now asserts the current live config labels.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json backend/tests/api/test_audit_router.py`: 6 passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/tests/api/test_phase5_stateful_routes.py`: 0 errors.
  - `npx vitest run src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 53 passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `pnpm exec playwright test e2e/case-dossier.spec.ts e2e/investigation-workbench.spec.ts`: 9 passed against the real dev stack; e2e teardown deleted its seeded KB, then the temporary compose stack and volumes were stopped/removed.

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
