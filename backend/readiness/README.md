# readiness

**Knowledge-base / domain readiness aggregation** (SAFE-CMS-018). Answers
"is this KB ready to investigate under the active domain pack?" by reading the
existing state of four subsystems — the knowledge base itself, its connectors,
its workflow definitions and the capability registry — and folding them into
one response of per-component status plus a flat list of blockers and
warnings. The module is read-only: it owns no tables and writes nothing.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `ReadinessComponentStatus` (`ready \| blocked \| warning \| unknown`), `ReadinessIssue` (`component`, `code`, `message`, optional `action`), `ReadinessComponent`, `ReadinessKnowledgeBaseSummary`, `ReadinessResponse`. |
| `service.py` | `ReadinessService.get_readiness(knowledge_base_id)` and one private builder per component. |

## Components and issue codes

`get_readiness` raises `KeyError` for an unknown KB, otherwise builds these
components (keys of `ReadinessResponse.components`):

| Component | Blockers | Warnings | `details` |
|-----------|----------|----------|-----------|
| `knowledge_base` | `kb_not_ready` (KB `status != "ready"`) | `domain_mismatch` (KB `domain` set and not the active domain) | `status`, `document_count`, `entity_count`, `relationship_count`, `domain` |
| `connectors` | `no_connectors`; `connector_sync_failed` (latest run of a connector is `failed`) | `connector_never_synced` | `configured_count`, `completed_runs`, `failed_connectors`, `never_synced` |
| `workflows` | `no_workflows` (no definitions for the KB) | — | `definition_count`, `approved_count` |
| `capabilities` | `no_capabilities` (registry returns zero for the active domain) | — | `available_count`, `capability_ids` |

A component is `blocked` if it has any blocker, `warning` if it has only
warnings, else `ready` (`unknown` is declared in the type but not produced by
the service). `ReadinessResponse.ready` is true exactly when the aggregated
blocker list is empty. Connector and workflow lookups are capped at 500 items
per KB; only the most recent sync run of each connector is inspected.

## Contracts and dependencies

`ReadinessService` is constructed with a `KnowledgeBaseRepository`, a
`ConnectorService`, a `WorkflowDefinitionService`, a
`CapabilityRegistryService` and the active domain name. `service.py` imports
those service classes directly from `connectors.service`,
`workflow_definitions.service` and `capabilities.service` (plus model types
from `connectors.models` and `capabilities.models`), and `models.py` imports
`JsonValue` from `capabilities.models`. These are direct cross-module imports
rather than the `shared/` / API-DI / event paths described in
[`docs/architecture.md`](../../docs/architecture.md); the API wires the
concrete instances in via `get_readiness_service` (`api/dependencies.py`).

## How it is reached

`GET /knowledgebases/{knowledge_base_id}/readiness` (`api/routers/readiness.py`,
viewer role). The router returns 404 when the caller cannot access the KB, when
the KB does not exist, or when the service raises `KeyError`. There are no
worker handlers or events.

## Persistence

None — readiness is computed on every request from the repositories behind the
injected services.

## Tests

`tests/readiness/test_readiness_service.py`, `tests/api/test_readiness_router.py`.

See also: [`../connectors/`](../connectors/),
[`../workflow_definitions/README.md`](../workflow_definitions/README.md),
[`../capabilities/`](../capabilities/),
[`../knowledgebases/README.md`](../knowledgebases/README.md).
