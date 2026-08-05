# SAFE-CMS-014 Workflow Definitions Design

> Scope: backend-first slice for `SAFE-CMS-014`
> Source plan: `docs/superpowers/plans/2026-07-30-cms-fraud-ai-safe-agile-20-sprint-surge.md`
> Runway ADR: `docs/superpowers/specs/2026-08-04-safe-cms-pi4-playbooks-workflows-adr.md`
> Branch context: `safe-cms-013-playbooks`

## 1. Goal

Add a KB-scoped backend surface for user-authored workflow definitions that analysts can draft, admins can approve or retire, and analysts can run once approved. The first slice persists and validates workflow definitions, records audit events, and creates preview workflow runs through the existing `WorkflowRun` store without invoking arbitrary tools.

## 2. Non-Goals

- Do not build a low-code canvas or frontend workflow authoring UI in this slice.
- Do not execute arbitrary user-authored tool calls.
- Do not introduce Flowise as a runtime dependency.
- Do not replace the existing `/workflows` run status API or `agent.definitions` static pipeline registry.
- Do not implement the full typed capability registry planned for `SAFE-CMS-015`; use a small built-in capability catalog as a temporary enforcement boundary.

## 3. Current System Fit

The repo already has:

- `backend/agent/models.py` for workflow run state.
- `backend/agent/adapters/*` for in-memory and Redis-backed run stores.
- `backend/api/routers/workflows.py` for list, detail, and cancellation of workflow runs.
- `backend/agent/definitions.py` for the static ingestion and analytics pipeline step registry.
- `backend/auditlog/*` for append-only audit events.
- `backend/api/routers/playbooks.py` for the KB-scoped routing and authorization pattern used by `SAFE-CMS-013`.

`SAFE-CMS-014` should add user-authored workflow definition boundaries beside these pieces. It should reuse the existing run store for preview runs, but it should not overload the static agent registry with user-authored data.

## 4. Authorization

Use existing roles:

- `viewer`: list and read workflow definitions.
- `analyst`: create draft definitions, update draft definitions, and run approved definitions.
- `admin`: approve and retire definitions.

All routes must require KB access through `User.knowledge_base_ids` with the same rule used by playbooks: unauthorized KBs return 404, and admins may access all KBs. When auth is disabled, existing RBAC middleware bypass behavior applies.

## 5. API Surface

Add routes under `backend/api/routers/workflow_definitions.py`:

- `GET /knowledgebases/{knowledge_base_id}/workflow-definitions`
- `POST /knowledgebases/{knowledge_base_id}/workflow-definitions`
- `GET /knowledgebases/{knowledge_base_id}/workflow-definitions/{definition_id}/versions/{version}`
- `PUT /knowledgebases/{knowledge_base_id}/workflow-definitions/{definition_id}/versions/{version}`
- `POST /knowledgebases/{knowledge_base_id}/workflow-definitions/{definition_id}/versions/{version}/approve`
- `POST /knowledgebases/{knowledge_base_id}/workflow-definitions/{definition_id}/versions/{version}/retire`
- `POST /knowledgebases/{knowledge_base_id}/workflow-definitions/{definition_id}/versions/{version}/run`

Create/update return a draft definition response. Approve and retire return the updated definition response. Run returns the existing frontend-compatible `WorkflowRunResponse` shape so the current `/workflows` UI can display the preview run.

## 6. Data Model

Create a new backend package, `backend/workflow_definitions/`, with models separate from `backend/agent/definitions.py`.

Core models:

- `WorkflowDefinition`: `definition_id`, `knowledge_base_id`, `domain_name`, `name`, `description`, `version`, `status`, `allowed_capability_refs`, `steps`, `created_by`, `approved_by`, `created_at`, `updated_at`, `approved_at`, `retired_at`.
- `WorkflowStepDefinition`: `step_id`, `label`, `capability_ref`, `input_refs`, `output_refs`, `condition`, `retry_policy`, `requires_human_approval`, `on_failure`.
- `WorkflowDefinitionCreate`: authoring payload for draft creation.
- `WorkflowDefinitionUpdate`: draft-only update payload.
- `WorkflowDefinitionRunRequest`: `target_type`, `target_id`, `inputs`, and optional `idempotency_key`.
- `WorkflowDefinitionValidationResult`: normalized validation errors and warnings for service tests and API 422 details.

Definition status values:

- `draft`
- `approved`
- `retired`

Run target values for this slice:

- `alert`
- `entity`
- `case`
- `knowledge_base`

## 7. Persistence

Add a repository protocol and in-memory implementation first, matching existing store patterns. Add Postgres persistence and migration in the implementation plan because definitions are durable product state.

