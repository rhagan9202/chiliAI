# Module: agent

**Verified against codebase:** 2026-06-16, except the `handle_records_ingested` gap note and Tests section (both **2026-07-24**, D1 demo closeout)
**Source:** `backend/agent/`

## Purpose

Workflow coordinator and pipeline worker. The composition root of the `chili-worker` container. Consumes Redis Streams events and dispatches to pipeline handlers (ingestion, graph, embeddings, analytics). Tracks workflow run lifecycle. Manages retry/dead-letter logic.

---

## Service Protocol (`agent/protocols.py`)

```python
class AgentServiceProtocol(Protocol):
    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse: ...
    def get_workflow_status(self, workflow_id: str) -> WorkflowRun: ...
    def list_workflows(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowRunPage: ...
    def cancel_workflow(self, workflow_id: str) -> WorkflowRun: ...
```

---

## Workflow Run State (`agent/models.py`)

Last verified: 2026-05-28

```python
MetadataValue = str | int | float | bool

class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=1.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    def delay_for_attempt(self, attempt: int) -> float: ...

class HealthSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8001, gt=0)
    degraded_after_seconds: float = Field(default=300.0, gt=0.0)

class WorkflowStepStatus(str, Enum):
    PENDING = "pending"; RUNNING = "running"
    COMPLETED = "completed"; FAILED = "failed"

class WorkflowRunStatus(str, Enum):
    QUEUED = "queued"; RUNNING = "running"
    COMPLETED = "completed"; FAILED = "failed"; CANCELLED = "cancelled"

TERMINAL_RUN_STATUSES: frozenset[WorkflowRunStatus]  # COMPLETED, FAILED, CANCELLED

class WorkflowStepState(BaseModel):
    step_name: str
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    metadata: dict[str, MetadataValue] = {}

class WorkflowRun(BaseModel):
    workflow_id: str
    knowledge_base_id: str
    trigger_event_type: str
    status: WorkflowRunStatus = WorkflowRunStatus.QUEUED
    steps: list[WorkflowStepState] = []   # non-empty + unique names enforced
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, MetadataValue] = {}
    idempotency_key: str | None = None

class WorkflowRunUpdate(BaseModel):
    """Partial update; None fields leave existing values unchanged."""
    status: WorkflowRunStatus | None = None
    steps: list[WorkflowStepState] | None = None
    updated_at: datetime | None = None
    metadata: dict[str, MetadataValue] | None = None
```

---

## Coordinator (`agent/coordinator.py`)

Last verified: 2026-06-16

The `coordinator.py` is the worker entry point. It:
1. Loads `DomainConfig` from env.
2. Wires all adapters (graph, vectorstore, embeddings, llm, storage, events, database, analytics, monitoring).
3. Creates `WorkflowRunStoreProtocol` via `create_workflow_run_store_from_env()`.
4. Constructs `LlmClientProtocol` via `llm.factory.create_llm_client(config)` (replaces previously-inlined construction logic).
5. Registers event handlers for each event type, including `"kb.delete"` → `handle_knowledge_base_deleted`.
6. Starts an optional health-check HTTP endpoint.
7. Runs an event loop: `event_bus.consume()` → dispatch handler → `event_bus.ack()` or dead-letter.
8. Handles SIGTERM/SIGINT for graceful shutdown.

### Key handlers (updated 2026-06-16)

**`handle_records_ingested`** - optionally embeds and indexes records-derived entities into the vector store. When `embeddings_service` and `vector_store` are both passed, stored entities are embedded using `_build_entity_embedding_text` (shared with the documents path), then indexed as `VectorRecord` objects with `source_kind=record` metadata. No `VectorsIndexedEvent` is published from this path (the event is documents-only). When wired, the handler also runs best-effort policy-rule evaluation over stored entities and throttled graph metrics, then a best-effort peerstats stage that can persist derived risk signals and reassess affected entities.

