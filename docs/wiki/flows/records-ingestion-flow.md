# Records Ingestion Flow: Structured Data → Graph + Observations

**Verified against codebase:** 2026-05-20
**Sources:** `records/service.py`, `records/mappers/feed_mapper.py`, `records/models.py`, `records/service_models.py`, `api/routers/records.py`, `events/types.py`

---

## Overview

The records ingestion path is a **synchronous, single-step API flow** for structured tabular data (CSV, JSONL, or API-pushed JSON rows). It is parallel to the document ingestion pipeline — records land directly in `raw_records` storage without a multi-stage worker pipeline.

A downstream worker can then process `RecordsIngestedEvent` to map records into graph entities, relationships, and monitoring observations via `records/mappers/feed_mapper.py`.

---

## Step-by-step: Ingest Phase (Synchronous, API-layer)

```
1. API: POST /records/{kb_id}/files
         Payload: multipart/form-data {feed: str, file: .csv or .jsonl}
   OR
   API: POST /records/{kb_id}/push
         Payload: RecordPushRequest {feed_name: str, rows: list[dict[str, object]]}
   │
   └── RecordsService.register_records(knowledge_base_id, RecordSubmission)
         ├── _resolve_feed(feed_name) → RecordFeedConfig (from DomainConfig.records.feeds)
         │     └── Raises RecordFeedNotFoundError if feed_name not in config
         │
         ├── validate_rows(feed, submission.rows) → coerced_rows
         │     └── Raises RecordValidationError on schema violations
         │
         ├── For each coerced row:
         │     └── Extracts row[feed.id_field] → raw_id (RecordValidationError if missing)
         │         Creates RawRecord {
         │           knowledge_base_id, record_type (from feed), record_id: str(raw_id),
         │           payload: dict, source_type: "file_upload"|"api_push",
         │           source_ref: str | None, correlation_id, content_hash, ingested_at
         │         }
         │
         ├── RawRecordStore.persist(raw_records) → accepted_count (int)
         │     Backends: InMemoryRawRecordStore | PostgresRawRecordStore
         │
         └── EventBus.publish(RecordsIngestedEvent {
               correlation_id, kb_id, feed_name, record_type, record_count
             })
             event_type: "records.ingested"

Returns RecordIngestReceipt {kb_id, feed_name, record_type, correlation_id, accepted_count, created_at}
HTTP 202 Accepted
```

---

## Step-by-step: Mapping Phase (Worker-side)

```
Worker consumes "records.ingested"
   ├── Loads raw records from RawRecordStore by correlation_id
   │
   ├── map_batch(feed, records) → MappedGraph {entities: list[Entity], relationships: list[Relationship]}
   │     ├── For each entity_mapping in feed.entities:
   │     │     entity_id = "{entity_type}:{raw_id}"   ← deterministic, idempotent
   │     │     Builds Entity {id, type, properties (from property_fields map)}
   │     └── For each relationship_mapping in feed.relationships:
   │           relationship_id = "{rel_type}:{source_id}->{target_id}"
   │           Builds Relationship {id, type, source_id, target_id}
   │
   ├── map_observations(feed, records) → list[MonitoringObservation]
   │     ├── For each observation_mapping in feed.observations:
   │     │     score = row[score_field] (coerced to float via _as_float)
   │     │     entity_id = "{entity_type}:{raw_id}"
   │     │     MonitoringObservation {entity_id, entity_type, metric_name, score,
   │     │       observed_at=record.ingested_at,  ← idempotent across retries
   │     │       rationale=observation_mapping.rationale}
   │     └── Raises RecordMappingError if score_field value is non-numeric or entity type missing
   │
   ├── GraphServiceProtocol.upsert_task(GraphBuildTask) → GraphBuildReceipt
   │     (entities + relationships from MappedGraph)
   │
   └── MonitoringServiceProtocol.evaluate(MonitoringEvaluationRequest)
         (MonitoringObservation list fed into monitoring service)
```

---

## Feed Configuration

Records ingest behavior is fully driven by `DomainConfig.records.feeds: list[RecordFeedConfig]`. Each `RecordFeedConfig` defines:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | `str` | Feed identifier matched by API |
| `record_type` | `str` | Stored as `RawRecord.record_type` |
| `source` | `"file_upload" \| "api_push"` | Accepted submission source |
| `id_field` | `str` | Required field in each row; becomes `record_id` |
| `record_schema` | `dict[str, PropertyDefinition]` | Schema for row validation |
| `entities` | `list[RecordEntityMapping]` | Entity extraction rules |
| `relationships` | `list[RecordRelationshipMapping]` | Relationship extraction rules |
| `observations` | `list[RecordObservationMapping]` | Monitoring score extraction rules |

---

## Idempotency

- Entity and relationship IDs are deterministic: `"{entity_type}:{raw_id}"` and `"{rel_type}:{src_id}->{tgt_id}"`. Re-processing the same batch upserts the same graph nodes.
- Observation `observed_at` comes from `RawRecord.ingested_at`, not wall clock, ensuring retried handler writes identical observation rows.

---

## Key Differences from Document Ingestion

| Dimension | Document ingestion | Records ingestion |
|-----------|-------------------|-------------------|
| Trigger | Multipart file upload via `/knowledgebases/{kb_id}/documents` | CSV/JSONL file or JSON push via `/records/{kb_id}/files` or `/push` |
| Synchrony | Asynchronous (API registers, worker processes) | Synchronous registration; async mapping step in worker |
| Parsing/chunking | Full parse → chunk → extract → validate pipeline | No parsing; rows are validated against feed schema directly |
| Embedding | Entities are embedded and indexed in vector store | No embedding step for records |
| Configuration | Fixed pipeline, format-detected | Fully driven by `RecordFeedConfig` in `DomainConfig` |
| Event emitted | `DocumentsUploadedEvent` (→ long pipeline chain) | `RecordsIngestedEvent` (→ worker mapping only) |

---

## Relevant Source Files

- `backend/records/service.py` — `RecordsService.register_records()`, `create_records_service()`
- `backend/records/service_models.py` — `RecordSubmission`, `RecordIngestReceipt`
- `backend/records/models.py` — `RawRecord`
- `backend/records/mappers/feed_mapper.py` — `map_batch()`, `map_observations()`, `MappedGraph`
- `backend/records/validation.py` — `validate_rows()`
- `backend/records/adapters/protocols.py` — `RawRecordStore`
- `backend/records/adapters/in_memory.py` — `InMemoryRawRecordStore`
- `backend/records/adapters/postgres.py` — `PostgresRawRecordStore`
- `backend/api/routers/records.py` — HTTP entry points
- `backend/events/types.py` — `RecordsIngestedEvent`
- `backend/config/schema.py` — `RecordFeedConfig`, `RecordsConfig`