Database table: `workflow_definition_snapshots`

Columns:

- `snapshot_id`
- `knowledge_base_id`
- `domain_name`
- `definition_id`
- `version`
- `status`
- `name`
- `description`
- `allowed_capability_refs` JSONB
- `steps` JSONB
- `created_by`
- `approved_by`
- `created_at`
- `updated_at`
- `approved_at`
- `retired_at`

Unique key: `(knowledge_base_id, definition_id, version)`.

Definitions are versioned snapshots. Approved versions are immutable except for status transition to `retired`. Draft versions may be updated by analysts until approval.

## 8. Capability Boundary

Until `SAFE-CMS-015` introduces the full typed capability registry, the backend should enforce a small built-in catalog:

- `playbook.step`
- `rag.query`
- `analytics.peer_context`
- `evidence.checklist.generate`
- `case.note.draft`
- `human.approval`

Validation rules:

- `definition_id`, `version`, `name`, and every `step_id` are non-empty.
- Step IDs are unique within a definition.
- Every step `capability_ref` must exist in the built-in catalog.
- Every step `capability_ref` must appear in `allowed_capability_refs`.
- `allowed_capability_refs` must not include unknown capability refs.
- `retry_policy.max_attempts` must be at least 1 when present.
- `on_failure` must be one of `fail_workflow`, `continue`, or `require_approval`.
- Definitions with `case.note.draft` or `human.approval` steps must preserve `requires_human_approval=true` on those steps.

Unknown capability refs must fail validation before any definition is persisted.

## 9. Preview Run Handoff

Running an approved definition creates a `WorkflowRun` with:

- `knowledge_base_id` from the route.
- `trigger_event_type="workflow_definition.requested"`.
- one `WorkflowStepState` per definition step, in definition order.
- metadata containing `definition_id`, `definition_version`, `definition_status`, `target_type`, `target_id`, and `approved_by`.
- `idempotency_key` from the request when supplied.

The run starts queued. This slice does not dispatch tool calls. Existing `/workflows` list/detail/cancel behavior remains the read and cancellation surface for the resulting run records.

Draft and retired definitions cannot be run. Requests for missing or unauthorized definitions return 404 where authorization would otherwise disclose a KB or definition boundary. Requests to run a draft or retired version return 409.

## 10. Audit Events

Record audit events through `AuditLogService` for material transitions:

- `workflow_definition.created`
- `workflow_definition.updated`
- `workflow_definition.approved`
- `workflow_definition.retired`
- `workflow_definition.run_requested`

Use:

- `resource_type="workflow_definition"` for definition changes.
- `resource_id="{definition_id}:{version}"`.
- `knowledge_base_id` from the route.
- `actor_user_id`, `actor_email`, and `actor_roles` from the authenticated user.
- `metadata` for `domain_name`, `definition_id`, `version`, `run_id` when available, `target_type`, and `target_id`.

Audit write failures must not fail the primary workflow definition operation, following current audit service semantics.

## 11. Contracts

Add request and response models to `backend/api/contracts.py`, then regenerate OpenAPI and frontend schema in the implementation phase.

Response models should expose validation-safe data only:

- definition identity and status fields
- allowed capability refs
- step metadata
- author and approver IDs
- timestamps

Do not echo secret values in `inputs`; run request inputs should be stored only in workflow metadata if they are JSON scalar values, and tests should cover redaction boundaries before any broader input persistence is added.

## 12. Testing

Use TDD. Initial RED tests should cover:

- service rejects unknown capability refs before persistence.
- service rejects steps whose capability is not listed in `allowed_capability_refs`.
- analyst can create and update a draft.
- admin can approve a draft.
- analyst can run an approved definition and receives a `WorkflowRunResponse`.
- analyst cannot run draft or retired definitions.
- viewer cannot create, update, approve, retire, or run.
- out-of-scope KB access returns 404.
- audit events are recorded for create, update, approve, retire, and run request.
- migration replay creates the durable table without drift.

Focused verification for this slice:

- backend tests for workflow definition models, service, repository, router, and migration.
- `uv run --project backend ruff check backend`
- `uv run --project backend pyright`
- OpenAPI export after contract changes.
- frontend schema/codegen check if generated contracts change.

## 13. Acceptance Criteria

The slice is complete when:

- workflow definitions are durable, versioned, KB-scoped, and RBAC protected.
- invalid capability refs cannot be persisted.
- analysts can create drafts and run approved versions only.
- admins can approve and retire definitions.
- preview runs appear through the existing workflow run API.
- every material transition has an audit event.
- OpenAPI and generated frontend schema match the backend contracts.