**Records→analytics fan-out (`analytics.34`, closed 2026-07-24):** at the end of `handle_records_ingested`, when the batch produced risk-assessable entities (the peerstats/timeseries stages' `affected` set, scored by `assess_entities`), the handler runs Flow B **in-process** — a direct call to `handle_graph_updated_for_analytics` with an in-memory `GraphUpdatedEvent` whose single `GraphUpdatedDocumentReference` carries **inline `upserted_entity_ids`** (the `_resolve_upserted_entity_ids` resolver prefers that field over storage keys, so no `GraphUpsertResult`/`ValidationReport` artifacts are staged and no event is published — Flow A never re-runs). Gated by `RecordsConfig.analytics_trigger` (`enabled`, default off; the CMS pack enables it), throttled per KB by a dedicated `MetricsRecomputeThrottle` (`min_interval_seconds`), and capped to the batch's top-N entities by `overall_score` (`max_entities_per_batch`). Best-effort-wrapped exactly like the document dispatch (`_publish_analytics_fanout_failed`, stage `analytics_fanout`) so an analytics failure never makes the retry/DLQ wrapper replay the records ingest. Trade-off recorded in the story: the throttle is leading-edge, so within a window only the first assessable batch fires — entities landing in later batches wait for the next window/ingest. The former demo stand-in `backend/tools/demo_trigger_analytics.py` is deleted.

```python
def handle_records_ingested(
    event: RecordsIngestedEvent,
    *,
    records_config: RecordsConfig,
    raw_record_store: RawRecordStore,
    graph_service: GraphService,
    observation_writer: ObservationWriter,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    policy_rules: list[PolicyRulePack] | None = None,
    policy_service: PolicyService | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    risk_service: RiskService | None = None,
    peer_stats_enabled: bool = False,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
```

**`handle_knowledge_base_deleted`** - subscribes to `"kb.delete"` events. When `event.cleanup_pending=True`, retries the centralized cascade from `knowledgebases.cleanup` (graph, vector, raw records, derived signals, risk history, observations, alert history, metrics, conversations, cases, policy, evidence, and object-store payloads), then deletes KB metadata. All calls are idempotent; exceptions bubble to the DLQ wrapper.

```python
def handle_knowledge_base_deleted(
    event: KnowledgeBaseDeletedEvent,
    *,
    kb_deletion_stores: KbDeletionStores,
    kb_repository: KnowledgeBaseRepository,
) -> None:
```

---

## WorkflowRunStore Adapters

| Backend | File | Config env var |
|---------|------|----------------|
| In-memory | `adapters/in_memory.py` | `CHILI_WORKFLOW_RUN_STORE_BACKEND=in_memory` |
| Redis | `adapters/redis_store.py` | `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis` |

Factory: `adapters/runtime.py::create_workflow_run_store_from_env()`.

The Redis store allows both API and worker containers to observe the same workflow lifecycle state.

### `WorkflowRunStoreProtocol` (`adapters/protocols.py`)

Last verified: 2026-06-16

```python
class WorkflowRunStoreProtocol(Protocol):
    def save_run(self, run: WorkflowRun) -> WorkflowRun: ...
    # Upsert keyed by workflow_id; enforces uniqueness on (knowledge_base_id, idempotency_key)

    def get_run(self, workflow_id: str) -> WorkflowRun: ...

    def list_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowRunPage: ...
    # Returns newest-first ordered by created_at with has_more/next_offset metadata

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun: ...

    def update_run_if_current(
        self,
        workflow_id: str,
        update: WorkflowRunUpdate,
        *,
        expected_statuses: set[WorkflowRunStatus] | frozenset[WorkflowRunStatus],
        updated_before: datetime | None = None,
    ) -> WorkflowRun | None: ...

    def delete_run(self, workflow_id: str) -> None: ...
    # Idempotent for missing IDs

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> WorkflowRun | None: ...

    def find_by_correlation_id(self, correlation_id: str) -> WorkflowRun | None: ...
```

**Drift note:** The TODO in `adapters/protocols.py` is partially stale: `RedisWorkflowRunStore` now exists and implements shared API/worker state, including idempotency, indexed correlation-id lookup, and conditional stale-run reconciliation. A Postgres workflow-run adapter is still not implemented.

---

## `WorkflowEventTracker` (`agent/workflow_tracking.py`)

Last verified: 2026-06-16

Tracks workflow run state transitions during coordinator dispatch. Writes to `WorkflowRunStoreProtocol`. Implements the `WorkflowBusyTracker` protocol used by the API layer.

Public methods:
- `begin_event(event: AnyEvent) -> bool` — marks step RUNNING; returns `False` if the run is already terminal (coordinator skips cancelled workflows).
- `complete_event(event: AnyEvent) -> None` — marks step COMPLETED or FAILED; terminal events also move the run to COMPLETED/FAILED.
- `fail_event(event: AnyEvent, error: BaseException) -> None` — marks step + run FAILED after retry exhaustion.
- `is_busy(knowledge_base_id: str) -> bool` — returns `True` when the KB has at least one non-terminal (QUEUED or RUNNING) workflow run. Queries `list_runs` for each non-terminal status; returns as soon as a run is found.
- `reconcile_stale_runs(max_age_seconds: int, batch_size: int = 1000) -> int` — conditionally marks stale QUEUED/RUNNING runs failed so busy checks and UI workflow lists do not hang after worker interruption.

---

## Retry and Dead-Letter Policy

`RetryPolicy` model in `agent/models.py`. Coordinator wraps each handler in retry logic; exhausted retries → `event_bus.publish_to_dlq()`.

---

## Health Endpoint (`agent/health.py`)

Optional lightweight HTTP server (not FastAPI) for container health checks. Controlled by `HealthSettings` model.

---

## Module Dependencies

- All capability modules: `ingestion`, `graph`, `vectorstore`, `embeddings`, `llm`, `analytics`, `monitoring`, `records`
- `events/` — `EventBus`
- `database/` — `ConnectionProvider`
- `storage/` — `ObjectStore`
- `config/` — `DomainConfig`
- `shared/` — logging, utils

The coordinator is the only module permitted to import from all capability modules simultaneously.

---

## Tests

Location: `backend/tests/agent/`

The records→analytics fan-out (`analytics.34`) is covered by
`backend/tests/agent/test_records_analytics_fanout.py`: a records-only KB
produces GNN clusters and alerts with the trigger enabled, nothing when
disabled, top-N capping, throttle suppression, and failure isolation
(ingest completes and an `analysis.failed` visibility event with stage
`analytics_fanout` is published when Flow B raises). The former
`backend/tools/` demo-trigger package and its `tests/tools/` suite are
deleted; the repo-root `tools/` package remains a separate pyright
invocation (`tools/pyrightconfig.json`, its own CI step).
