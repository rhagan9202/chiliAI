# Vectorstore 1.0 Design

## Purpose

Vectorstore 1.0 makes `backend/vectorstore` a production-ready module while preserving chiliAI's interface-first architecture. The release scope is limited to the vectorstore module and its direct factory/configuration touchpoints. Qdrant is the only production backend for 1.0, but it remains fully isolated behind an adapter.

## Current State

The module already provides:

- `VectorService` with synchronous `index()` and `search()` methods.
- Service DTOs for index and search flows.
- `VectorStoreProtocol` with `upsert_records()` and `search()`.
- `InMemoryVectorStore` for local development and tests.
- `QdrantVectorStore` with upsert, search, and adapter-local record deletion support.
- API and worker factory wiring that selects in-memory or Qdrant from `VectorStoreConfig`.
- Unit tests and optional Qdrant live integration tests.

The release gaps are lifecycle operations, complete service/adapter contracts, audit artifacts, batch handling, Qdrant parity, required live integration coverage, and explicit architecture guardrails.

## Hard Architecture Requirement

Qdrant must remain behind `vectorstore.adapters.qdrant_adapter.QdrantVectorStore`. Business logic must not import Qdrant SDK types, call Qdrant APIs directly, or depend on Qdrant-specific behavior.

Allowed Qdrant references:

- `backend/vectorstore/adapters/qdrant_adapter.py` may import and use `qdrant_client`.
- Dependency factories may import `QdrantVectorStore` to instantiate the adapter from `VectorStoreConfig`.
- Tests may import Qdrant SDK types only in Qdrant adapter tests and live integration tests.

Disallowed Qdrant references:

- `backend/vectorstore/service.py`
- `backend/vectorstore/service_models.py`
- `backend/vectorstore/protocols.py`
- `backend/vectorstore/models.py`
- Any non-vectorstore feature module business logic

Architecture tests must enforce these boundaries before 1.0 is considered releasable.

## Architecture

The module keeps the existing layered structure:

- `vectorstore.models`: persisted vector-domain records and adapter-neutral match objects.
- `vectorstore.service_models`: service request/response DTOs.
- `vectorstore.adapters.protocols.VectorStoreProtocol`: backend-neutral storage contract.
- `vectorstore.protocols.VectorServiceProtocol`: public service boundary consumed by other modules.
- `vectorstore.service.VectorService`: backend-agnostic orchestration, validation, chunking, audit persistence, event publishing, and exception normalization.
- `vectorstore.adapters.in_memory.InMemoryVectorStore`: local/test adapter that implements the full adapter contract.
- `vectorstore.adapters.qdrant_adapter.QdrantVectorStore`: production adapter that maps the contract onto Qdrant.

The service depends only on `VectorStoreProtocol`, `EventBus`, and an optional object-store dependency for audit artifacts. The adapter contract provides storage primitives; the service contract provides application-level workflows.

## Release Surface

Vectorstore 1.0 exposes a complete synchronous service contract:

- `index(request: VectorIndexRequest) -> list[VectorIndexReceipt]`
- `search(request: VectorSearchRequest) -> VectorSearchResponse`
- `batch_search(requests: list[VectorSearchRequest]) -> list[VectorSearchResponse]`
- `get_record(knowledge_base_id: str, record_id: str) -> VectorRecord | None`
- `count(knowledge_base_id: str) -> int`
- `delete_record(knowledge_base_id: str, record_id: str) -> bool`
- `delete_knowledge_base(knowledge_base_id: str) -> VectorDeleteResponse`

The adapter protocol exposes backend-neutral primitives with equivalent semantics:

- `upsert_records(knowledge_base_id: str, records: list[VectorRecord]) -> list[VectorRecord]`
- `search(knowledge_base_id: str, query_vector: list[float], limit: int, filters: dict[str, MetadataValue] | None = None) -> list[VectorMatch]`
- `get_record(knowledge_base_id: str, record_id: str) -> VectorRecord | None`
- `count_records(knowledge_base_id: str) -> int`
- `delete_record(knowledge_base_id: str, record_id: str) -> bool`
- `delete_namespace(knowledge_base_id: str) -> int`

`delete_namespace()` returns the number of records deleted when the backend can determine it. If the backend must count before deleting, the adapter performs that internally and still returns a count through the protocol. The service never calls Qdrant-specific collection APIs.

## Model Additions

Add service models:

- `VectorDeleteResponse`
  - `knowledge_base_id: str`
  - `deleted_count: int`
  - `deleted_at: datetime`
- `VectorAuditArtifact`
  - `request_id: str`
  - `knowledge_base_id: str`
  - `receipt_count: int`
  - `receipts: list[VectorIndexReceipt]`
  - `created_at: datetime`

Add event type:

- `VectorsDeletedEvent`
  - `event_type: Literal["vectors.deleted"]`
  - `knowledge_base_id: str`
  - `deleted_count: int`

