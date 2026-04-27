# Knowledge Graph Workflow Validation — 2026-04-27

## Scope

Validated whether the current local development UI workflow actually creates a knowledge graph, persists it across the API/worker boundary, and makes it queryable through the Investigation route.

## Construction path in code

The intended graph construction path is event-driven:

1. UI creates a knowledge base through `POST /knowledgebases`.
2. UI uploads a document through `POST /knowledgebases/{kb_id}/documents`.
3. `backend/api/routers/knowledgebases.py` calls `IngestionService.register_documents(...)`.
4. `IngestionService.register_documents(...)` stores raw bytes and publishes `documents.uploaded`.
5. `agent.coordinator` consumes events and runs:
   - `documents.uploaded` → parse document
   - `documents.parsed` → chunk document
   - `documents.chunked` → extract candidate entities/relationships
   - `entities.extracted` → validate against domain config
   - `entities.validated` → `GraphService.upsert_task(...)`
   - `graph.updated` → embeddings, analytics, vectors
   - `vectors.indexed` → `kb.ready`
6. Investigation API queries `GraphService` through:
   - `GET /investigation/search?kb_id=...&q=...`
   - `GET /investigation/entities/{entity_id}?kb_id=...`
   - `GET /investigation/entities/{entity_id}/neighborhood?kb_id=...&depth=...`
7. Investigation UI reads `kb_id` and `entity_id` from URL params and calls those endpoints through `useEntity` and `useNeighborhood`.

## Live UI validation result

Result: **failed** for the real dev UI workflow.

### Steps executed

1. Opened `http://localhost:5173/knowledgebases` in the browser.
2. Created knowledge base `Graph UI Smoke 2026-04-27` through the UI.
3. Uploaded `tmp_graph_workflow_claim.json` through the UI drop-zone handler with Medicare-domain properties:
   - `npi`
   - `hic_number`
   - `claim_id`
   - `amount`
   - `service_date`
   - `facility_id`
   - `name`
   - `type`
4. Verified the KB detail page showed the document row with status `pending`.
5. Reloaded the KB detail page and confirmed the backend persisted the document metadata count: `1 document(s)`.
6. Queried the live Investigation API:
   - `GET /investigation/search?kb_id=<kb_id>&q=Austin&limit=20`
   - `GET /investigation/search?kb_id=<kb_id>&q=CLAIM-GRAPH-001&limit=20`
7. Opened `http://localhost:5173/investigation?kb_id=<kb_id>&entity_id=CLAIM-GRAPH-001`.

### Evidence observed

`GET /knowledgebases/<kb_id>` after upload:

```json
{
  "entity_count": 0,
  "relationship_count": 0,
  "document_count": 1,
  "status": "active"
}
```

`GET /investigation/search?kb_id=<kb_id>&q=Austin&limit=20`:

```json
{
  "items": [],
  "total": 0
}
```

`GET /investigation/search?kb_id=<kb_id>&q=CLAIM-GRAPH-001&limit=20`:

```json
{
  "items": [],
  "total": 0
}
```

Investigation UI with `kb_id` and `entity_id=CLAIM-GRAPH-001` showed:

- `Failed to load neighborhood: Entity 'CLAIM-GRAPH-001' not found in knowledge base ...`
- Entity Detail panel showed the same 404 message.
- Graph canvas showed `No graph data — select an entity to load its neighborhood.`

## Root cause

The graph pipeline works only in the in-process E2E harness, not in the running Docker dev stack.

### 1. Dev containers do not enable Redis event bus

`docker-compose.dev.yaml` sets `REDIS_URL=redis://redis:6379`, but it does **not** set `CHILI_EVENT_BUS_BACKEND=redis` for either `api` or `worker`.

`events.runtime.load_event_bus_settings()` defaults to:

```python
backend=os.environ.get("CHILI_EVENT_BUS_BACKEND", "in-memory")
```

So the API publishes `documents.uploaded` into its own process-local `InMemoryEventBus`, not Redis. The worker uses its own separate process-local bus and never receives the upload event.

Direct Redis check after UI upload found no `chili.*` streams.

### 2. Storage is process-local by default

Even if Redis were enabled, the default domain config leaves `storage` commented out. `DomainConfig` fills this with default `ObjectStoreConfig(backend="local")`, but API dependency wiring currently maps `backend == "local"` to `InMemoryObjectStore`.

That means uploaded document bytes live only inside the API process. A worker in a separate process/container cannot retrieve the raw document content by storage key unless storage is backed by a shared adapter such as local filesystem volume, MinIO/S3, or another shared store.

### 3. Graph repository is process-local by default

Both API and worker default to `InMemoryGraphRepository` unless config explicitly selects a production/shared graph backend. In the live stack, the API and worker have separate graph repository instances.

Even if the worker upserted entities into its in-memory graph, the Investigation API would still query the API process's empty in-memory graph repository.

### 4. Investigation UI has no entity discovery path

The route can query a known `entity_id`, but the UI currently has no KB selector plus entity search to discover IDs after ingestion. It depends on URL params:

