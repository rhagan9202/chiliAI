# Vectorstore

`vectorstore` owns embedding storage and similarity search for chiliAI.

## Boundaries

Application code depends on `VectorServiceProtocol` from `vectorstore.protocols`.
`VectorService` depends on `VectorStoreProtocol` from `vectorstore.adapters.protocols`.
Qdrant is available only through `vectorstore.adapters.qdrant_adapter.QdrantVectorStore`.
Do not import `qdrant_client` outside the Qdrant adapter, dependency factories, or Qdrant-specific tests.

## Service Contract

The 1.0 service contract is synchronous:

- `index(request)`
- `search(request)`
- `batch_search(requests)`
- `get_record(knowledge_base_id, record_id)`
- `count(knowledge_base_id)`
- `delete_record(knowledge_base_id, record_id)`
- `delete_knowledge_base(knowledge_base_id)`

`delete_record` is idempotent and returns `False` for missing records.
`delete_knowledge_base` is idempotent and returns a `VectorDeleteResponse` with the deleted count.

## Qdrant Configuration

Use `VectorStoreConfig`:

```yaml
vectorstore:
  backend: qdrant
  uri: http://localhost:6333
  dimensions: 384
  distance_metric: cosine
```

`dimensions` must match the configured embeddings provider dimensions.

## Metadata Filters

Metadata values are scalar: `str | int | float | bool`.
Filters are exact-match filters. Qdrant float equality is implemented with an equal `gte/lte` range inside the adapter.

## Audit Artifacts

When `VectorService` receives an object store, successful index calls persist:

`knowledgebases/{knowledge_base_id}/vector_index/{request_id}.json`

The artifact contains request ID, knowledge base ID, receipts, receipt count, and creation time.
Audit write failures are logged and do not roll back vector writes.

## Live Qdrant Tests

Vectorstore 1.0 requires live Qdrant integration tests:

```bash
QDRANT_URL=http://localhost:6333 uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -m integration -v
```

## Non-Goals

1.0 does not include async contracts, pgvector, Weaviate, hybrid search, advanced metadata filters, public API endpoint expansion, RAG behavior changes, or cross-module document provenance cleanup.