The event type lives in `backend/events/types.py` because events are a cross-cutting contract. The vectorstore module owns publishing it through `VectorService.delete_knowledge_base()`.

## Indexing Behavior

`VectorService.index()`:

1. Builds `VectorRecord` instances from each submission.
2. Splits records into chunks using `max_batch_size`, default `500`.
3. Calls `VectorStoreProtocol.upsert_records()` once per chunk.
4. Verifies that each expected record is returned exactly once.
5. Preserves aggregate receipt order.
6. Publishes `VectorsIndexedEvent` after successful indexing.
7. Persists a JSON audit artifact when object-store persistence is configured.

Audit artifacts use this key format:

`knowledgebases/{knowledge_base_id}/vector_index/{request_id}.json`

Audit persistence failures are logged as warnings and do not roll back successful vector writes.

## Search Behavior

`VectorService.search()` validates the query, delegates to `VectorStoreProtocol.search()`, wraps backend failures in vectorstore exceptions, and maps adapter matches into service DTOs.

`VectorService.batch_search()` executes `search()` for each request in input order and returns responses in the same order. Adapter-specific batch optimization is out of scope for 1.0 and can be added later without changing the service contract.

## Lifecycle Behavior

`get_record()` returns `None` for missing records.

`count()` returns `0` for missing namespaces.

`delete_record()` is idempotent and returns `False` when the record is absent.

`delete_knowledge_base()` is idempotent, delegates namespace deletion through `VectorStoreProtocol.delete_namespace()`, publishes `VectorsDeletedEvent`, and returns `VectorDeleteResponse`.

The knowledge-base API router does not need to call vectorstore deletion as part of this module-only release. That integration can be a later API-level story once vectorstore 1.0 is available.

## Metadata And Filtering

Metadata remains scalar for 1.0:

`str | int | float | bool`

Filter semantics are exact match. Qdrant float filters continue to use an equal `gte/lte` range internally because that is adapter implementation detail. List filters, range filters, hybrid lexical/vector search, and faceting are not part of 1.0.

## Qdrant Adapter Requirements

`QdrantVectorStore` must implement the full adapter protocol:

- Create collections lazily on upsert using configured dimensions and distance metric.
- Upsert points with stable deterministic Qdrant point IDs derived from vector record IDs.
- Store payload fields needed to reconstruct `VectorRecord`.
- Search with payload and scalar metadata filters.
- Retrieve a single record by record ID.
- Count records in a collection.
- Delete a single record by record ID.
- Delete a knowledge-base namespace by deleting the corresponding Qdrant collection, after determining the deleted count.
- Return empty results for missing collections.
- Wrap Qdrant failures in vectorstore exceptions.

The adapter may use Qdrant collection, retrieve, count, scroll, and delete APIs internally, but those details must not leak into service models or non-adapter modules.

## In-Memory Adapter Requirements

`InMemoryVectorStore` must implement the same adapter protocol as Qdrant. It remains suitable for deterministic unit tests and local development. Its behavior must match Qdrant semantics for missing records, missing namespaces, counts, deletion, filters, and dimension checks.

## Testing And Release Gates

Vectorstore 1.0 requires:

- Unit tests for all new and existing service models.
- Service tests for index chunking, receipt verification, audit artifact persistence, audit failure logging, search, batch search, get, count, single-record delete, and knowledge-base delete.
- In-memory adapter tests for full protocol behavior.
- Qdrant fake-client tests for collection creation, upsert payloads, search filters, get, count, record delete, namespace delete, missing collection behavior, and exception wrapping.
- Live Qdrant integration tests as a required release gate using `QDRANT_URL`.
- Architecture guard tests that fail if Qdrant SDK imports leak outside approved files.
- Coverage of at least 90% for `backend/vectorstore`.
- Existing repo lint/type/test commands must pass for touched modules.

## Documentation

Add or update vectorstore documentation covering:

- Public synchronous service contract.
- Adapter contract and architecture boundary.
- Qdrant configuration.
- Required live Qdrant test setup.
- Metadata filter semantics.
- Lifecycle/delete semantics.
- Audit artifact format.
- Non-goals for 1.0.

## Non-Goals

Vectorstore 1.0 does not include:

- Additional production adapters such as pgvector or Weaviate.
- Async service or adapter contracts.
- Hybrid search.
- Advanced metadata filters.
- Public API endpoint expansion.
- RAG behavior changes.
- Worker pipeline changes beyond compatibility fixes required by contract updates.
- Document-level provenance cleanup across ingestion and graph modules.

## Acceptance Criteria

Vectorstore 1.0 is complete when:

- The synchronous service and adapter protocols expose the full release surface.
- In-memory and Qdrant adapters implement the full adapter contract.
- Qdrant remains isolated behind the adapter and approved factory/test locations.
- Service workflows are backend-neutral and tested through protocols.
- Live Qdrant integration tests pass with `QDRANT_URL`.
- Vectorstore coverage is at least 90%.
- Module documentation describes operation, configuration, lifecycle behavior, and release non-goals.