- `kb_id`
- `entity_id`

Because extracted entity IDs are generated UUIDs, users cannot infer them from source properties like `CLAIM-GRAPH-001`.

## Control validation

The focused in-process pipeline test passed:

```text
backend/tests/e2e/test_full_pipeline.py::test_happy_path_single_document_reaches_kb_ready
1 passed in 0.12s
```

This confirms the intended event-chain logic can construct graph data when the FastAPI test client and worker coordinator share the same in-memory event bus, object store, and graph repository.

## Verdict

The current live UI workflow **does not actually create and persist a queryable knowledge graph** in the Docker dev stack.

What works:

- UI KB creation.
- UI document upload.
- Backend document metadata registration.
- In-process pipeline unit/E2E behavior with manually shared dependencies.
- Investigation API contracts when graph data exists in the same repository instance.

What does not work live:

- API upload events are not delivered to the worker.
- Worker cannot read API-uploaded document bytes with current default storage.
- Worker-created graph data would not be visible to API investigation queries with current default graph repository.
- Investigation UI cannot discover generated entity IDs.

## Recommended fix sequence

1. Add a dev runtime config that explicitly selects shared backends:
   - `events.backend: redis`
   - shared object storage, either local filesystem volume or MinIO/S3
   - shared graph backend, preferably Neo4j for the existing dev Compose topology
2. Set matching environment variables in `docker-compose.dev.yaml`:
   - `CHILI_EVENT_BUS_BACKEND=redis`
   - keep `REDIS_URL=redis://redis:6379`
3. Wire API dependency factories to the same shared adapters that the worker already supports, especially:
   - local filesystem or S3/MinIO object store
   - Neo4j graph repository
4. Ensure Docker installs required optional adapter dependencies for dev images, for example Neo4j if using the Neo4j graph adapter.
5. Add a live-stack integration/smoke test that performs:
   - create KB through API or UI
   - upload document
   - wait for `kb.ready` or observable graph count
   - search `/investigation/search`
   - query `/investigation/entities/{id}/neighborhood`
6. Add Investigation UI entity discovery:
   - KB selector
   - entity search using `GET /investigation/search`
   - select result → update URL params → load neighborhood
7. Invalidate the KB detail query after upload/delete so the document count updates without a full page reload.

## Cleanup

Temporary validation artifacts were removed:

- UI smoke KB `de56459d-a520-45a8-bc41-5d1043fdaf87` was deleted.
- Local WSL file `tmp_graph_workflow_claim.json` was removed.

## Post-fix validation

Status after the shared-dev-stack implementation: **passed**.

Implemented remediation:

- `docker-compose.dev.yaml` now runs API and worker with `CHILI_EVENT_BUS_BACKEND=redis` and `REDIS_URL=redis://redis:6379`.
- API and worker now load `backend/config/defaults/medicare_fraud_dev.yaml`, which selects:
   - Redis events
   - shared local filesystem object storage under `/app/data/objects`
   - Neo4j graph persistence at `bolt://neo4j:7687`
- API dependency factories now support the same local filesystem object store and Neo4j graph repository used by the worker.
- Backend Docker images install the Neo4j optional dependency.
- `scripts/smoke_graph_workflow.sh` exercises the live stack end to end.
- Investigation UI now supports KB selection, entity search, and click-to-load neighborhood discovery.

Live smoke executed against the rebuilt Docker dev stack:

```text
KB_ID=f5120f9c-93f4-47d2-ab06-420d9505ad7a
ENTITY_ID=da4da8e1-7fc2-41c4-a71d-9b515bc87f23
Graph workflow smoke passed.
```

Validated API results:

```json
{
   "id": "da4da8e1-7fc2-41c4-a71d-9b515bc87f23",
   "type": "claim",
   "properties": {
      "amount": 1250.5,
      "claim_id": "CLAIM-GRAPH-SMOKE-001",
      "procedure_codes": ["99213"],
      "service_date": "2026-04-26"
   }
}
```

Neighborhood validation returned:

```json
{
   "entity_count": 4,
   "relationship_count": 4
}
```

Browser validation opened the returned URL:

```text
http://localhost:5173/investigation?kb_id=f5120f9c-93f4-47d2-ab06-420d9505ad7a&entity_id=da4da8e1-7fc2-41c4-a71d-9b515bc87f23
```

Observed in the UI:

- KB selector loaded `Graph Workflow Smoke`.
- Entity Detail loaded the generated `claim` entity from the Investigation API.
- Graph canvas rendered the four-domain-node neighborhood.
- Entity search for `CLAIM-GRAPH-SMOKE-001` returned one result.
- Clicking the result selected the real generated entity ID and preserved the Investigation URL params.

Known remaining caveat: Flow B analytics still uses placeholder in-memory sources for some non-graph analytics inputs. During the smoke, the graph construction and query path passed; the worker logged an analytics-stage warning for the current placeholder GNN snapshot source. That does not block `kb.ready`, Neo4j graph persistence, or Investigation route queries, but it should be addressed when analytics adapters are promoted from scaffold to production wiring.
