# Module: records

**Verified against codebase:** 2026-05-22
**Source:** `backend/records/`

## Purpose

Structured/tabular ingestion. Accepts CSV or JSONL files and JSON-array API pushes, validates rows against `RecordFeedConfig` schema, persists to `raw_records` landing table, and publishes `RecordsIngestedEvent`. Parallel to `ingestion/` (which handles documents); `records/` handles structured data.

---

## Service Protocol (`records/protocols.py`)

```python
class RecordsServiceProtocol(Protocol):
    def register_records(
        self,
        knowledge_base_id: str,
        submission: RecordSubmission,
    ) -> RecordIngestReceipt: ...
```

## Adapter Protocol (`records/adapters/protocols.py`)

```python
class RawRecordStore(Protocol):
    def persist(self, records: list[RawRecord]) -> int:
        """Persist records idempotently; return the count of newly inserted rows."""

    def load_batch(self, *, knowledge_base_id: str, correlation_id: str) -> list[RawRecord]:
        """Return all records landed under one ingest run, ordered deterministically."""

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all records for a knowledge base; return the count removed."""
```

`InMemoryRawRecordStore` additionally exposes `count_for_kb(kb_id) -> int` (test helper, not on the protocol). `PostgresRawRecordStore` also implements `delete_by_kb`.

---

## Service Models (`records/service_models.py`)

### `RecordSubmission`
```python
class RecordSubmission(BaseModel):
    feed_name: str
    rows: list[dict[str, object]]
    source_type: Literal["file_upload", "api_push"]
    source_ref: str | None = None
```

### `RecordIngestReceipt`
```python
class RecordIngestReceipt(BaseModel):
    knowledge_base_id: str
    feed_name: str
    record_type: str
    correlation_id: str
    accepted_count: int      # >= 0
    created_at: datetime
```

---

## Models (`records/models.py`)

- `RawRecord` — individual persisted record row
- `RecordBatch` — batch of raw records keyed by `correlation_id`
- `content_hash_for(row)` — deterministic hash for deduplication

---

## Validation (`records/validation.py`)

```python
def coerce_row(row: dict, schema: dict[str, PropertyDefinition]) -> dict: ...
def validate_rows(rows: list[dict], schema: dict[str, PropertyDefinition]) -> list[str]: ...
```

Validates each row against `RecordFeedConfig.record_schema` (which uses `PropertyDefinition` types).

---

## Mappers (`records/mappers/feed_mapper.py`)

Last verified: 2026-05-22

Single mapper module; no plugin registration mechanism. Mapper functions consume `RecordFeedConfig` (from `DomainConfig`) and operate on `list[RawRecord]`.

```python
@dataclass(frozen=True, slots=True)
class MappedGraph:
    """Graph objects produced from a record batch."""
    entities: list[Entity]
    relationships: list[Relationship]

def map_batch(feed: RecordFeedConfig, records: list[RawRecord]) -> MappedGraph:
    """Map a record batch to deduplicated entities and relationships.
    Entity IDs are deterministic: "{entity_type}:{raw_id}".
    Re-running the same feed is idempotent (upserts same node IDs).
    Raises RecordMappingError if a required id_field is missing from a row.
    Stamps provenance metadata on every Entity and Relationship produced."""

def map_observations(
    feed: RecordFeedConfig, records: list[RawRecord]
) -> list[MonitoringObservation]:
    """Derive scored MonitoringObservations from a record batch.
    observed_at is sourced from record.ingested_at, keeping handler retries idempotent.
    Rows with a None score_field are silently skipped.
    Raises RecordMappingError if entity_type not in feed or id_field missing."""
```

Entity ID format: `"{entity_type}:{raw_id}"` — e.g., `"provider:NPI-123"`. Relationship ID format: `"{relationship_type}:{source_id}->{target_id}"`. Deduplication is dict-keyed; last write wins within a batch.

**Provenance stamping (2026-05-22):** `map_batch` now stamps the following metadata on every `Entity` and `Relationship` using constants from [`shared/provenance.py`](shared.md#provenancepy):

| Key constant | Value |
|---|---|
| `SOURCE_KIND_KEY` | `SOURCE_KIND_RECORD` (`"record"`) |
| `SOURCE_FEED_KEY` | `feed.name` |
| `SOURCE_RAW_RECORD_ID_KEY` | `record.record_id` |

---

## Directory Structure

```
records/
  service.py           # RecordsService.register_records(): validate → persist → publish
  service_models.py    # RecordSubmission, RecordIngestReceipt
  protocols.py         # RecordsServiceProtocol
  models.py            # RawRecord, RecordBatch, content_hash_for
  exceptions.py        # RecordFeedNotFoundError, RecordPersistenceError, RecordsError
  validation.py        # coerce_row / validate_rows
  mappers/
    feed_mapper.py     # map_batch(), map_observations(), MappedGraph
  adapters/
    sources/
      file_source.py   # CsvFileSource, JsonlFileSource
    in_memory.py       # InMemoryRawRecordStore
    postgres.py        # PostgresRawRecordStore (writes to raw_records table)
```

---

## Module Dependencies

- `config/schema.py` — `RecordFeedConfig`, `RecordsConfig`
- `events/` — publishes `RecordsIngestedEvent`
- `database/` — `ConnectionProvider` (for Postgres store)
- `shared/types.py` — `PropertyDefinition`

---

## Tests

Location: `backend/tests/records/`
Postgres store tests marked `@pytest.mark.integration`.
