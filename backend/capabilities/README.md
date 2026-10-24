# capabilities

Typed **capability (tool) registry** for workflow and agent callers. A
capability is described by a static `CapabilityManifest` (input/output JSON
schemas, side-effect class, required roles, audit requirement, domain and
environment compatibility). `CapabilityRegistryService` lists manifests,
authorizes a call (fail-closed), dispatches it to a bound executor, and audits
it. Manifests and executors are kept apart, so a capability can be registered
and browsed before anything can run it.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `CapabilityManifest` (frozen), `CapabilityPermission`, `CapabilityDomainCompatibility`, `CapabilityHealth`, `CapabilityExample`, `CapabilityQuery`, `CapabilityPage`, `CapabilityExecutionEnvelope`; literals `CapabilitySideEffectClass` (`read` / `write` / `external_call` / `approval`) and `CapabilityHealthStatus`. |
| `registry.py` | `CapabilityRegistry` (in-process manifest map) and `create_default_capability_registry()` with the built-in manifests: `analytics.peer_context`, `connector.sync.status`, `evidence.checklist.generate`, `rag.query`, `case.note.draft`. Environment tags are validated against `shared.environments.SUPPORTED_ENVIRONMENT_TAGS`. |
| `service.py` | `CapabilityRegistryService` — `list_capabilities`, `get_required`, `authorize`, `execute`, `execution_success` / `execution_failure`; `create_default_capability_registry_service()`. |
| `executors.py` | Module-level capability-id → callable map: `register_executor`, `get_executor`, `registered_capability_ids`, `clear_executors` (tests); `ExecutionContext` (frozen caller identity/authorization passed separately from the payload). |
| `builtin_executors.py` | `register_builtin_capability_executors(...)` binds closures over live services; `WORKER_EXECUTABLE_CAPABILITY_IDS`; `PEER_CONTEXT_CAPABILITY_ID`. |

## Contracts and invariants

- **Authorization fails closed.** `authorize` returns an unsuccessful envelope
  with one of `capability_not_registered`, `domain_not_supplied`,
  `capability_domain_denied`, `environment_not_supplied`,
  `capability_environment_denied`, `no_roles_permitted`,
  `capability_role_denied`. `domain_name` / `environment_tag` are required
  keyword arguments; `None` denies.
- **Order is authorize → dispatch → audit.** `execute` audits refused calls
  too. A registered capability with no bound executor returns
  `capability_not_executable`; an executor exception becomes
  `capability_execution_failed` rather than propagating. When
  `permission.requires_audit` is set, the call is written to the audit ledger
  as action `capability.execute` (resource type `capability`) under
  `PLATFORM_TENANT_ID`.
- **Executors are per-process state.** The worker binds them at startup
  (`agent/coordinator.py` calls `register_builtin_capability_executors` with
  `rag_service=None`), so in the worker `connector.sync.status` and
  `analytics.peer_context` are executable; `rag.query`,
  `evidence.checklist.generate`, and `case.note.draft` report
  `capability_not_executable`. The API binds nothing; its browse route reports
  executability from the declared `WORKER_EXECUTABLE_CAPABILITY_IDS`, which
  `tests/capabilities/test_builtin_executors.py` checks against what binding
  actually produces.
- **Cross-module imports.** This module imports other modules' services
  directly rather than through the gateway, coordinator, or `shared/`:
  `service.py` imports `auditlog.service.AuditLogService` and
  `auditlog.models`; `builtin_executors.py` imports
  `analytics.peerstats.peer_analysis.PeerAnalysisService`,
  `connectors.service.ConnectorService`, `connectors.status_adapter`,
  `rag.protocols.RagServiceProtocol`, and (inside the function, to avoid an
  import cycle) `workflow_definitions.rag_adapter.RAG_QUERY_CAPABILITY_ID`.

## How it is reached

- **API:** `api/routers/capabilities.py` —
  `GET /knowledgebases/{knowledge_base_id}/capabilities` (viewer; filters
  `role`, `module`, `side_effect_class`, `limit`, `offset`), scoped to the KB's
  domain. The service comes from `get_capability_registry_service`
  (`api/dependencies.py`).
- **Worker:** `workflow_definitions/executor.py` invokes
  `CapabilityRegistryService.execute` for workflow capability steps, using the
  registry and audit service from its execution deps.

## Persistence

None. Manifests are code-defined and held in memory; there is no table or
migration.

## Current gaps

- The `executors.py` module docstring says `capabilities/__init__.py` imports
  the built-in executors; it does not — binding happens only via the explicit
  `register_builtin_capability_executors` call in the worker.

## Tests

`tests/capabilities/` — `test_registry.py`, `test_execute.py`,
`test_builtin_executors.py`, `test_coherence.py`.

See also: [connectors](../connectors/README.md),
[workflow_definitions](../workflow_definitions/README.md),
[auditlog](../auditlog/README.md),
[architecture](../../docs/architecture.md).
