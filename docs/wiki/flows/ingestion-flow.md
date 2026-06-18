# Ingestion Flow: Document Upload → Index

**Verified against codebase:** 2026-06-16
**Sources:** `api/routers/knowledgebases.py`, `ingestion/service.py`, `ingestion/recovery.py`, `ingestion/parsers/remote.py`, `events/types.py`, `agent/coordinator.py`, `records/service.py`

---

## Overview

Document ingestion is an event-driven pipeline. The API registers documents synchronously, then the worker processes them asynchronously via Redis Streams.

---

## Step-by-step

```
1. API: POST /knowledgebases/{kb_id}/documents
   - Rejects disallowed content types (ValidationConfig.allowed_content_types)
   - Reads each upload in 64 KiB chunks and raises 413 after max_file_size_mb
   - Computes content hash and records any replacement candidate
   - Calls IngestionServiceProtocol.register_documents(correlation_id=...)
     - Stores raw bytes to ObjectStore (key: knowledgebases/{kb_id}/documents/{doc_id}/source)
     - Publishes DocumentsUploadedEvent -> EventBus when at least one document is new or recoverable
     - Returns list[DocumentReceipt {source_document_id, storage_key, enqueued, ...}]
   - Starts a workflow only if any receipt.enqueued is true
   - Cleans replacement artifacts only after an enqueued receipt exists
   - Persists new DocumentRecord rows to KnowledgeBaseRepository

2. Worker (coordinator.py) consumes "documents.uploaded"
   - Calls IngestionServiceProtocol.process_documents_uploaded(event)
     - For each DocumentReference:
       - Reads raw bytes from ObjectStore
       - Resolves parser via ParserRegistry (format_resolver + registry)
       - Calls parser.parse() -> ParsedDocument
       - Returns ParseResult | DocumentParseFailure
   - Publishes DocumentsParsedEvent (on success) or DocumentsFailedEvent (on failure)

3. Worker consumes "documents.parsed"
   - Calls DocumentChunkerProtocol.chunk_document(parsed_doc, source_doc_id)
     - Applies ChunkingConfig.strategy (recursive / fixed_size / sentence)
       Returns ChunkingResult
   - Publishes DocumentsChunkedEvent

4. Worker consumes "documents.chunked"
   - Calls DocumentExtractorProtocol.extract_document(chunking_result)
     - Two implementations (selected by create_document_extractor factory):
       a. PatternDocumentExtractor - regex property-label matching per chunk
       b. LlmDocumentExtractor - schema-driven LLM prompts per chunk;
          JSON-mode output, markdown-fence stripped, required-property
          validation, natural-key dedup across chunks, intra-chunk
          relationship pass. Used when llm_client is wired.
       Returns ExtractionResult {entity_candidates, relationship_candidates}
   - Publishes EntitiesExtractedEvent

5. Worker consumes "entities.extracted"
   - Calls DocumentValidatorProtocol.validate_extraction(extraction_result)
     - Validates each entity/relationship against DomainConfig (EntityDefinitions, RelationshipDefinitions)
       Stamps provenance metadata on each valid Entity/Relationship:
       source_kind="document", source_document_id, source_chunk_id
       Returns ValidationReport {valid_entities, valid_relationships, errors}
   - Publishes EntitiesValidatedEvent

6. Worker consumes "entities.validated"
   - Calls GraphServiceProtocol.upsert_task(GraphBuildTask)
     - Upserts valid entities + relationships into graph DB
       Returns GraphBuildReceipt {upserted_entity_count, upserted_relationship_count}
   - Publishes GraphUpdatedEvent

7. Worker consumes "graph.updated"
   - Calls EmbeddingsServiceProtocol.embed(EmbedRequest)
     - Embeds entity text representations
       Returns EmbedResponse {items: list[EmbeddedItem {content_id, vector}]}
   - Publishes EmbeddingsCompleteEvent

8. Worker consumes "embeddings.complete"
   - Calls VectorServiceProtocol.index(VectorIndexRequest)
     - Inserts (content_id, vector) pairs into vector store
       Returns list[VectorIndexReceipt]
   - Publishes VectorsIndexedEvent

9. Worker consumes "vectors.indexed"
   - Computes GraphMetrics (entity_count, relationship_count)
   - Updates KB status -> "ready"
   - Publishes KnowledgeBaseReadyEvent
```

---

