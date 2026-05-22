# Module: agent

**Verified against codebase:** 2026-05-22
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
    ) -> list[WorkflowRun]: ...
    def cancel_workflow(self, workflow_id: str) -> WorkflowRun: ...
```

---

## Workflow Run State (`agent/models.py`)

Last verified: 2026-05-20

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

Last verified: 2026-05-22

The `coordinator.py` is the worker entry point. It:
1. Loads `DomainConfig` from env.
2. Wires all adapters (graph, vectorstore, embeddings, llm, storage, events, database, analytics, monitoring).
3. Creates `WorkflowRunStoreProtocol` via `create_workflow_run_store_from_env()`.
4. Constructs `LlmClientProtocol` via `llm.factory.create_llm_client(config)` (replaces previously-inlined construction logic).
5. Registers event handlers for each event type, including `"kb.delete"` → `handle_knowledge_base_deleted`.
6. Starts an optional health-check HTTP endpoint.
7. Runs an event loop: `event_bus.consume()` → dispatch handler → `event_bus.ack()` or dead-letter.
8. Handles SIGTERM/SIGINT for graceful shutdown.

### Key handlers (updated 2026-05-22)

**`handle_records_ingested`** — extended to optionally embed-and-index records-derived entities into the vector store. When `embeddings_service` and `vector_store` are both passed (wired in production), stored entities are embedded using `_build_entity_embedding_text` (shared with the documents path), then indexed as `VectorRecord` objects with `source_kind=record` metadata. No `VectorsIndexedEvent` is published from this path (the event is documents-only).

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
) -> int:
```

**`handle_knowledge_base_deleted`** — new handler. Subscribes to `"kb.delete"` events. When `event.cleanup_pending=True`, retries the 5-step cascade: `graph.delete_knowledge_base` → `vector.delete_knowledge_base` → `raw_record_store.delete_by_kb` → object_store prefix-delete → `kb_repository.delete`. All calls are idempotent; exceptions bubble to the DLQ wrapper.

```python
def handle_knowledge_base_deleted(
    event: KnowledgeBaseDeletedEvent,
    *,
    graph_service: GraphServiceProtocol,
    vector_service: VectorServiceProtocol,
    raw_record_store: RawRecordStore,
    kb_repository: KnowledgeBaseRepository,
    object_store: ObjectStore | None = None,
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

Last verified: 2026-05-20

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
    ) -> list[WorkflowRun]: ...
    # Returns newest-first ordered by created_at

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun: ...

    def delete_run(self, workflow_id: str) -> None: ...
    # Idempotent for missing IDs

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> WorkflowRun | None: ...
```

**Drift note:** The TODO in `adapters/protocols.py` notes that durable adapters (`PostgresWorkflowRunStore`, `RedisWorkflowRunStore`) are not yet implemented. Current production backends are `in_memory` and `redis` (for workflow_id-keyed state only).

---

## `WorkflowEventTracker` (`agent/workflow_tracking.py`)

Last verified: 2026-05-22

Tracks workflow run state transitions during coordinator dispatch. Writes to `WorkflowRunStoreProtocol`. Implements the `WorkflowBusyTracker` protocol used by the API layer.

Public methods:
- `begin_event(event: AnyEvent) -> bool` — marks step RUNNING; returns `False` if the run is already terminal (coordinator skips cancelled workflows).
- `complete_event(event: AnyEvent) -> None` — marks step COMPLETED or FAILED; terminal events also move the run to COMPLETED/FAILED.
- `fail_event(event: AnyEvent, error: BaseException) -> None` — marks step + run FAILED after retry exhaustion.
- `is_busy(knowledge_base_id: str) -> bool` — returns `True` when the KB has at least one non-terminal (QUEUED or RUNNING) workflow run. Queries `list_runs` for each non-terminal status; returns as soon as a run is found.

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
