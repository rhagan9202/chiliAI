# workflow_definitions

User-authored, versioned **workflow definitions** and their executor. A
definition is an ordered list of steps, each naming a registered capability
(`capabilities/`), with optional conditions, retry policy, failure mode and a
human-approval gate. Definitions move `draft → approved → retired`; only an
approved definition can be run. A run is an `agent.models.WorkflowRun` driven
one step at a time by `workflow.step.queued` events.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `WorkflowDefinition` (computed `snapshot_id = "{kb}:{definition_id}:{version}"`), `WorkflowStepDefinition`, `WorkflowDefinitionCreate` / `WorkflowDefinitionUpdate` / `WorkflowDefinitionRunRequest`, `WorkflowDefinitionPage`, `WorkflowDefinitionValidationResult`, `WorkflowFailureMode` (`fail_workflow \| continue \| require_approval`), `WorkflowRetryPolicy`, `BUILT_IN_WORKFLOW_CAPABILITIES`, `HUMAN_APPROVAL_CAPABILITIES`, `validate_workflow_definition_payload`. |
| `conditions.py` | Restricted step-condition grammar: `parse_condition`, `evaluate_condition`, `ParsedCondition`, `ConditionSyntaxError`. |
| `repository.py` | `WorkflowDefinitionRepository` protocol — `save_definition / update_definition / get_definition / list_definitions`. |
| `adapters/in_memory.py` | `InMemoryWorkflowDefinitionRepository`. |
| `adapters/postgres.py` | `PostgresWorkflowDefinitionRepository` over `database.ConnectionProvider`. |
| `service.py` | `WorkflowDefinitionService` — list/get, `create_draft`, `update_draft`, `approve_definition`, `retire_definition`, `run_definition`; error types `WorkflowDefinitionError`, `…NotFoundError`, `…ConflictError`, `…ValidationError`. |
| `executor.py` | `handle_workflow_step_queued`, registered with `execution.registry.register_handler("workflow.step.queued", …)`. |
| `rag_adapter.py` | `execute_rag_query_capability` / `RAG_QUERY_CAPABILITY_ID` (`"rag.query"`): authorizes then runs a RAG query for workflow callers; used by `capabilities/builtin_executors.py`. |

## Contracts and invariants

- **Validation** (`validate_workflow_definition_payload`): every step's
  `capability_ref` must be a registered capability *and* listed in the
  definition's `allowed_capability_refs`; step ids are unique; a step using a
  capability in `HUMAN_APPROVAL_CAPABILITIES` (`case.note.draft`) must set
  `requires_human_approval`; a `condition` must parse and may only reference a
  step that runs *before* it. `BUILT_IN_WORKFLOW_CAPABILITIES` is derived from
  `create_default_capability_registry()` rather than written out.
- **Condition grammar** is one comparison, `<step_id>.<key> <op> <literal>`,
  with `op` in `== != > >= < <=`; there is no `eval` path.
- **Lifecycle**: only drafts can be updated or approved; only approved
  definitions can be retired (retiring a retired one is a no-op) or run. Every
  transition and run request writes an audit event
  (`workflow_definition.created|updated|approved|retired|run_requested`) via
  `AuditLogService`.
- **Runs**: `run_definition` honours `idempotency_key` (same key + same
  definition/target returns the existing run; a different one is a conflict),
  persists the requesting actor's id and roles on the run, then publishes a
  `WorkflowStepQueuedEvent` for the first step if an event bus is configured.
- **Executor**: a step already in a terminal status returns without dispatch
  (at-least-once redelivery guard); terminal or `AWAITING_APPROVAL` runs are
  not advanced; an approval-gated step parks the run until
  `run.metadata["approved.{step_id}"]` is set; capabilities are executed as
  the run's recorded actor (a run with no actor fails); failed steps retry up
  to `retry_policy.max_attempts`, then apply `on_failure`.
- **Cross-module imports**: `service.py` imports `agent.adapters.protocols`,
  `agent.models`, `auditlog.service`/`auditlog.models` and
  `capabilities.service`; `models.py` imports `capabilities.registry`;
  `executor.py` imports `agent.models`; `rag_adapter.py` imports
  `capabilities.service` and `rag.protocols` / `rag.service_models`. These are
  direct module-to-module imports outside the three paths in
  [`docs/architecture.md`](../../docs/architecture.md). Conversely
  `readiness/service.py` and `governance/service.py` import from this package.

## How it is reached

- **API** — `api/routers/workflow_definitions.py`, prefix
  `/knowledgebases/{knowledge_base_id}/workflow-definitions`: `GET ""`
  (viewer), `POST ""` (analyst), `GET|PUT /{definition_id}/versions/{version}`
  (viewer / analyst), `POST …/approve` and `…/retire` (admin), `POST …/run`
  (analyst).
- **Step approval** — `POST /workflows/{workflow_id}/steps/{step_id}/approve`
  (`api/routers/workflows.py` → `agent.service`) records the approval and
  republishes the step.
- **Worker** — the coordinator dispatches `workflow.step.queued` through
  `execution/`; repositories are wired in `agent/coordinator.py` and
  `api/dependencies.py` (in-memory without a connection provider, else
  Postgres).

## Persistence

Table `workflow_definition_snapshots` (migration
`database/migrations/versions/0021_workflow_definition_snapshots.py`):
`snapshot_id` primary key, `UNIQUE (knowledge_base_id, definition_id, version)`,
a status CHECK, and `ix_workflow_definition_snapshots_kb_status`. Runs live in
the agent workflow-run store (see [`../agent/README.md`](../agent/README.md)).

## Tests

`tests/workflow_definitions/` (`test_models.py`, `test_conditions.py`,
`test_service.py`, `test_executor.py`, `test_rag_adapter.py`,
`test_in_memory.py`, `test_postgres.py`), `tests/api/test_workflow_definitions_router.py`,
`tests/database/test_workflow_definitions_migration.py`.

See also: [`docs/ledger/event-catalog.md`](../../docs/ledger/event-catalog.md).