## Idempotent Re-upload (content-hash dedup, updated 2026-06-16)

Before registering a new document, `POST /knowledgebases/{kb_id}/documents` computes a SHA-256 content hash and checks for an existing `DocumentRecord` with the same `(kb_id, content_hash)` pair. If found:

```
1. Keep the existing document intact while calling register_documents().
2. If registration fails or returns receipt.enqueued = false, skip cleanup.
3. If receipt.enqueued = true:
   a. graph_service.delete_by_source_document(kb_id, existing.id)
   b. vector_service.delete_by_source_document(kb_id, existing.id)
   c. object_store: delete keys under knowledgebases/{kb_id}/documents/{existing.id}/ except receipt.storage_key
   d. repository.delete_document(kb_id, existing.id)
4. Add or refresh the DocumentRecord for the returned receipt.
5. Return DocumentReceipt.replaced_document_id = existing.id
```

The KB must not be busy or `pending_cleanup` (409 guard applies).

## Upload and Remote Fetch Limits

API-mediated local uploads are read incrementally by `_read_upload_file_with_limit()` with a 64 KiB read size and stop as soon as the configured byte cap is crossed. Remote fetches use `httpx.Client.stream()` and enforce their own `max_bytes` while iterating `response.iter_bytes()`. Malformed or negative `content-length` values raise `RemoteFetchError`, and redirected fetches must still end on HTTPS.

## Recovery Markers

If source bytes are stored but publishing `documents.uploaded` fails, a configured `IngestionRecoveryStore` persists an `IngestionRecoveryMarker` under `recovery/ingestion/`. `replay_recovery_markers()` reconstructs the upload event from the marker plus stored object metadata and removes the marker only after `EventBus.publish()` succeeds. Markers with missing source objects remain for inspection or repair.

---

## Failure Path

Any step failure → worker publishes `DocumentsFailedEvent` and/or sends event to dead-letter queue via `EventBus.publish_to_dlq()`.

---

## Storage Keys Written

At each step, the worker writes intermediate artifacts to ObjectStore:

| Step | Key pattern |
|------|------------|
| Raw upload | `knowledgebases/{kb_id}/documents/{doc_id}/source` |
| Remote URI marker | `knowledgebases/{kb_id}/documents/{doc_id}/remote.marker` |
| Recovery marker | `recovery/ingestion/{marker_id}.json` |
| Parsed | `knowledgebases/{kb_id}/parsed/{parsed_document_id}.json` |
| Chunks | `knowledgebases/{kb_id}/chunks/{parsed_document_id}.json` |
| Extraction | `knowledgebases/{kb_id}/extractions/{extraction_result_id}.json` |
| Validation | `knowledgebases/{kb_id}/validations/{extraction_result_id}.json` |
| Graph update | `knowledgebases/{kb_id}/graph_updates/{extraction_result_id}.json` |
| Embeddings | derived from graph update key as `knowledgebases/{kb_id}/embeddings/{extraction_result_id}.embeddings.json` |

---

## Event Payload Reference

Key event types and their wire shapes (all extend `EventBase {correlation_id, occurred_at, source, schema_version}`):

| Event type | Literal | Key payload fields |
|-----------|---------|-------------------|
| `DocumentsUploadedEvent` | `"documents.uploaded"` | `documents: list[DocumentReference {kb_id, source_document_id, filename, content_type, storage_key, uri, document_format, source_type, size_bytes}]` |
| `DocumentsParsedEvent` | `"documents.parsed"` | `documents: list[ParsedDocumentReference {kb_id, source_document_id, parsed_document_id, parser_name, parser_version, storage_key, parsed_document_storage_key}]` |
| `DocumentsChunkedEvent` | `"documents.chunked"` | `documents: list[ChunkedDocumentReference {kb_id, source_document_id, parsed_document_id, chunk_count, strategy, chunks_storage_key}]` |
| `EntitiesExtractedEvent` | `"entities.extracted"` | `documents: list[ExtractedDocumentReference {kb_id, source_document_id, extraction_result_id, entity_count, relationship_count, extraction_storage_key}]` |
| `EntitiesValidatedEvent` | `"entities.validated"` | `documents: list[ValidatedDocumentReference {kb_id, source_document_id, validation_report_id, valid_entity_count, valid_relationship_count, entity_error_count, relationship_error_count}]` |
| `GraphUpdatedEvent` | `"graph.updated"` | `documents: list[GraphUpdatedDocumentReference {kb_id, source_document_id, upserted_entity_count, upserted_relationship_count, graph_update_storage_key}]` |
| `EmbeddingsCompleteEvent` | `"embeddings.complete"` | `documents: list[EmbeddingsCompleteDocumentReference {kb_id, source_document_id, entity_count, graph_update_storage_key, embeddings_storage_key}]` |
| `VectorsIndexedEvent` | `"vectors.indexed"` | `records: list[VectorIndexedReference {kb_id, record_id, content_id, dimension}]` + `documents: list[VectorsIndexedDocumentReference {kb_id, source_document_id, vector_count, embeddings_storage_key, record_ids}]` |
| `KnowledgeBaseReadyEvent` | `"kb.ready"` | `knowledge_bases: list[KnowledgeBaseReadyReference {kb_id, entity_count, relationship_count, vector_count}]` |
| `DocumentsFailedEvent` | `"documents.failed"` | `documents: list[DocumentFailureReference {kb_id, source_document_id, error_message, storage_key}]` |

