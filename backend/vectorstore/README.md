# Vectorstore

`vectorstore` owns embedding storage and similarity search for chiliAI.

## Boundaries

Application code depends on `VectorServiceProtocol` from `vectorstore.protocols`.
`VectorService` depends on `VectorStoreProtocol` from `vectorstore.adapters.protocols`.
Qdrant is available only through `vectorstore.adapters.qdrant_adapter.QdrantVectorStore`.
Dependency factories may import `QdrantVectorStore`, but direct `qdrant_client` imports belong only in the Qdrant adapter and Qdrant-specific tests.

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

## Source-Document Delete

`VectorService` and `VectorStoreProtocol` expose `delete_by_source_document(kb_id, doc_id)` which removes all indexed vectors whose metadata contains `source_document_id == doc_id` within the given KB namespace. This is the vector-store leg of the KB-delete cascade. Like the other delete methods it is idempotent — calling it when no matching vectors exist is a no-op. See the graph module README and the demo spec at [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the full cascade sequence.

## Non-Goals

1.0 does not include async contracts, pgvector, Weaviate, hybrid search, advanced metadata filters, public API endpoint expansion, RAG behavior changes, or cross-module document provenance cleanup.
