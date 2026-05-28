# Module: shared

**Verified against codebase:** 2026-05-28
**Source:** `backend/shared/`

## Purpose

Lightweight shared contracts library. Provides generic platform types, cross-cutting protocols, and small utilities. Imported by all other backend modules. Contains **no business logic** and is **dependency-light** — only `pydantic`, standard library, `structlog`, and `opentelemetry`.

Does **not** own: domain types, adapter implementations, service logic.

---

## Public Surface

### `types.py`
- `Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`, `MonitoringObservation` — generic runtime types
- `EntityDefinition`, `RelationshipDefinition`, `PropertyDefinition`, `PropertyType` — config-definition types
- `validate_entity(entity, entity_definitions) -> list[str]`
- `validate_relationship(relationship, relationship_definitions, entities_by_id) -> list[str]`

Full shapes: see [contracts/shared-types.md](../contracts/shared-types.md).

### `protocols.py`
- `ObjectStoreProtocol` — `put_bytes`, `get_bytes`, `delete`, `exists`, `list_keys`
- `Configurable` — `configure(config: DomainConfig) -> None`
- `StoredObjectWriteResult`, `StoredObject`

Full shapes: see [contracts/shared-types.md](../contracts/shared-types.md).

### `exceptions.py`

Last verified: 2026-05-20

```python
class ConfigurationError(Exception):
    """Raised when configuration references an unsupported or unavailable backend."""
```

This is the only exception class currently in `shared/exceptions.py`. Module-specific exceptions live in each module's own `exceptions.py`.

### `logging.py`

```python
def configure_logging() -> None: ...
def get_logger(name: str) -> structlog.BoundLogger: ...
```
Configures `structlog` with JSON output. Called by `create_app()` and `coordinator.py`.

### `tracing.py`

```python
def setup_tracing() -> None: ...
def instrument_fastapi_app(app: FastAPI) -> None: ...
```
Sets up OpenTelemetry. No-ops when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset.

### `utils.py`

```python
def generate_id() -> str: ...    # Returns a unique string ID (UUID4 or similar)
def utc_now() -> datetime: ...   # Returns timezone-aware UTC datetime
```

### `alerts.py`

Last verified: 2026-05-20

```python
AlertSeverity = Literal["low", "medium", "high", "critical"]

def normalize_severity(raw_severity: str, confidence: float) -> AlertSeverity:
    """Normalize a raw severity string to a typed AlertSeverity.
    Falls back to confidence-based mapping if raw_severity is not a known literal:
    confidence >= 0.9 → "critical"; >= 0.75 → "high"; >= 0.5 → "medium"; else "low"."""
```

### `provenance.py`

Exports canonical metadata-key constants and `source_kind` value constants used by every write and read site that stamps or filters on provenance. All sites must import from here — never use bare string literals.

```python
# Metadata keys (type: Final)
SOURCE_KIND_KEY: Final          # "source_kind"
SOURCE_FEED_KEY: Final          # "source_feed"
SOURCE_RAW_RECORD_ID_KEY: Final # "source_raw_record_id"
SOURCE_DOCUMENT_ID_KEY: Final   # "source_document_id"
SOURCE_CHUNK_ID_KEY: Final      # "source_chunk_id"
SOURCE_ID_KEY: Final            # "source_id"

# source_kind values (type: Final)
SOURCE_KIND_RECORD: Final       # "record"
SOURCE_KIND_DOCUMENT: Final     # "document"
```

**Usage pattern:**
- Document path (`ingestion/validator.py`): stamps `SOURCE_KIND_DOCUMENT`, `SOURCE_DOCUMENT_ID_KEY`, `SOURCE_CHUNK_ID_KEY` onto validated `Entity` and `Relationship` objects.
- Records path (`records/mappers/feed_mapper.py`): stamps `SOURCE_KIND_RECORD`, `SOURCE_FEED_KEY`, `SOURCE_RAW_RECORD_ID_KEY` onto mapped `Entity` and `Relationship` objects.
- Vector indexing (`agent/coordinator.py`): uses `SOURCE_KIND_KEY`, `SOURCE_DOCUMENT_ID_KEY`, `SOURCE_ID_KEY` in `VectorRecord.metadata`.

### `validation.py`

```python
def sanitize_filename(filename: str) -> str: ...
def validate_content_type(content_type: str | None, allowed: set[str]) -> bool: ...
```

---

## Module Dependencies

- Standard library only + `pydantic`, `structlog`, `opentelemetry`
- Does **not** import from any other backend module (by design)