---

## Structured Records Path (Parallel Flow)

The `records/` module provides a **synchronous** structured-data ingestion path parallel to document ingestion. There is no multi-step worker pipeline for records.

```
API: POST /records/{kb_id}/files  (multipart: feed=str, file=.csv/.jsonl)
     POST /records/{kb_id}/push   (JSON: RecordPushRequest {feed_name, rows})
  │
  ├── RecordsService.register_records(knowledge_base_id, RecordSubmission)
  │     ├── _resolve_feed(feed_name) → RecordFeedConfig (from DomainConfig.records.feeds)
  │     ├── validate_rows_partition(feed, rows) → coerced rows + RejectedRow entries
  │     ├── For each row: RawRecord {kb_id, record_type, record_id, payload, source_type, source_ref, correlation_id, content_hash, ingested_at}
  │     ├── submission_hash_for(feed.name, row.content_hashes)
  │     ├── If RawRecordStore.was_submitted(...) is true:
  │     │     └── return duplicate receipt; skip persist and event publication
  │     ├── RawRecordStore.persist(raw_records) → accepted_count
  │     ├── RawRecordStore.record_submission(...)
  │     └── If accepted_count > 0, publish RecordsIngestedEvent {correlation_id, kb_id, feed_name, record_type, record_count}
  └── Returns RecordIngestReceipt {kb_id, feed_name, record_type, correlation_id, accepted_count, duplicate, duplicate_count, rejected_count, rejected[], created_at}
```

**Key differences from document ingestion:**
- Synchronous: no Redis Streams worker pipeline; the full operation completes in the API request.
- No parsing/chunking/extraction/embedding steps; records are persisted as raw JSON payloads.
- Whole-submission dedup is service-level. Duplicate file or push submissions return HTTP 200 with `duplicate=True`; fresh accepted submissions return HTTP 202 from the router.
- Valid rows can still ingest when some rows are rejected; rejected rows are reported on the receipt and only accepted rows are published downstream.
- Feed config (`RecordFeedConfig`) in `DomainConfig.records.feeds` defines schema, id field, record type, and entity/relationship/observation mappings.
- `RecordsIngestedEvent` (`"records.ingested"`) carries `correlation_id` so a worker can later process the batch via `records/mappers/feed_mapper.py` (graph entity extraction from records).

For the full records flow (including the mapper), see: [flows/records-ingestion-flow.md](records-ingestion-flow.md)

---

## Relevant Source Files

- `backend/api/routers/knowledgebases.py` — step 1 (document upload + idempotent re-upload)
- `backend/api/routers/records.py` — records ingestion API
- `backend/api/_kb_busy.py` — `ensure_kb_idle`, `WorkflowBusyTracker` protocol
- `backend/ingestion/service.py` — register + parse orchestration
- `backend/ingestion/chunker.py` — step 3
- `backend/ingestion/extractor.py` — step 4: `PatternDocumentExtractor`, `LlmDocumentExtractor`, `create_document_extractor`
- `backend/ingestion/validator.py` — step 5 + provenance stamping
- `backend/agent/coordinator.py` — worker dispatch logic
- `backend/events/types.py` — all event payload shapes
- `backend/records/service.py` — structured records ingestion
- `backend/records/mappers/feed_mapper.py` — record → entity/observation mapping
- `backend/shared/provenance.py` — provenance key/value constants
