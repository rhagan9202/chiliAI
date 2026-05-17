# Records Module & Structured Ingestion (Plan B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the top-level `records/` module for structured/tabular ingestion (parallel to `ingestion/` for documents) and wire Flow 1 — a structured-records batch fans out to the knowledge graph and to the `observations` table.

**Architecture:** A new `records/` module accepts CSV/JSONL file uploads and JSON api-push payloads, validates each row against a config-declared feed schema, lands canonical rows in the `raw_records` Postgres table, and publishes a `RecordsIngestedEvent`. The worker's new `handle_records_ingested` handler reads those rows back, maps them to graph entities/relationships via a config-driven feed mapper, upserts them through a new `GraphService.upsert_records_graph` method, derives scored observations, and writes them to the `observations` table through a new write-side Postgres adapter in `monitoring/`. All adapters have an in-memory sibling so the default unit suite stays green without a database.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg 3 (sync, via the `database/` `ConnectionProvider` protocol from Plan A), Redis Streams events, pytest.

**Scope note:** This is Plan B of three. Plan A delivered the `database/` module and the `0001_persistence_baseline` migration — the `raw_records` and `observations` tables **already exist**; this plan adds no migration. Plan C adds the per-consumer *read-side* Postgres adapters (`monitoring`, `analytics/timeseries`, `analytics/risk`), the `analytics/metrics/` package, and Flows 2/3/4. This plan produces working, testable structured ingestion on its own: upload a CSV → graph entities + observation rows.

**Reference spec:** `docs/superpowers/specs/2026-05-14-backend-persistence-design.md` (§5.2 `records/`, §6.1–6.2 schema, §7 config, §8 Flow 1).

**Design decisions confirmed for this plan (deviations from the literal spec, approved):**

- **Graph write path** — Flow 1 does **not** call `GraphService.upsert_task()`. That method requires document-pipeline artifacts and publishes a `GraphUpdatedEvent` the existing `handle_graph_updated` handler would crash on. Instead this plan adds `GraphService.upsert_records_graph()`, which upserts entities/relationships only, persists no artifacts, and publishes no event. Triggering metric recompute from records is deferred to Plan C.
- **Observation writer** — the `observations` table write-side adapter lives in `monitoring/adapters/postgres.py` (`PostgresObservationStore`) behind a new narrow `ObservationWriter` protocol. Plan C extends that same file with the read-side `ObservationSourceProtocol` implementation.
- **API surface** — this plan ships a `records` FastAPI router (`POST /records/{kb}/files`, `POST /records/{kb}/push`) so structured ingestion is usable end to end.

---

## Conventions

- All commands run from `backend/` unless stated otherwise.
- The `[postgres]` extra is already declared (Plan A). New Postgres adapters in this plan depend only on the psycopg-free `database.ConnectionProvider` protocol — they import no psycopg and need no lazy-import handling.
- Run unit tests with `pytest -m "not integration"`; integration tests with `pytest -m integration` against a running TimescaleDB that has had `alembic upgrade head` applied (Plan A's `0001_persistence_baseline` creates `raw_records` and `observations`).
- New code must pass `pyright --strict` and `ruff check .`. New `records` source/tests and the new individual API/test files are added to `tool.pyright.include` in Task 1.
- Per-package pytest coverage ≥ 85% is evaluated on a run that includes the integration suite against a live DB, so the Postgres adapters count toward coverage — mirroring how Plan A's `database` package is gated.
- The host venv is the fast path for tests/typecheck/lint: `.venv/bin/pytest`, `.venv/bin/pyright`, `.venv/bin/ruff` from `backend/`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/pyproject.toml` | Add `records*` to packaging; add `records`/test paths to pyright include |
| `backend/events/types.py` | New `RecordsIngestedEvent`; add to `AnyEvent` + `__all__` |
| `backend/events/codec.py` | Register `records.ingested` in the codec registry |
| `backend/config/schema.py` | `RecordEntityMapping`, `RecordRelationshipMapping`, `RecordObservationMapping`, `RecordFeedConfig`, `RecordsConfig`; `CapabilitiesConfig.structured_ingestion`; `DomainConfig.records` + cross-validation |
| `backend/records/__init__.py` | Public exports |
| `backend/records/exceptions.py` | `RecordsError` hierarchy |
| `backend/records/models.py` | `RawRecord`, `RecordBatch`, `content_hash_for` |
| `backend/records/service_models.py` | `RecordSubmission`, `RecordIngestReceipt` |
| `backend/records/validation.py` | `coerce_row`, `validate_rows` |
| `backend/records/protocols.py` | `RecordsServiceProtocol` |
| `backend/records/adapters/protocols.py` | `RawRecordStore`, `RecordSourceProtocol` |
| `backend/records/adapters/in_memory.py` | `InMemoryRawRecordStore` |
| `backend/records/adapters/postgres.py` | `PostgresRawRecordStore` |
| `backend/records/adapters/sources/file_source.py` | `CsvFileSource`, `JsonlFileSource` |
| `backend/records/adapters/sources/api_push_source.py` | `ApiPushSource` |
| `backend/records/mappers/feed_mapper.py` | `MappedGraph`, `map_batch`, `map_observations` |
| `backend/records/service.py` | `RecordsService`, `create_records_service` |
| `backend/monitoring/adapters/protocols.py` | New `ObservationWriter` protocol |
| `backend/monitoring/adapters/postgres.py` | `PostgresObservationStore` (write side) |
| `backend/monitoring/adapters/in_memory.py` | New `InMemoryObservationWriter` |
| `backend/graph/service.py` | New `GraphService.upsert_records_graph` |
| `backend/agent/coordinator.py` | `handle_records_ingested` + builders + dispatch wiring |
| `backend/api/routers/records.py` | `records` REST router |
| `backend/api/dependencies.py` | `get_connection_provider`, `get_raw_record_store`, `get_records_service` |
| `backend/api/app.py` | Register the records router |
| `backend/config/defaults/*.yaml` | Example feed definitions + `structured_ingestion` flag |
| `backend/records/README.md`, `backend/README.md`, `docs/architecture.md`, `.github/copilot-instructions.md` | Docs |
| `backend/tests/records/`, `tests/agent/`, `tests/graph/`, `tests/events/`, `tests/monitoring/`, `tests/api/` | Tests |

---

## Task 1: Packaging and pyright wiring

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add `records` to the setuptools package list**

In `[tool.setuptools.packages.find]`, append `"records*"` to the `include` list:

```toml
[tool.setuptools.packages.find]
include = ["api*", "agent*", "shared*", "config*", "events*", "storage*",
           "ingestion*", "graph*", "vectorstore*", "embeddings*", "rag*",
           "llm*", "analytics*", "monitoring*", "database*", "records*"]
```

- [ ] **Step 2: Add the new source path to the pyright include list**

In `[tool.pyright]`, in the `include` array, insert `"records"` immediately after the `"monitoring"` line:

```toml
    "monitoring",
    "records",
    "tests/agent",
```

Then insert `"api/routers/records.py"` immediately after `"api/routers/alerts.py"`:

```toml
    "api/routers/alerts.py",
    "api/routers/records.py",
    "api/routers/investigation.py",
```

- [ ] **Step 3: Add the new test paths to the pyright include list**

In the same `include` array, insert `"tests/api/test_records_router.py"` immediately after `"tests/api/test_production_guardrail.py"`:

```toml
    "tests/api/test_production_guardrail.py",
    "tests/api/test_records_router.py",
    "tests/api/test_ws_router.py",
```

Insert `"tests/monitoring/test_postgres_observation_store.py"` immediately after `"tests/graph"` (the last current entry):

```toml
    "tests/graph",
    "tests/monitoring/test_postgres_observation_store.py",
    "tests/records",
]
```

Add only these entries; leave every other line untouched.

- [ ] **Step 4: Verify the project still installs and pyright still resolves**

Run: `pip install -e ".[dev,postgres]"`
Expected: completes with no errors.

Run: `pyright`
Expected: 0 errors (no new files yet — this confirms the config edits are valid).

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build: register the records package and pyright paths"
```

---

## Task 2: `RecordsIngestedEvent` event type

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/events/codec.py`
- Create: `backend/tests/events/test_records_event.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/events/test_records_event.py`:

```python
"""Tests for the RecordsIngestedEvent type and its codec registration."""

from __future__ import annotations

from events.codec import EVENT_TYPE_REGISTRY, decode_event, encode_event
from events.types import RecordsIngestedEvent


def test_event_has_stable_type() -> None:
    event = RecordsIngestedEvent(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=3,
    )
    assert event.event_type == "records.ingested"


def test_event_is_registered_in_codec() -> None:
    assert EVENT_TYPE_REGISTRY["records.ingested"] is RecordsIngestedEvent


def test_event_round_trips_through_the_codec() -> None:
    event = RecordsIngestedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=5,
    )
    decoded = decode_event(encode_event(event))
    assert isinstance(decoded, RecordsIngestedEvent)
    assert decoded.correlation_id == "corr-1"
    assert decoded.knowledge_base_id == "kb-1"
    assert decoded.feed_name == "claims_feed"
    assert decoded.record_count == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/events/test_records_event.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecordsIngestedEvent'`.

- [ ] **Step 3: Add `RecordsIngestedEvent` to `events/types.py`**

In `backend/events/types.py`, add this class immediately after `ClaimsIngestedEvent` (just before the `AnyEvent` union):

```python
class RecordsIngestedEvent(EventBase):
    """Published when a structured-records batch has landed in ``raw_records``.

    Carries enough context for the worker's Flow 1 handler to resolve the
    feed config and read the persisted rows back by ``correlation_id``.
    """

    event_type: Literal["records.ingested"] = "records.ingested"
    knowledge_base_id: str
    feed_name: str
    record_type: str
    record_count: int = Field(ge=0)
```

- [ ] **Step 4: Add `RecordsIngestedEvent` to the `AnyEvent` union**

In the `AnyEvent` union, add the member after `ClaimsIngestedEvent`:

```python
    | ClaimsReceivedEvent
    | ClaimsIngestedEvent
    | RecordsIngestedEvent
)
```

- [ ] **Step 5: Add `RecordsIngestedEvent` to `__all__`**

In the `__all__` list in `events/types.py`, insert `"RecordsIngestedEvent"` between `"RagCompletionReference"` and `"RiskScoredEvent"`.

- [ ] **Step 6: Register the event in the codec**

In `backend/events/codec.py`, add `RecordsIngestedEvent` to the import block from `events.types` (alphabetical, after `RagCompletedEvent`):

```python
    RagCompletedEvent,
    RecordsIngestedEvent,
    RiskScoredEvent,
```

Then add to `EVENT_TYPE_REGISTRY`, after the `"claims.ingested"` entry:

```python
    "claims.ingested": ClaimsIngestedEvent,
    "records.ingested": RecordsIngestedEvent,
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/events/test_records_event.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Type-check**

Run: `pyright events tests/events/test_records_event.py`
Expected: 0 errors.

- [ ] **Step 9: Commit**

```bash
git add backend/events/types.py backend/events/codec.py backend/tests/events/test_records_event.py
git commit -m "feat: add RecordsIngestedEvent event type"
```

---

## Task 3: Records configuration schema

**Files:**
- Modify: `backend/config/schema.py`
- Create: `backend/records/__init__.py` *(empty package marker — placed here so `tests/records` can exist)*
- Create: `backend/tests/records/__init__.py`
- Create: `backend/tests/records/test_config.py`

- [ ] **Step 1: Create the test package markers**

Create `backend/records/__init__.py` with:

```python
"""Structured / tabular record ingestion module."""

from __future__ import annotations
```

Create `backend/tests/records/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/records/test_config.py`:

```python
"""Tests for the records configuration schema and DomainConfig wiring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import (
    CapabilitiesConfig,
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordsConfig,
)
from shared.types import PropertyDefinition, PropertyType


def _schema() -> dict[str, PropertyDefinition]:
    return {
        "claim_id": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True),
        "score": PropertyDefinition(type=PropertyType.DECIMAL, display="Score"),
    }


def test_capabilities_defaults_structured_ingestion_off() -> None:
    assert CapabilitiesConfig().structured_ingestion is False


def test_records_config_defaults_to_no_feeds() -> None:
    assert RecordsConfig().feeds == []


def test_feed_config_accepts_a_full_definition() -> None:
    feed = RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema=_schema(),
        entities=[RecordEntityMapping(entity_type="claim", id_field="claim_id")],
        observations=[
            RecordObservationMapping(
                metric_name="claim_anomaly", entity_type="claim", score_field="score"
            )
        ],
    )
    assert feed.name == "claims_feed"
    assert feed.entities[0].entity_type == "claim"


def test_feed_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        RecordFeedConfig(
            name="f",
            record_type="r",
            source="kafka",  # type: ignore[arg-type]
            id_field="claim_id",
            record_schema=_schema(),
        )


def test_domain_config_rejects_feed_with_unknown_entity_type() -> None:
    from config.loader import load_config  # noqa: PLC0415

    base = load_config()
    payload = base.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "bad_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True}
                },
                "entities": [{"entity_type": "not_an_entity", "id_field": "claim_id"}],
            }
        ]
    }
    with pytest.raises(ValidationError, match="unknown entity type"):
        base.__class__.model_validate(payload)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/records/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecordsConfig'`.

- [ ] **Step 4: Import `PropertyDefinition` into `config/schema.py`**

In `backend/config/schema.py`, change the `shared.types` import line to:

```python
from shared.types import EntityDefinition, PropertyDefinition, RelationshipDefinition
```

- [ ] **Step 5: Add `structured_ingestion` to `CapabilitiesConfig`**

In `CapabilitiesConfig`, add the field after `explainability`:

```python
class CapabilitiesConfig(BaseModel):
    """Feature toggles for optional analytics capabilities."""

    timeseries: bool = False
    gnn: bool = False
    risk_scoring: bool = False
    rag_chat: bool = False
    explainability: bool = False
    structured_ingestion: bool = False
```

- [ ] **Step 6: Add the records config models**

In `backend/config/schema.py`, add these classes immediately after `ValidationConfig` (just before the `# Top-level config` divider):

```python
class RecordEntityMapping(BaseModel):
    """Maps fields of a record row onto one graph entity."""

    entity_type: str
    id_field: str
    property_fields: dict[str, str] = Field(default_factory=dict)


class RecordRelationshipMapping(BaseModel):
    """Maps a pair of a row's mapped entities onto one graph relationship."""

    relationship_type: str
    source_entity_type: str
    target_entity_type: str


class RecordObservationMapping(BaseModel):
    """Maps a numeric record field onto a scored monitoring observation."""

    metric_name: str
    entity_type: str
    score_field: str
    rationale: str = ""


class RecordFeedConfig(BaseModel):
    """A single structured-ingestion feed definition."""

    name: str
    record_type: str
    source: Literal["file_upload", "api_push"]
    id_field: str
    record_schema: dict[str, PropertyDefinition] = Field(default_factory=dict)
    entities: list[RecordEntityMapping] = Field(default_factory=list)
    relationships: list[RecordRelationshipMapping] = Field(default_factory=list)
    observations: list[RecordObservationMapping] = Field(default_factory=list)


class RecordsConfig(BaseModel):
    """Structured-ingestion feed configuration for the domain."""

    feeds: list[RecordFeedConfig] = Field(default_factory=list)
```

> **Note:** the schema field is named `record_schema`, not `schema`, deliberately — a Pydantic v2 field named `schema` shadows a `BaseModel` attribute and emits a warning, which `CLAUDE.md` forbids silencing.

- [ ] **Step 7: Wire `records` into `DomainConfig`**

In the `DomainConfig` class body, add the field after `validation`:

```python
    validation: ValidationConfig | None = None
    records: RecordsConfig | None = None
    alerts: AlertsConfig
```

In `_validate_cross_references`, add the default-fill after the `validation` block:

```python
        if self.validation is None:
            self.validation = ValidationConfig()
        if self.records is None:
            self.records = RecordsConfig()
```

- [ ] **Step 8: Add records cross-validation**

In `_validate_cross_references`, immediately before the final `if errors:` block, add:

```python
        # --- records feed references ---
        records_config = self.records
        if records_config is not None:
            relationship_name_set = set(rel_names)
            for feed in records_config.feeds:
                schema_fields = set(feed.record_schema.keys())
                if feed.id_field not in schema_fields:
                    errors.append(
                        f"Records feed '{feed.name}' id_field '{feed.id_field}' "
                        f"is not declared in record_schema."
                    )
                feed_entity_types: set[str] = set()
                for entity_mapping in feed.entities:
                    feed_entity_types.add(entity_mapping.entity_type)
                    if entity_mapping.entity_type not in entity_name_set:
                        errors.append(
                            f"Records feed '{feed.name}' maps to unknown entity "
                            f"type '{entity_mapping.entity_type}'."
                        )
                    if entity_mapping.id_field not in schema_fields:
                        errors.append(
                            f"Records feed '{feed.name}' entity mapping id_field "
                            f"'{entity_mapping.id_field}' is not in record_schema."
                        )
                for relationship_mapping in feed.relationships:
                    if relationship_mapping.relationship_type not in relationship_name_set:
                        errors.append(
                            f"Records feed '{feed.name}' maps to unknown relationship "
                            f"type '{relationship_mapping.relationship_type}'."
                        )
                for observation_mapping in feed.observations:
                    if observation_mapping.entity_type not in feed_entity_types:
                        errors.append(
                            f"Records feed '{feed.name}' observation references entity "
                            f"type '{observation_mapping.entity_type}' not mapped by the feed."
                        )
```

- [ ] **Step 9: Export the new models**

In the `__all__` list at the bottom of `config/schema.py`, add (keep the list readable — exact alphabetical order is not enforced in this file): `"RecordEntityMapping"`, `"RecordFeedConfig"`, `"RecordObservationMapping"`, `"RecordRelationshipMapping"`, `"RecordsConfig"`.

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/records/test_config.py tests/config -v`
Expected: PASS — new records config tests pass and all existing config tests still pass.

- [ ] **Step 11: Type-check**

Run: `pyright config tests/records/test_config.py`
Expected: 0 errors.

- [ ] **Step 12: Commit**

```bash
git add backend/config/schema.py backend/records/__init__.py backend/tests/records/__init__.py backend/tests/records/test_config.py
git commit -m "feat: add records feed configuration schema"
```

---

## Task 4: `records/exceptions.py` — exception hierarchy

**Files:**
- Create: `backend/records/exceptions.py`
- Create: `backend/tests/records/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/records/test_exceptions.py`:

```python
"""Tests for the records module exception hierarchy."""

from __future__ import annotations

from records.exceptions import (
    RecordFeedNotFoundError,
    RecordMappingError,
    RecordPersistenceError,
    RecordsError,
    RecordValidationError,
)


def test_all_errors_subclass_records_error() -> None:
    assert issubclass(RecordValidationError, RecordsError)
    assert issubclass(RecordPersistenceError, RecordsError)
    assert issubclass(RecordFeedNotFoundError, RecordsError)
    assert issubclass(RecordMappingError, RecordsError)


def test_feed_not_found_error_names_the_feed() -> None:
    error = RecordFeedNotFoundError("claims_feed")
    assert error.feed_name == "claims_feed"
    assert "claims_feed" in str(error)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/records/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.exceptions'`.

- [ ] **Step 3: Write the implementation**

Create `backend/records/exceptions.py`:

```python
"""Exception hierarchy for the records module."""

from __future__ import annotations


class RecordsError(Exception):
    """Base exception for structured-records ingestion failures."""


class RecordValidationError(RecordsError):
    """Raised when submitted rows fail feed-schema validation or coercion."""


class RecordPersistenceError(RecordsError):
    """Raised when raw records cannot be persisted or read back."""


class RecordFeedNotFoundError(RecordsError):
    """Raised when a submission references a feed not declared in config."""

    def __init__(self, feed_name: str) -> None:
        super().__init__(f"Records feed '{feed_name}' is not declared in the domain config.")
        self.feed_name = feed_name


class RecordMappingError(RecordsError):
    """Raised when a record row cannot be mapped to graph or observation objects."""


__all__ = [
    "RecordFeedNotFoundError",
    "RecordMappingError",
    "RecordPersistenceError",
    "RecordValidationError",
    "RecordsError",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/records/test_exceptions.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/records/exceptions.py backend/tests/records/test_exceptions.py
git commit -m "feat: add records module exception hierarchy"
```

---

## Task 5: Records domain models and service-boundary models

**Files:**
- Create: `backend/records/models.py`
- Create: `backend/records/service_models.py`
- Create: `backend/tests/records/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/records/test_models.py`:

```python
"""Tests for records domain models and service-boundary models."""

from __future__ import annotations

from records.models import RawRecord, RecordBatch, content_hash_for
from records.service_models import RecordIngestReceipt, RecordSubmission


def _record(record_id: str = "claim-1") -> RawRecord:
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=record_id,
        payload={"claim_id": record_id, "amount": 10.0},
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id="corr-1",
        content_hash=content_hash_for({"claim_id": record_id, "amount": 10.0}),
    )


def test_content_hash_is_stable_and_order_independent() -> None:
    first = content_hash_for({"a": 1, "b": 2})
    second = content_hash_for({"b": 2, "a": 1})
    assert first == second
    assert first != content_hash_for({"a": 1, "b": 3})


def test_raw_record_carries_all_table_columns() -> None:
    record = _record()
    assert record.knowledge_base_id == "kb-1"
    assert record.record_type == "claim_record"
    assert record.source_type == "file_upload"
    assert record.ingested_at is not None


def test_record_batch_groups_records() -> None:
    batch = RecordBatch(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        correlation_id="corr-1",
        records=[_record("claim-1"), _record("claim-2")],
    )
    assert len(batch.records) == 2


def test_record_submission_and_receipt() -> None:
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "claim-1"}],
        source_type="api_push",
    )
    assert submission.source_ref is None
    receipt = RecordIngestReceipt(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        correlation_id="corr-1",
        accepted_count=1,
    )
    assert receipt.accepted_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/records/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.models'`.

- [ ] **Step 3: Write `records/models.py`**

Create `backend/records/models.py`:

```python
"""Internal domain models for structured-record ingestion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now


def content_hash_for(payload: Mapping[str, object]) -> str:
    """Return a stable SHA-256 hex digest of a record payload.

    The payload is serialized with sorted keys so logically equal rows hash
    identically regardless of field order — this digest backs the
    ``raw_records`` idempotency check.
    """

    canonical = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RawRecord(BaseModel):
    """A canonical row landed in the ``raw_records`` table."""

    knowledge_base_id: str
    record_type: str
    record_id: str
    payload: dict[str, object] = Field(default_factory=dict)
    source_type: Literal["file_upload", "api_push"]
    source_ref: str | None = None
    correlation_id: str
    content_hash: str
    ingested_at: datetime = Field(default_factory=utc_now)


class RecordBatch(BaseModel):
    """A batch of raw records produced by one feed submission."""

    knowledge_base_id: str
    feed_name: str
    record_type: str
    correlation_id: str
    records: list[RawRecord] = Field(default_factory=list)


__all__ = [
    "RawRecord",
    "RecordBatch",
    "content_hash_for",
]
```

- [ ] **Step 4: Write `records/service_models.py`**

Create `backend/records/service_models.py`:

```python
"""Service-boundary models for the records ingestion API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now


class RecordSubmission(BaseModel):
    """A batch of rows submitted to a single feed."""

    feed_name: str
    rows: list[dict[str, object]]
    source_type: Literal["file_upload", "api_push"]
    source_ref: str | None = None


class RecordIngestReceipt(BaseModel):
    """Receipt returned after a record submission is registered."""

    knowledge_base_id: str
    feed_name: str
    record_type: str
    correlation_id: str
    accepted_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "RecordIngestReceipt",
    "RecordSubmission",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/records/test_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Type-check**

Run: `pyright records tests/records/test_models.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/records/models.py backend/records/service_models.py backend/tests/records/test_models.py
git commit -m "feat: add records domain and service-boundary models"
```

---

## Task 6: Raw record store protocols and in-memory adapter

**Files:**
- Create: `backend/records/adapters/__init__.py`
- Create: `backend/records/adapters/protocols.py`
- Create: `backend/records/adapters/in_memory.py`
- Create: `backend/tests/records/test_in_memory_store.py`

- [ ] **Step 1: Create the adapters package marker**

Create `backend/records/adapters/__init__.py` with:

```python
"""Records module adapters."""

from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/records/test_in_memory_store.py`:

```python
"""Tests for the in-memory raw record store."""

from __future__ import annotations

from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.models import RawRecord, content_hash_for


def _record(record_id: str, *, correlation_id: str = "corr-1") -> RawRecord:
    payload = {"claim_id": record_id}
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=record_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id=correlation_id,
        content_hash=content_hash_for(payload),
    )


def test_store_satisfies_protocol() -> None:
    store: RawRecordStore = InMemoryRawRecordStore()
    assert store.persist([]) == 0


def test_persist_counts_only_new_rows() -> None:
    store = InMemoryRawRecordStore()
    assert store.persist([_record("c1"), _record("c2")]) == 2
    # Re-persisting the same primary keys inserts nothing (idempotency).
    assert store.persist([_record("c1")]) == 0


def test_load_batch_filters_by_correlation_id() -> None:
    store = InMemoryRawRecordStore()
    store.persist([_record("c1", correlation_id="corr-1")])
    store.persist([_record("c2", correlation_id="corr-2")])
    loaded = store.load_batch(knowledge_base_id="kb-1", correlation_id="corr-1")
    assert [record.record_id for record in loaded] == ["c1"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/records/test_in_memory_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.adapters.protocols'`.

- [ ] **Step 4: Write `records/adapters/protocols.py`**

Create `backend/records/adapters/protocols.py`:

```python
"""Adapter-level protocols for the records module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from records.models import RawRecord


@runtime_checkable
class RawRecordStore(Protocol):
    """Persist and read back canonical structured records."""

    def persist(self, records: list[RawRecord]) -> int:
        """Persist records idempotently; return the count of newly inserted rows."""
        ...

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        """Return all records landed under one ingest run, ordered deterministically."""
        ...


@runtime_checkable
class RecordSourceProtocol(Protocol):
    """Parse raw submission bytes into a list of record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]: ...


__all__ = [
    "RawRecordStore",
    "RecordSourceProtocol",
]
```

- [ ] **Step 5: Write `records/adapters/in_memory.py`**

Create `backend/records/adapters/in_memory.py`:

```python
"""In-memory raw record store for tests and local development."""

from __future__ import annotations

from records.models import RawRecord

__all__ = ["InMemoryRawRecordStore"]


class InMemoryRawRecordStore:
    """A dict-backed ``RawRecordStore`` keyed by the table's primary key."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], RawRecord] = {}

    def persist(self, records: list[RawRecord]) -> int:
        inserted = 0
        for record in records:
            key = (record.knowledge_base_id, record.record_type, record.record_id)
            if key in self._records:
                continue
            self._records[key] = record
            inserted += 1
        return inserted

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.correlation_id == correlation_id
        ]
        return sorted(matches, key=lambda record: (record.record_type, record.record_id))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/records/test_in_memory_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Type-check**

Run: `pyright records tests/records/test_in_memory_store.py`
Expected: 0 errors.

- [ ] **Step 8: Commit**

```bash
git add backend/records/adapters/__init__.py backend/records/adapters/protocols.py backend/records/adapters/in_memory.py backend/tests/records/test_in_memory_store.py
git commit -m "feat: add raw record store protocols and in-memory adapter"
```

---

## Task 7: `PostgresRawRecordStore` adapter

**Files:**
- Create: `backend/records/adapters/postgres.py`
- Create: `backend/tests/records/conftest.py`
- Create: `backend/tests/records/test_postgres_store.py`

- [ ] **Step 1: Create the integration-test fixture module**

Create `backend/tests/records/conftest.py`:

```python
"""Shared fixtures for records integration tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping records integration test.")
    return url
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/records/test_postgres_store.py`:

```python
"""Integration tests for the Postgres raw record store."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from records.adapters.postgres import PostgresRawRecordStore
from records.models import RawRecord, content_hash_for

pytestmark = pytest.mark.integration


def _record(record_id: str, *, correlation_id: str) -> RawRecord:
    payload = {"claim_id": record_id, "amount": 12.5}
    return RawRecord(
        knowledge_base_id="kb-records-test",
        record_type="claim_record",
        record_id=record_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id=correlation_id,
        content_hash=content_hash_for(payload),
    )


def test_persist_and_load_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRawRecordStore(provider)
    correlation_id = "corr-records-store-1"
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()

        inserted = store.persist(
            [
                _record("claim-1", correlation_id=correlation_id),
                _record("claim-2", correlation_id=correlation_id),
            ]
        )
        assert inserted == 2

        # Idempotent re-persist inserts nothing.
        assert store.persist([_record("claim-1", correlation_id=correlation_id)]) == 0

        loaded = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=correlation_id
        )
        assert [record.record_id for record in loaded] == ["claim-1", "claim-2"]
        assert loaded[0].payload["amount"] == 12.5
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()
        provider.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/records/test_postgres_store.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.adapters.postgres'` (start TimescaleDB and apply migrations first: `docker compose -f docker-compose.dev.yaml up -d postgres && make migrate`, or run `alembic upgrade head` against the DB).

- [ ] **Step 4: Write the implementation**

Create `backend/records/adapters/postgres.py`:

```python
"""Postgres-backed raw record store.

This adapter depends only on the psycopg-free ``database.ConnectionProvider``
protocol — it imports no psycopg and is safe to import unconditionally. The
``payload`` column is jsonb; rows are inserted with an explicit ``::jsonb``
cast over a serialized-JSON text parameter so no psycopg JSON adapter is
needed.
"""

from __future__ import annotations

import json

from database.protocols import ConnectionProvider, Row
from records.exceptions import RecordPersistenceError
from records.models import RawRecord

_INSERT_SQL = """
    INSERT INTO raw_records (
        knowledge_base_id, record_type, record_id, payload,
        source_type, source_ref, correlation_id, content_hash, ingested_at
    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, record_type, record_id) DO NOTHING
"""

_SELECT_SQL = """
    SELECT knowledge_base_id, record_type, record_id, payload,
           source_type, source_ref, correlation_id, content_hash, ingested_at
    FROM raw_records
    WHERE knowledge_base_id = %s AND correlation_id = %s
    ORDER BY record_type, record_id
"""


class PostgresRawRecordStore:
    """A ``RawRecordStore`` backed by the ``raw_records`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def persist(self, records: list[RawRecord]) -> int:
        if not records:
            return 0
        inserted = 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    cursor = conn.execute(
                        _INSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.record_type,
                            record.record_id,
                            json.dumps(record.payload, default=str),
                            record.source_type,
                            record.source_ref,
                            record.correlation_id,
                            record.content_hash,
                            record.ingested_at,
                        ),
                    )
                    inserted += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise RecordPersistenceError("Failed to persist raw records.") from exc
        return inserted

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SELECT_SQL, (knowledge_base_id, correlation_id)
                ).fetchall()
        except Exception as exc:
            raise RecordPersistenceError("Failed to load raw records.") from exc
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Row) -> RawRecord:
    payload = row[3]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise RecordPersistenceError("raw_records.payload did not decode to an object.")
    source_type = str(row[4])
    if source_type not in {"file_upload", "api_push"}:
        raise RecordPersistenceError(
            f"raw_records.source_type has unexpected value '{source_type}'."
        )
    return RawRecord(
        knowledge_base_id=str(row[0]),
        record_type=str(row[1]),
        record_id=str(row[2]),
        payload=payload,
        source_type=source_type,
        source_ref=None if row[5] is None else str(row[5]),
        correlation_id=str(row[6]),
        content_hash=str(row[7]),
        ingested_at=row[8],  # type: ignore[arg-type]
    )


__all__ = [
    "PostgresRawRecordStore",
]
```

> **Note on `ingested_at`:** psycopg 3 returns `timestamptz` columns as `datetime` objects, which Pydantic accepts directly. The `# type: ignore[arg-type]` is needed because the `Row` element is statically typed `object`. If `pyright --strict` reports the ignore is unused, remove it.

- [ ] **Step 5: Run test to verify it passes**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/records/test_postgres_store.py -v -m integration`
Expected: PASS (1 test).

- [ ] **Step 6: Type-check**

Run: `pyright records tests/records/conftest.py tests/records/test_postgres_store.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/records/adapters/postgres.py backend/tests/records/conftest.py backend/tests/records/test_postgres_store.py
git commit -m "feat: add Postgres raw record store adapter"
```

---

## Task 8: Record source adapters (CSV, JSONL, api-push)

**Files:**
- Create: `backend/records/adapters/sources/__init__.py`
- Create: `backend/records/adapters/sources/file_source.py`
- Create: `backend/records/adapters/sources/api_push_source.py`
- Create: `backend/tests/records/test_sources.py`

- [ ] **Step 1: Create the sources package marker**

Create `backend/records/adapters/sources/__init__.py` with:

```python
"""Record source adapters: file uploads and api-push payloads."""

from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/records/test_sources.py`:

```python
"""Tests for record source adapters."""

from __future__ import annotations

import pytest

from records.adapters.sources.api_push_source import ApiPushSource
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordValidationError


def test_csv_source_parses_rows() -> None:
    raw = b"claim_id,amount\nc1,10\nc2,20\n"
    rows = CsvFileSource().read_rows(raw)
    assert rows == [
        {"claim_id": "c1", "amount": "10"},
        {"claim_id": "c2", "amount": "20"},
    ]


def test_csv_source_rejects_empty_content() -> None:
    with pytest.raises(RecordValidationError):
        CsvFileSource().read_rows(b"")


def test_jsonl_source_parses_one_object_per_line() -> None:
    raw = b'{"claim_id": "c1", "amount": 10}\n{"claim_id": "c2", "amount": 20}\n'
    rows = JsonlFileSource().read_rows(raw)
    assert rows == [
        {"claim_id": "c1", "amount": 10},
        {"claim_id": "c2", "amount": 20},
    ]


def test_jsonl_source_rejects_non_object_line() -> None:
    with pytest.raises(RecordValidationError):
        JsonlFileSource().read_rows(b'[1, 2, 3]\n')


def test_api_push_source_parses_a_json_array() -> None:
    raw = b'[{"claim_id": "c1"}, {"claim_id": "c2"}]'
    rows = ApiPushSource().read_rows(raw)
    assert rows == [{"claim_id": "c1"}, {"claim_id": "c2"}]


def test_api_push_source_rejects_a_bare_object() -> None:
    with pytest.raises(RecordValidationError):
        ApiPushSource().read_rows(b'{"claim_id": "c1"}')
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/records/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.adapters.sources.file_source'`.

- [ ] **Step 4: Write `records/adapters/sources/file_source.py`**

Create `backend/records/adapters/sources/file_source.py`:

```python
"""File-upload record sources: delimited CSV and line-delimited JSON."""

from __future__ import annotations

import csv
import io
import json

from records.exceptions import RecordValidationError

__all__ = ["CsvFileSource", "JsonlFileSource"]


class CsvFileSource:
    """Parse a CSV upload into one row dict per record (all values are strings)."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        text = raw.decode("utf-8-sig")
        if text.strip() == "":
            raise RecordValidationError("CSV upload is empty.")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise RecordValidationError("CSV upload has no header row.")
        rows: list[dict[str, object]] = []
        for line in reader:
            rows.append({key: value for key, value in line.items() if key is not None})
        if not rows:
            raise RecordValidationError("CSV upload has a header but no data rows.")
        return rows


class JsonlFileSource:
    """Parse a JSON-Lines upload into one row dict per non-blank line."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        text = raw.decode("utf-8")
        rows: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.strip() == "":
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RecordValidationError(
                    f"JSONL line {line_number} is not valid JSON."
                ) from exc
            if not isinstance(parsed, dict):
                raise RecordValidationError(
                    f"JSONL line {line_number} is not a JSON object."
                )
            rows.append({str(key): value for key, value in parsed.items()})
        if not rows:
            raise RecordValidationError("JSONL upload has no record lines.")
        return rows
```

- [ ] **Step 5: Write `records/adapters/sources/api_push_source.py`**

Create `backend/records/adapters/sources/api_push_source.py`:

```python
"""Api-push record source: a JSON array of record objects."""

from __future__ import annotations

import json

from records.exceptions import RecordValidationError

__all__ = ["ApiPushSource"]


class ApiPushSource:
    """Parse an api-push request body (a JSON array) into record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RecordValidationError("Api-push payload is not valid JSON.") from exc
        if not isinstance(parsed, list):
            raise RecordValidationError("Api-push payload must be a JSON array of objects.")
        rows: list[dict[str, object]] = []
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise RecordValidationError(
                    f"Api-push payload item {index} is not a JSON object."
                )
            rows.append({str(key): value for key, value in item.items()})
        if not rows:
            raise RecordValidationError("Api-push payload contains no records.")
        return rows
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/records/test_sources.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Type-check**

Run: `pyright records tests/records/test_sources.py`
Expected: 0 errors.

- [ ] **Step 8: Commit**

```bash
git add backend/records/adapters/sources backend/tests/records/test_sources.py
git commit -m "feat: add CSV, JSONL, and api-push record sources"
```

---

## Task 9: Row validation and coercion

**Files:**
- Create: `backend/records/validation.py`
- Create: `backend/tests/records/test_validation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/records/test_validation.py`:

```python
"""Tests for record row coercion and feed-schema validation."""

from __future__ import annotations

import pytest

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from records.validation import coerce_row, validate_rows
from shared.types import PropertyDefinition, PropertyType


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema={
            "claim_id": PropertyDefinition(
                type=PropertyType.STRING, display="Claim ID", required=True
            ),
            "amount": PropertyDefinition(
                type=PropertyType.DECIMAL, display="Amount", required=True, min_value=0
            ),
            "score": PropertyDefinition(type=PropertyType.DECIMAL, display="Score"),
        },
    )


def test_coerce_row_converts_string_numbers() -> None:
    schema = _feed().record_schema
    coerced = coerce_row({"claim_id": "c1", "amount": "12.5"}, schema)
    assert coerced["amount"] == 12.5
    assert coerced["claim_id"] == "c1"


def test_coerce_row_raises_on_non_numeric_string() -> None:
    schema = _feed().record_schema
    with pytest.raises(RecordValidationError):
        coerce_row({"claim_id": "c1", "amount": "not-a-number"}, schema)


def test_validate_rows_returns_coerced_rows() -> None:
    rows = validate_rows(_feed(), [{"claim_id": "c1", "amount": "10"}])
    assert rows == [{"claim_id": "c1", "amount": 10.0}]


def test_validate_rows_rejects_missing_required_field() -> None:
    with pytest.raises(RecordValidationError, match="row 0"):
        validate_rows(_feed(), [{"claim_id": "c1"}])


def test_validate_rows_rejects_unknown_field() -> None:
    with pytest.raises(RecordValidationError, match="Unexpected"):
        validate_rows(_feed(), [{"claim_id": "c1", "amount": 10, "extra": "x"}])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/records/test_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.validation'`.

- [ ] **Step 3: Write the implementation**

Create `backend/records/validation.py`:

```python
"""Coercion and feed-schema validation for submitted record rows.

Row validation reuses :func:`shared.types.validate_entity` by treating a feed
``record_schema`` as a synthetic ``EntityDefinition`` — this keeps a single
source of truth for property type / range / pattern checks.
"""

from __future__ import annotations

from collections.abc import Mapping

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from shared.types import (
    Entity,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    validate_entity,
)

_TRUE_TOKENS = frozenset({"true", "1", "yes"})
_FALSE_TOKENS = frozenset({"false", "0", "no"})


def _coerce_value(value: object, property_type: PropertyType) -> object:
    """Coerce a string-encoded value to the declared property type.

    Non-string values pass through untouched (JSON sources are already typed).
    """

    if not isinstance(value, str):
        return value
    text = value.strip()
    if property_type is PropertyType.INTEGER:
        try:
            return int(text)
        except ValueError as exc:
            raise RecordValidationError(f"Value '{value}' is not a valid integer.") from exc
    if property_type is PropertyType.DECIMAL:
        try:
            return float(text)
        except ValueError as exc:
            raise RecordValidationError(f"Value '{value}' is not a valid number.") from exc
    if property_type is PropertyType.BOOLEAN:
        lowered = text.lower()
        if lowered in _TRUE_TOKENS:
            return True
        if lowered in _FALSE_TOKENS:
            return False
        raise RecordValidationError(f"Value '{value}' is not a valid boolean.")
    return value


def coerce_row(
    row: Mapping[str, object], schema: dict[str, PropertyDefinition]
) -> dict[str, object]:
    """Return a copy of ``row`` with values coerced to their declared types."""

    coerced: dict[str, object] = {}
    for key, value in row.items():
        definition = schema.get(key)
        coerced[key] = value if definition is None else _coerce_value(value, definition.type)
    return coerced


def validate_rows(
    feed: RecordFeedConfig, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Coerce and validate every row against the feed schema.

    Returns the coerced rows on success; raises :class:`RecordValidationError`
    listing every offending row when any row fails.
    """

    definition = EntityDefinition(
        name=feed.record_type,
        display_label=feed.record_type,
        icon="record",
        properties=feed.record_schema,
    )
    coerced_rows: list[dict[str, object]] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        coerced = coerce_row(row, feed.record_schema)
        coerced_rows.append(coerced)
        row_errors = validate_entity(
            Entity(id=f"row-{index}", type=feed.record_type, properties=coerced),
            [definition],
        )
        if row_errors:
            errors.append(f"row {index}: " + "; ".join(row_errors))
    if errors:
        raise RecordValidationError(
            f"Feed '{feed.name}' validation failed:\n  - " + "\n  - ".join(errors)
        )
    return coerced_rows


__all__ = [
    "coerce_row",
    "validate_rows",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/records/test_validation.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Type-check**

Run: `pyright records tests/records/test_validation.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/records/validation.py backend/tests/records/test_validation.py
git commit -m "feat: add record row coercion and feed-schema validation"
```

---

## Task 10: Config-driven feed mapper

**Files:**
- Create: `backend/records/mappers/__init__.py`
- Create: `backend/records/mappers/feed_mapper.py`
- Create: `backend/tests/records/test_feed_mapper.py`

- [ ] **Step 1: Create the mappers package marker**

Create `backend/records/mappers/__init__.py` with:

```python
"""Config-driven mappers from record rows to graph and observation objects."""

from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/records/test_feed_mapper.py`:

```python
"""Tests for the config-driven feed mapper."""

from __future__ import annotations

import pytest

from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordRelationshipMapping,
)
from records.exceptions import RecordMappingError
from records.mappers.feed_mapper import map_batch, map_observations
from records.models import RawRecord, content_hash_for


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        entities=[
            RecordEntityMapping(
                entity_type="claim",
                id_field="claim_id",
                property_fields={"amount": "billed_amount"},
            ),
            RecordEntityMapping(entity_type="provider", id_field="provider_npi"),
        ],
        relationships=[
            RecordRelationshipMapping(
                relationship_type="submitted_by",
                source_entity_type="claim",
                target_entity_type="provider",
            )
        ],
        observations=[
            RecordObservationMapping(
                metric_name="claim_anomaly",
                entity_type="claim",
                score_field="anomaly_score",
                rationale="Structured-feed anomaly score.",
            )
        ],
    )


def _record(claim_id: str) -> RawRecord:
    payload: dict[str, object] = {
        "claim_id": claim_id,
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "anomaly_score": 0.8,
    }
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=claim_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id="corr-1",
        content_hash=content_hash_for(payload),
    )


def test_map_batch_builds_entities_and_relationships() -> None:
    mapped = map_batch(_feed(), [_record("c1")])
    entity_ids = {entity.id for entity in mapped.entities}
    assert entity_ids == {"claim:c1", "provider:1234567890"}
    claim = next(entity for entity in mapped.entities if entity.id == "claim:c1")
    assert claim.type == "claim"
    assert claim.properties["amount"] == 99.0
    assert len(mapped.relationships) == 1
    relationship = mapped.relationships[0]
    assert relationship.type == "submitted_by"
    assert relationship.source_id == "claim:c1"
    assert relationship.target_id == "provider:1234567890"


def test_map_batch_deduplicates_repeated_entities() -> None:
    mapped = map_batch(_feed(), [_record("c1"), _record("c1")])
    assert len(mapped.entities) == 2  # claim:c1 + provider:1234567890, deduplicated


def test_map_batch_raises_on_missing_id_field() -> None:
    record = _record("c1")
    record.payload.pop("provider_npi")
    with pytest.raises(RecordMappingError):
        map_batch(_feed(), [record])


def test_map_observations_uses_record_ingested_at() -> None:
    record = _record("c1")
    observations = map_observations(_feed(), [record])
    assert len(observations) == 1
    observation = observations[0]
    assert observation.entity_id == "claim:c1"
    assert observation.metric_name == "claim_anomaly"
    assert observation.score == 0.8
    assert observation.observed_at == record.ingested_at
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/records/test_feed_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.mappers.feed_mapper'`.

- [ ] **Step 4: Write the implementation**

Create `backend/records/mappers/feed_mapper.py`:

```python
"""Map structured record rows onto graph entities, relationships, observations.

Entity ids are deterministic (``"{entity_type}:{raw_id}"``) so re-running a
feed upserts the same nodes — the worker's Flow 1 handler is idempotent.
Observation timestamps come from the persisted record's ``ingested_at`` so a
retried handler writes identical ``observations`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import RecordFeedConfig
from monitoring.models import MonitoringObservation
from records.exceptions import RecordMappingError
from records.models import RawRecord
from shared.types import Entity, Relationship


@dataclass(frozen=True, slots=True)
class MappedGraph:
    """Graph objects produced from a record batch."""

    entities: list[Entity]
    relationships: list[Relationship]


def _entity_id(entity_type: str, raw_id: object) -> str:
    return f"{entity_type}:{raw_id}"


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise RecordMappingError("Observation score must be numeric, not boolean.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise RecordMappingError(f"Observation score '{value}' is not numeric.") from exc
    raise RecordMappingError(
        f"Observation score of type {type(value).__name__} is not numeric."
    )


def map_batch(feed: RecordFeedConfig, records: list[RawRecord]) -> MappedGraph:
    """Map a record batch to deduplicated graph entities and relationships."""

    entities: dict[str, Entity] = {}
    relationships: dict[str, Relationship] = {}
    for record in records:
        row = record.payload
        row_entity_ids: dict[str, str] = {}
        for entity_mapping in feed.entities:
            raw_id = row.get(entity_mapping.id_field)
            if raw_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' record '{record.record_id}' is missing "
                    f"id field '{entity_mapping.id_field}'."
                )
            entity_id = _entity_id(entity_mapping.entity_type, raw_id)
            properties: dict[str, object] = {
                entity_property: row[record_field]
                for entity_property, record_field in entity_mapping.property_fields.items()
                if record_field in row
            }
            entities[entity_id] = Entity(
                id=entity_id, type=entity_mapping.entity_type, properties=properties
            )
            row_entity_ids[entity_mapping.entity_type] = entity_id
        for relationship_mapping in feed.relationships:
            source_id = row_entity_ids.get(relationship_mapping.source_entity_type)
            target_id = row_entity_ids.get(relationship_mapping.target_entity_type)
            if source_id is None or target_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' relationship "
                    f"'{relationship_mapping.relationship_type}' references an entity "
                    f"type not mapped by record '{record.record_id}'."
                )
            relationship_id = (
                f"{relationship_mapping.relationship_type}:{source_id}->{target_id}"
            )
            relationships[relationship_id] = Relationship(
                id=relationship_id,
                type=relationship_mapping.relationship_type,
                source_id=source_id,
                target_id=target_id,
            )
    return MappedGraph(
        entities=list(entities.values()),
        relationships=list(relationships.values()),
    )


def map_observations(
    feed: RecordFeedConfig, records: list[RawRecord]
) -> list[MonitoringObservation]:
    """Derive scored observations from a record batch.

    Each observation's ``observed_at`` is the source record's ``ingested_at``,
    keeping observation writes idempotent across handler retries.
    """

    id_field_by_entity_type = {
        entity_mapping.entity_type: entity_mapping.id_field
        for entity_mapping in feed.entities
    }
    observations: list[MonitoringObservation] = []
    for record in records:
        row = record.payload
        for observation_mapping in feed.observations:
            score_value = row.get(observation_mapping.score_field)
            if score_value is None:
                continue
            id_field = id_field_by_entity_type.get(observation_mapping.entity_type)
            if id_field is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' observation references entity type "
                    f"'{observation_mapping.entity_type}' not mapped by the feed."
                )
            raw_id = row.get(id_field)
            if raw_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' record '{record.record_id}' is missing "
                    f"observation id field '{id_field}'."
                )
            observations.append(
                MonitoringObservation(
                    entity_id=_entity_id(observation_mapping.entity_type, raw_id),
                    entity_type=observation_mapping.entity_type,
                    metric_name=observation_mapping.metric_name,
                    score=_as_float(score_value),
                    observed_at=record.ingested_at,
                    rationale=observation_mapping.rationale,
                )
            )
    return observations


__all__ = [
    "MappedGraph",
    "map_batch",
    "map_observations",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/records/test_feed_mapper.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Type-check**

Run: `pyright records tests/records/test_feed_mapper.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/records/mappers backend/tests/records/test_feed_mapper.py
git commit -m "feat: add config-driven record feed mapper"
```

---

## Task 11: `RecordsService` and module exports

**Files:**
- Create: `backend/records/protocols.py`
- Create: `backend/records/service.py`
- Modify: `backend/records/__init__.py`
- Create: `backend/tests/records/test_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/records/test_service.py`:

```python
"""Tests for RecordsService.register_records."""

from __future__ import annotations

import pytest

from config.schema import RecordEntityMapping, RecordFeedConfig, RecordsConfig
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError, RecordValidationError
from records.service import create_records_service
from records.service_models import RecordSubmission
from shared.types import PropertyDefinition, PropertyType


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                record_schema={
                    "claim_id": PropertyDefinition(
                        type=PropertyType.STRING, display="Claim ID", required=True
                    ),
                    "amount": PropertyDefinition(
                        type=PropertyType.DECIMAL, display="Amount", required=True
                    ),
                },
                entities=[RecordEntityMapping(entity_type="claim", id_field="claim_id")],
            )
        ]
    )


def test_register_records_persists_publishes_and_receipts() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
            source_type="file_upload",
            source_ref="claims.csv",
        ),
    )

    assert receipt.accepted_count == 2
    assert receipt.record_type == "claim_record"
    persisted = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=receipt.correlation_id
    )
    assert {record.record_id for record in persisted} == {"c1", "c2"}
    assert persisted[0].payload["amount"] == 10.0  # coerced from "10"

    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1
    assert published[0].correlation_id == receipt.correlation_id
    assert published[0].record_count == 2


def test_register_records_rejects_unknown_feed() -> None:
    service = create_records_service(
        InMemoryRawRecordStore(), event_bus=InMemoryEventBus(), records_config=_records_config()
    )
    with pytest.raises(RecordFeedNotFoundError):
        service.register_records(
            "kb-1",
            RecordSubmission(feed_name="ghost_feed", rows=[{}], source_type="api_push"),
        )


def test_register_records_rejects_invalid_rows() -> None:
    service = create_records_service(
        InMemoryRawRecordStore(), event_bus=InMemoryEventBus(), records_config=_records_config()
    )
    with pytest.raises(RecordValidationError):
        service.register_records(
            "kb-1",
            RecordSubmission(
                feed_name="claims_feed",
                rows=[{"claim_id": "c1"}],  # missing required "amount"
                source_type="api_push",
            ),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/records/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'records.service'`.

- [ ] **Step 3: Write `records/protocols.py`**

Create `backend/records/protocols.py`:

```python
"""Service-level protocols for the records module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from records.service_models import RecordIngestReceipt, RecordSubmission


@runtime_checkable
class RecordsServiceProtocol(Protocol):
    """Service boundary for structured-record ingestion consumed by the API."""

    def register_records(
        self, knowledge_base_id: str, submission: RecordSubmission
    ) -> RecordIngestReceipt: ...


__all__ = [
    "RecordsServiceProtocol",
]
```

- [ ] **Step 4: Write `records/service.py`**

Create `backend/records/service.py`:

```python
"""Service entry point for structured-record registration."""

from __future__ import annotations

from config.schema import RecordFeedConfig, RecordsConfig
from events.protocols import EventBus
from events.types import RecordsIngestedEvent
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError, RecordValidationError
from records.models import RawRecord, content_hash_for
from records.service_models import RecordIngestReceipt, RecordSubmission
from records.validation import validate_rows
from shared.utils import generate_id, utc_now


class RecordsService:
    """Validate, persist, and announce structured-record submissions."""

    def __init__(
        self,
        store: RawRecordStore,
        *,
        event_bus: EventBus,
        records_config: RecordsConfig,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._records_config = records_config

    def register_records(
        self, knowledge_base_id: str, submission: RecordSubmission
    ) -> RecordIngestReceipt:
        feed = self._resolve_feed(submission.feed_name)
        coerced_rows = validate_rows(feed, submission.rows)

        correlation_id = generate_id()
        ingested_at = utc_now()
        raw_records: list[RawRecord] = []
        for row in coerced_rows:
            raw_id = row.get(feed.id_field)
            if raw_id is None:
                raise RecordValidationError(
                    f"Feed '{feed.name}' record is missing id field '{feed.id_field}'."
                )
            raw_records.append(
                RawRecord(
                    knowledge_base_id=knowledge_base_id,
                    record_type=feed.record_type,
                    record_id=str(raw_id),
                    payload=row,
                    source_type=submission.source_type,
                    source_ref=submission.source_ref,
                    correlation_id=correlation_id,
                    content_hash=content_hash_for(row),
                    ingested_at=ingested_at,
                )
            )

        accepted = self._store.persist(raw_records)
        self._event_bus.publish(
            RecordsIngestedEvent(
                correlation_id=correlation_id,
                knowledge_base_id=knowledge_base_id,
                feed_name=feed.name,
                record_type=feed.record_type,
                record_count=accepted,
            )
        )
        return RecordIngestReceipt(
            knowledge_base_id=knowledge_base_id,
            feed_name=feed.name,
            record_type=feed.record_type,
            correlation_id=correlation_id,
            accepted_count=accepted,
        )

    def _resolve_feed(self, feed_name: str) -> RecordFeedConfig:
        for feed in self._records_config.feeds:
            if feed.name == feed_name:
                return feed
        raise RecordFeedNotFoundError(feed_name)


def create_records_service(
    store: RawRecordStore,
    *,
    event_bus: EventBus,
    records_config: RecordsConfig,
) -> RecordsService:
    """Create the default records service."""

    return RecordsService(store, event_bus=event_bus, records_config=records_config)


__all__ = [
    "RecordsService",
    "create_records_service",
]
```

- [ ] **Step 5: Populate `records/__init__.py` with public exports**

Replace the contents of `backend/records/__init__.py` with:

```python
"""Structured / tabular record ingestion module."""

from __future__ import annotations

from records.exceptions import (
    RecordFeedNotFoundError,
    RecordMappingError,
    RecordPersistenceError,
    RecordValidationError,
    RecordsError,
)
from records.models import RawRecord, RecordBatch, content_hash_for
from records.protocols import RecordsServiceProtocol
from records.service import RecordsService, create_records_service
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = [
    "RawRecord",
    "RecordBatch",
    "RecordFeedNotFoundError",
    "RecordIngestReceipt",
    "RecordMappingError",
    "RecordPersistenceError",
    "RecordSubmission",
    "RecordValidationError",
    "RecordsError",
    "RecordsService",
    "RecordsServiceProtocol",
    "content_hash_for",
    "create_records_service",
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/records/test_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Type-check and run the whole records suite**

Run: `pyright records tests/records`
Expected: 0 errors.

Run: `pytest tests/records -m "not integration"`
Expected: PASS — all records unit tests green.

- [ ] **Step 8: Commit**

```bash
git add backend/records/protocols.py backend/records/service.py backend/records/__init__.py backend/tests/records/test_service.py
git commit -m "feat: add RecordsService for structured-record registration"
```

---

## Task 12: Monitoring observation writer (write-side Postgres adapter)

**Files:**
- Modify: `backend/monitoring/adapters/protocols.py`
- Create: `backend/monitoring/adapters/postgres.py`
- Modify: `backend/monitoring/adapters/in_memory.py`
- Modify: `backend/monitoring/adapters/__init__.py`
- Modify: `backend/monitoring/__init__.py`
- Create: `backend/tests/monitoring/test_observation_writer.py`
- Create: `backend/tests/monitoring/test_postgres_observation_store.py`

- [ ] **Step 1: Write the failing unit test**

Create `backend/tests/monitoring/test_observation_writer.py`:

```python
"""Tests for the in-memory observation writer."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationWriter
from monitoring.adapters.protocols import ObservationWriter
from monitoring.models import MonitoringBatch, MonitoringObservation


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-1",
        batch_id="corr-1",
        observations=[
            MonitoringObservation(
                entity_id="claim:c1",
                entity_type="claim",
                metric_name="claim_anomaly",
                score=0.8,
                rationale="test",
            )
        ],
    )


def test_in_memory_writer_satisfies_protocol() -> None:
    writer: ObservationWriter = InMemoryObservationWriter()
    assert writer.write_observations(_batch(), correlation_id="corr-1") == 1


def test_in_memory_writer_records_written_batches() -> None:
    writer = InMemoryObservationWriter()
    writer.write_observations(_batch(), correlation_id="corr-1")
    assert len(writer.written) == 1
    batch, correlation_id = writer.written[0]
    assert batch.batch_id == "corr-1"
    assert correlation_id == "corr-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/monitoring/test_observation_writer.py -v`
Expected: FAIL — `ImportError: cannot import name 'InMemoryObservationWriter'`.

- [ ] **Step 3: Add the `ObservationWriter` protocol**

In `backend/monitoring/adapters/protocols.py`, add the import and the protocol. Change the top imports to:

```python
from monitoring.models import MonitoringBatch
from shared.types import Alert
```

Then add this protocol after `ObservationSourceProtocol` (before `AlertRepositoryProtocol`):

```python
@runtime_checkable
class ObservationWriter(Protocol):
    """Persist scored observations to the analytics-facing observations store.

    The read-side ``ObservationSourceProtocol`` adapter is added in Plan C;
    this write-side protocol is what the worker's Flow 1 handler depends on.
    """

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        """Persist a batch's observations idempotently; return the row count written."""
        ...
```

Then add `"ObservationWriter"` to `__all__`:

```python
__all__ = [
    "AlertRepositoryProtocol",
    "ObservationSourceProtocol",
    "ObservationWriter",
]
```

- [ ] **Step 4: Add `InMemoryObservationWriter`**

In `backend/monitoring/adapters/in_memory.py`, update the `__all__` line and append the new class:

```python
__all__ = [
    "InMemoryAlertRepository",
    "InMemoryObservationSource",
    "InMemoryObservationWriter",
]
```

Append at the end of the file:

```python
class InMemoryObservationWriter:
    """An ``ObservationWriter`` that records written batches in memory."""

    def __init__(self) -> None:
        self.written: list[tuple[MonitoringBatch, str]] = []

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        self.written.append((batch, correlation_id))
        return len(batch.observations)
```

The file's existing import line is `from monitoring.models import MonitoringBatch` — confirm it is present at the top; it already imports `MonitoringBatch`, so no import change is needed.

- [ ] **Step 5: Run the unit test to verify it passes**

Run: `pytest tests/monitoring/test_observation_writer.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Write the failing integration test**

Create `backend/tests/monitoring/test_postgres_observation_store.py`:

```python
"""Integration tests for the Postgres observation writer."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresObservationStore
from monitoring.models import MonitoringBatch, MonitoringObservation

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping observation store integration test.")
    return url


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-obs-test",
        batch_id="corr-obs-1",
        observations=[
            MonitoringObservation(
                entity_id="claim:c1",
                entity_type="claim",
                metric_name="claim_anomaly",
                score=0.8,
                rationale="integration test",
            )
        ],
    )


def test_write_observations_is_idempotent(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresObservationStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()

        assert store.write_observations(_batch(), correlation_id="corr-obs-1") == 1
        # Same observation (same PK incl. observed_at) writes nothing on retry.
        assert store.write_observations(_batch(), correlation_id="corr-obs-1") == 0

        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            ).fetchone()
            assert rows is not None and rows[0] == 1
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()
        provider.close()
```

> **Note:** the `_batch()` helper builds a `MonitoringObservation` without an explicit `observed_at`, so each call defaults to a fresh `utc_now()`. The test re-uses one `_batch()` value per call — call it once and reuse it so both writes carry the same `observed_at` and exercise the `ON CONFLICT` path. Adjust the test to build the batch once: `batch = _batch()` then pass `batch` to both `write_observations` calls.

Apply that adjustment now — rewrite `test_write_observations_is_idempotent` to build the batch once:

```python
def test_write_observations_is_idempotent(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresObservationStore(provider)
    batch = _batch()
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()

        assert store.write_observations(batch, correlation_id="corr-obs-1") == 1
        assert store.write_observations(batch, correlation_id="corr-obs-1") == 0

        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            ).fetchone()
            assert rows is not None and rows[0] == 1
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()
        provider.close()
```

- [ ] **Step 7: Run the integration test to verify it fails**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/monitoring/test_postgres_observation_store.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'monitoring.adapters.postgres'`.

- [ ] **Step 8: Write `monitoring/adapters/postgres.py`**

Create `backend/monitoring/adapters/postgres.py`:

```python
"""Postgres-backed observation writer (write side of the observations table).

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol. The
read-side ``ObservationSourceProtocol`` adapter against the same table is
added in Plan C.
"""

from __future__ import annotations

from database.protocols import ConnectionProvider
from monitoring.exceptions import MonitoringSourceError
from monitoring.models import MonitoringBatch

_INSERT_SQL = """
    INSERT INTO observations (
        knowledge_base_id, entity_id, entity_type, metric_name,
        score, observed_at, rationale, evidence_pack_id, batch_id, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at) DO NOTHING
"""


class PostgresObservationStore:
    """An ``ObservationWriter`` backed by the ``observations`` hypertable."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        if not batch.observations:
            return 0
        written = 0
        try:
            with self._provider.connection() as conn:
                for observation in batch.observations:
                    cursor = conn.execute(
                        _INSERT_SQL,
                        (
                            batch.knowledge_base_id,
                            observation.entity_id,
                            observation.entity_type,
                            observation.metric_name,
                            observation.score,
                            observation.observed_at,
                            observation.rationale,
                            observation.evidence_pack_id,
                            batch.batch_id,
                            correlation_id,
                        ),
                    )
                    written += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise MonitoringSourceError("Failed to write observations.") from exc
        return written


__all__ = [
    "PostgresObservationStore",
]
```

- [ ] **Step 9: Update the monitoring adapter package exports**

Replace the contents of `backend/monitoring/adapters/__init__.py` with:

```python
"""Monitoring adapters."""

from __future__ import annotations

from monitoring.adapters.in_memory import (
    InMemoryAlertRepository,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.protocols import ObservationSourceProtocol, ObservationWriter

__all__ = [
    "InMemoryAlertRepository",
    "InMemoryObservationSource",
    "InMemoryObservationWriter",
    "ObservationSourceProtocol",
    "ObservationWriter",
]
```

In `backend/monitoring/__init__.py`, add `InMemoryObservationWriter` and `ObservationWriter` to the adapter imports and to `__all__`. Change the adapter import block to:

```python
from monitoring.adapters.in_memory import (
    InMemoryAlertRepository,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.protocols import ObservationSourceProtocol, ObservationWriter
```

Then add `"InMemoryObservationWriter"` and `"ObservationWriter"` to the `__all__` list (alongside the other adapter names).

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/monitoring/test_observation_writer.py -v`
Expected: PASS (2 tests).

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/monitoring/test_postgres_observation_store.py -v -m integration`
Expected: PASS (1 test).

- [ ] **Step 11: Type-check and check monitoring regressions**

Run: `pyright monitoring tests/monitoring/test_postgres_observation_store.py`
Expected: 0 errors.

Run: `pytest tests/monitoring -m "not integration"`
Expected: PASS — existing monitoring tests still green.

- [ ] **Step 12: Commit**

```bash
git add backend/monitoring/adapters/protocols.py backend/monitoring/adapters/postgres.py backend/monitoring/adapters/in_memory.py backend/monitoring/adapters/__init__.py backend/monitoring/__init__.py backend/tests/monitoring/test_observation_writer.py backend/tests/monitoring/test_postgres_observation_store.py
git commit -m "feat: add observation writer protocol and Postgres write adapter"
```

---

## Task 13: `GraphService.upsert_records_graph`

**Files:**
- Modify: `backend/graph/service.py`
- Create: `backend/tests/graph/test_records_graph.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/graph/test_records_graph.py`:

```python
"""Tests for GraphService.upsert_records_graph (structured-records path)."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def test_upsert_records_graph_persists_entities_and_relationships() -> None:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    entities = [
        Entity(id="claim:c1", type="claim", properties={"amount": 10.0}),
        Entity(id="provider:p1", type="provider", properties={}),
    ]
    relationships = [
        Relationship(
            id="submitted_by:claim:c1->provider:p1",
            type="submitted_by",
            source_id="claim:c1",
            target_id="provider:p1",
        )
    ]
    stored_entities, stored_relationships = service.upsert_records_graph(
        "kb-1", entities, relationships
    )
    assert {entity.id for entity in stored_entities} == {"claim:c1", "provider:p1"}
    assert [relationship.id for relationship in stored_relationships] == [
        "submitted_by:claim:c1->provider:p1"
    ]
    assert service.get_entity("kb-1", "claim:c1") is not None


def test_upsert_records_graph_publishes_no_graph_updated_event() -> None:
    bus = InMemoryEventBus()
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=bus,
    )
    service.upsert_records_graph(
        "kb-1", [Entity(id="claim:c1", type="claim", properties={})], []
    )
    assert not any(isinstance(e, GraphUpdatedEvent) for e in bus.published_events)


def test_upsert_records_graph_is_idempotent() -> None:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    entity = Entity(id="claim:c1", type="claim", properties={})
    service.upsert_records_graph("kb-1", [entity], [])
    service.upsert_records_graph("kb-1", [entity], [])
    assert service.compute_metrics("kb-1").entity_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_records_graph.py -v`
Expected: FAIL — `AttributeError: 'GraphService' object has no attribute 'upsert_records_graph'`.

- [ ] **Step 3: Add the method to `GraphService`**

In `backend/graph/service.py`, add this method to the `GraphService` class immediately after `update_entity_properties` (after line ~183, before `query_neighborhood`):

```python
    def upsert_records_graph(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> tuple[list[Entity], list[Relationship]]:
        """Upsert entities and relationships from a structured-records feed.

        Unlike :meth:`upsert_task`, this writes no document-pipeline artifacts
        and publishes no ``GraphUpdatedEvent`` — structured records have no
        parsed-document lineage. Both writes are idempotent upserts, so the
        worker's Flow 1 handler is safely replayable.
        """

        try:
            stored_entities: list[Entity] = []
            for entity_batch in self._chunk_items(entities):
                with self._repository.transaction(knowledge_base_id):
                    stored_entities.extend(
                        self._repository.upsert_entities(knowledge_base_id, entity_batch)
                    )
            stored_relationships: list[Relationship] = []
            for relationship_batch in self._chunk_items(relationships):
                with self._repository.transaction(knowledge_base_id):
                    stored_relationships.extend(
                        self._repository.upsert_relationships(
                            knowledge_base_id, relationship_batch
                        )
                    )
        except BatchUpsertError:
            raise
        except Exception as exc:
            raise GraphPersistenceError(
                "Failed to upsert structured-records graph objects."
            ) from exc
        return stored_entities, stored_relationships
```

`BatchUpsertError` and `GraphPersistenceError` are already imported at the top of `graph/service.py`; `_chunk_items` is an existing private method on the class. No new imports are needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_records_graph.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Type-check and check graph regressions**

Run: `pyright graph tests/graph/test_records_graph.py`
Expected: 0 errors.

Run: `pytest tests/graph -m "not integration"`
Expected: PASS — existing graph tests still green.

- [ ] **Step 6: Commit**

```bash
git add backend/graph/service.py backend/tests/graph/test_records_graph.py
git commit -m "feat: add GraphService.upsert_records_graph for structured records"
```

---

## Task 14: Worker handler `handle_records_ingested` (Flow 1)

**Files:**
- Modify: `backend/agent/coordinator.py`
- Create: `backend/tests/agent/test_records_handler.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/agent/test_records_handler.py`:

```python
"""Tests for the Flow 1 worker handler handle_records_ingested."""

from __future__ import annotations

import pytest

from agent.coordinator import handle_records_ingested
from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordRelationshipMapping,
    RecordsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.models import RawRecord, content_hash_for
from storage.adapters.in_memory import InMemoryObjectStore


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                entities=[
                    RecordEntityMapping(
                        entity_type="claim",
                        id_field="claim_id",
                        property_fields={"amount": "billed_amount"},
                    ),
                    RecordEntityMapping(entity_type="provider", id_field="provider_npi"),
                ],
                relationships=[
                    RecordRelationshipMapping(
                        relationship_type="submitted_by",
                        source_entity_type="claim",
                        target_entity_type="provider",
                    )
                ],
                observations=[
                    RecordObservationMapping(
                        metric_name="claim_anomaly",
                        entity_type="claim",
                        score_field="anomaly_score",
                        rationale="feed score",
                    )
                ],
            )
        ]
    )


def _seed_store(store: InMemoryRawRecordStore, correlation_id: str) -> None:
    payload: dict[str, object] = {
        "claim_id": "c1",
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "anomaly_score": 0.8,
    }
    store.persist(
        [
            RawRecord(
                knowledge_base_id="kb-1",
                record_type="claim_record",
                record_id="c1",
                payload=payload,
                source_type="file_upload",
                source_ref="claims.csv",
                correlation_id=correlation_id,
                content_hash=content_hash_for(payload),
            )
        ]
    )


def _graph_service() -> object:
    return create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def test_handler_fans_records_out_to_graph_and_observations() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store, "corr-1")
    graph_service = _graph_service()
    writer = InMemoryObservationWriter()

    processed = handle_records_ingested(
        RecordsIngestedEvent(
            correlation_id="corr-1",
            knowledge_base_id="kb-1",
            feed_name="claims_feed",
            record_type="claim_record",
            record_count=1,
        ),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=graph_service,  # type: ignore[arg-type]
        observation_writer=writer,
    )

    assert processed == 1
    assert graph_service.get_entity("kb-1", "claim:c1") is not None  # type: ignore[attr-defined]
    assert len(writer.written) == 1
    batch, correlation_id = writer.written[0]
    assert correlation_id == "corr-1"
    assert batch.observations[0].metric_name == "claim_anomaly"


def test_handler_raises_for_unknown_feed() -> None:
    with pytest.raises(RecordFeedNotFoundError):
        handle_records_ingested(
            RecordsIngestedEvent(
                correlation_id="corr-1",
                knowledge_base_id="kb-1",
                feed_name="ghost_feed",
                record_type="claim_record",
                record_count=0,
            ),
            records_config=_records_config(),
            raw_record_store=InMemoryRawRecordStore(),
            graph_service=_graph_service(),  # type: ignore[arg-type]
            observation_writer=InMemoryObservationWriter(),
        )


def test_handler_returns_zero_when_no_records_found() -> None:
    processed = handle_records_ingested(
        RecordsIngestedEvent(
            correlation_id="missing-corr",
            knowledge_base_id="kb-1",
            feed_name="claims_feed",
            record_type="claim_record",
            record_count=0,
        ),
        records_config=_records_config(),
        raw_record_store=InMemoryRawRecordStore(),
        graph_service=_graph_service(),  # type: ignore[arg-type]
        observation_writer=InMemoryObservationWriter(),
    )
    assert processed == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_records_handler.py -v`
Expected: FAIL — `ImportError: cannot import name 'handle_records_ingested'`.

- [ ] **Step 3: Add imports to `agent/coordinator.py`**

In `backend/agent/coordinator.py`, add to the `config.schema` import block (after `ObjectStoreConfig`):

```python
from config.schema import (
    DomainConfig,
    EmbeddingsConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
```

Add a new import block after the `database`-free imports — place it after the `from config.schema import (...)` block:

```python
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
```

Add `RecordsIngestedEvent` to the `events.types` import block (alphabetically, near the other event types):

```python
    RecordsIngestedEvent,
```

Add to the `monitoring` import block (after the existing monitoring imports):

```python
from monitoring.adapters.in_memory import (
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.postgres import PostgresObservationStore
from monitoring.adapters.protocols import ObservationSourceProtocol, ObservationWriter
from monitoring.models import MonitoringBatch
```

> Replace the existing single-line `from monitoring.adapters.in_memory import InMemoryObservationSource` and `from monitoring.adapters.protocols import ObservationSourceProtocol` imports with the grouped forms above.

Add a new `records` import block after the `monitoring` imports:

```python
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.mappers.feed_mapper import map_batch, map_observations
```

- [ ] **Step 4: Extend `__all__`**

In the `__all__` list at the top of `coordinator.py`, add these entries in alphabetical position: `"build_connection_provider"`, `"build_observation_writer"`, `"build_raw_record_store"`, `"handle_records_ingested"`.

- [ ] **Step 5: Add fields to `WorkerDependencies`**

In the `WorkerDependencies` dataclass, add three fields after `monitoring_service`:

```python
    monitoring_service: MonitoringService
    records_config: RecordsConfig
    raw_record_store: RawRecordStore
    observation_writer: ObservationWriter
    event_settings: EventBusSettings
    workflow_run_store: WorkflowRunStoreProtocol
    workflow_tracker: WorkflowEventTracker
```

- [ ] **Step 6: Add the builder functions**

In `coordinator.py`, add these functions immediately after `build_monitoring_observation_source` (before `_section_is_default`):

```python
def build_connection_provider(config: DomainConfig) -> ConnectionProvider | None:
    """Return a database connection provider, or None for the in-memory backend."""

    return create_connection_provider(config.database or DatabaseConfig())


def build_raw_record_store(
    provider: ConnectionProvider | None,
) -> RawRecordStore:
    """Select a raw record store: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryRawRecordStore()
    return PostgresRawRecordStore(provider)


def build_observation_writer(
    provider: ConnectionProvider | None,
) -> ObservationWriter:
    """Select an observation writer: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryObservationWriter()
    return PostgresObservationStore(provider)
```

The `DatabaseConfig` name is needed here — add `DatabaseConfig` to the `config.schema` import block created in Step 3 (so the block imports `DatabaseConfig`, `DomainConfig`, `EmbeddingsConfig`, `GraphDbConfig`, `LlmConfig`, `ObjectStoreConfig`, `RecordsConfig`, `VectorStoreConfig`).

- [ ] **Step 7: Wire the new dependencies into `build_worker_dependencies`**

In `build_worker_dependencies`, after the `monitoring_service = create_monitoring_service(...)` block and before the `return WorkerDependencies(...)`, add:

```python
    connection_provider = build_connection_provider(config)
    raw_record_store = build_raw_record_store(connection_provider)
    observation_writer = build_observation_writer(connection_provider)
    records_config = config.records or RecordsConfig()
```

Then add the three fields to the `WorkerDependencies(...)` constructor call (after `monitoring_service=monitoring_service,`):

```python
        monitoring_service=monitoring_service,
        records_config=records_config,
        raw_record_store=raw_record_store,
        observation_writer=observation_writer,
        event_settings=event_settings,
```

- [ ] **Step 8: Add the `handle_records_ingested` handler**

In `coordinator.py`, add this function immediately after `handle_risk_scored` (before `_publish_analysis_failed`):

```python
def handle_records_ingested(
    event: RecordsIngestedEvent,
    *,
    records_config: RecordsConfig,
    raw_record_store: RawRecordStore,
    graph_service: GraphService,
    observation_writer: ObservationWriter,
) -> int:
    """Flow 1 — fan a structured-records batch out to the graph and observations.

    A single handler: map rows to graph entities/relationships and upsert them,
    then derive observations and persist them. Every write is idempotent so the
    worker's retry/DLQ wrapper can safely re-run this handler.
    """

    feed = _resolve_records_feed(records_config, event.feed_name)
    records = raw_record_store.load_batch(
        knowledge_base_id=event.knowledge_base_id,
        correlation_id=event.correlation_id,
    )
    if not records:
        logger.info(
            "No raw records found for feed=%s kb=%s correlation=%s",
            event.feed_name,
            event.knowledge_base_id,
            event.correlation_id,
        )
        return 0

    mapped = map_batch(feed, records)
    graph_service.upsert_records_graph(
        event.knowledge_base_id, mapped.entities, mapped.relationships
    )

    observations = map_observations(feed, records)
    if observations:
        observation_writer.write_observations(
            MonitoringBatch(
                knowledge_base_id=event.knowledge_base_id,
                batch_id=event.correlation_id,
                observations=observations,
            ),
            correlation_id=event.correlation_id,
        )
    return len(records)


def _resolve_records_feed(
    records_config: RecordsConfig, feed_name: str
) -> RecordFeedConfig:
    for feed in records_config.feeds:
        if feed.name == feed_name:
            return feed
    raise RecordFeedNotFoundError(feed_name)
```

This references `RecordFeedConfig` — add it to the `config.schema` import block (so it imports `DatabaseConfig`, `DomainConfig`, `EmbeddingsConfig`, `GraphDbConfig`, `LlmConfig`, `ObjectStoreConfig`, `RecordFeedConfig`, `RecordsConfig`, `VectorStoreConfig`).

- [ ] **Step 9: Run the handler test to verify it passes**

Run: `pytest tests/agent/test_records_handler.py -v`
Expected: PASS (3 tests).

- [ ] **Step 10: Wire the handler into event dispatch**

In `_dispatch_event`, add three keyword parameters to the signature (after `monitoring_service: MonitoringService | None`):

```python
    monitoring_service: MonitoringService | None,
    records_config: RecordsConfig | None,
    raw_record_store: RawRecordStore | None,
    observation_writer: ObservationWriter | None,
) -> int:
```

Then add this dispatch branch immediately before the final `return 0`:

```python
    if isinstance(event, RecordsIngestedEvent):
        if (
            records_config is None
            or raw_record_store is None
            or observation_writer is None
        ):
            logger.warning(
                "RecordsIngestedEvent received but records dependencies are not wired."
            )
            return 0
        return handle_records_ingested(
            event,
            records_config=records_config,
            raw_record_store=raw_record_store,
            graph_service=graph_service,
            observation_writer=observation_writer,
        )
    return 0
```

- [ ] **Step 11: Thread the dependencies through `handle_event`**

In `handle_event`, add three keyword parameters after `monitoring_service`:

```python
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    workflow_tracker: WorkflowEventTracker | None = None,
) -> int:
```

In the `_dispatch_event(...)` call inside `handle_event`, pass them through (after `monitoring_service=monitoring_service,`):

```python
            monitoring_service=monitoring_service,
            records_config=records_config,
            raw_record_store=raw_record_store,
            observation_writer=observation_writer,
        )
```

- [ ] **Step 12: Thread the dependencies through `drain_ingestion_events`**

In `drain_ingestion_events`, add three keyword parameters after `monitoring_service`:

```python
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    consumer_group: str,
```

Add `"records.ingested"` to the `event_types` list:

```python
    event_types = [
        "documents.uploaded",
        "documents.parsed",
        "documents.chunked",
        "entities.extracted",
        "entities.validated",
        "graph.updated",
        "embeddings.complete",
        "vectors.indexed",
        "risk.scored",
        "records.ingested",
    ]
```

In the `_run_handler` inner function, pass the new arguments to `handle_event` (after `monitoring_service=monitoring_service,`):

```python
                monitoring_service=monitoring_service,
                records_config=records_config,
                raw_record_store=raw_record_store,
                observation_writer=observation_writer,
                workflow_tracker=workflow_tracker,
            )
```

- [ ] **Step 13: Pass the dependencies from `run_worker`**

In `run_worker`, in the `drain_ingestion_events(...)` call, add the three arguments after `monitoring_service=deps.monitoring_service,`:

```python
                monitoring_service=deps.monitoring_service,
                records_config=deps.records_config,
                raw_record_store=deps.raw_record_store,
                observation_writer=deps.observation_writer,
                consumer_group=deps.event_settings.consumer_group,
```

- [ ] **Step 14: Type-check and run the agent suite**

Run: `pyright agent tests/agent/test_records_handler.py`
Expected: 0 errors.

Run: `pytest tests/agent -m "not integration"`
Expected: PASS — existing agent/coordinator tests still green (the new optional parameters default to `None`, so existing callers are unaffected).

- [ ] **Step 15: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_records_handler.py
git commit -m "feat: add Flow 1 worker handler for structured records"
```

---

## Task 15: Records API router and dependency wiring

**Files:**
- Create: `backend/api/routers/records.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Create: `backend/tests/api/test_records_router.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_records_router.py`:

```python
"""Tests for the records ingestion API router."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv(
        "CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml"
    )
    return TestClient(create_app())


def test_push_records_returns_a_receipt(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c1",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted_count"] == 1
    assert body["record_type"] == "claim_record"


def test_push_records_rejects_unknown_feed(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={"feed_name": "ghost_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 404


def test_push_records_rejects_invalid_rows(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 422


def test_upload_csv_file_returns_a_receipt(client: TestClient) -> None:
    csv_body = (
        "claim_id,provider_npi,billed_amount,service_date,anomaly_score\n"
        "c1,1234567890,99.0,2026-01-15,0.8\n"
    )
    response = client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["accepted_count"] == 1


def test_upload_rejects_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 415
```

> This test relies on the `claims_feed` example feed added to `medicare_fraud.yaml` in Task 16. If Task 16 runs after this task in your execution order, expect these tests to fail on "unknown feed" until Task 16 lands; run this task's type-check and the no-feed cases first, then re-run after Task 16. (Subagent-driven execution: note this cross-task dependency to the reviewer.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_records_router.py -v`
Expected: FAIL — `404` for `/records/...` (router not registered).

- [ ] **Step 3: Add dependency wiring to `api/dependencies.py`**

In `backend/api/dependencies.py`, add `DatabaseConfig` and `RecordsConfig` to the `config.schema` import block:

```python
from config.schema import (
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphDbConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
```

Add these imports after the `monitoring` import block (near line 65):

```python
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.protocols import RecordsServiceProtocol
from records.service import create_records_service
```

Add `"get_connection_provider"`, `"get_raw_record_store"`, and `"get_records_service"` to the `__all__` list.

Add these provider functions immediately after `get_ingestion_service` (before the bottom-of-file import block):

```python
@lru_cache(maxsize=1)
def get_connection_provider() -> ConnectionProvider | None:
    """Return the database connection provider, or None for the in-memory backend."""
    config = get_domain_config()
    return create_connection_provider(config.database or DatabaseConfig())


@lru_cache(maxsize=1)
def get_raw_record_store() -> RawRecordStore:
    """Return the raw record store selected by the configured database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRawRecordStore()
    return PostgresRawRecordStore(provider)


def get_records_service(
    event_bus: EventBus = Depends(get_event_bus),
    store: RawRecordStore = Depends(get_raw_record_store),
    config: DomainConfig = Depends(get_domain_config),
) -> RecordsServiceProtocol:
    """Return the records ingestion service assembled from configured dependencies."""
    return create_records_service(
        store,
        event_bus=event_bus,
        records_config=config.records or RecordsConfig(),
    )
```

- [ ] **Step 4: Write the router**

Create `backend/api/routers/records.py`:

```python
"""Structured-record ingestion API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from api.dependencies import get_domain_config, get_records_service
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from records.adapters.sources.api_push_source import ApiPushSource
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordFeedNotFoundError, RecordsError
from records.protocols import RecordsServiceProtocol
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = ["RecordPushRequest", "router"]

router = APIRouter(prefix="/records", tags=["records"])


class RecordPushRequest(BaseModel):
    """Request payload for the api-push records endpoint."""

    feed_name: str = Field(min_length=1)
    rows: list[dict[str, object]] = Field(min_length=1)


def _select_file_source(filename: str) -> CsvFileSource | JsonlFileSource:
    lowered = filename.lower()
    if lowered.endswith((".jsonl", ".json")):
        return JsonlFileSource()
    if lowered.endswith(".csv"):
        return CsvFileSource()
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported records file type: '{filename}'. Use .csv or .jsonl.",
    )


@router.post(
    "/{knowledge_base_id}/files",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecordIngestReceipt,
    dependencies=[Depends(require_role("analyst"))],
)
async def upload_record_file(
    knowledge_base_id: str,
    feed: str = Form(...),
    file: UploadFile = File(...),
    service: RecordsServiceProtocol = Depends(get_records_service),
    config: DomainConfig = Depends(get_domain_config),
) -> RecordIngestReceipt:
    """Ingest a CSV or JSONL upload into the named feed."""
    filename = file.filename or "upload"
    source = _select_file_source(filename)
    content = await file.read()

    validation = config.validation or ValidationConfig()
    if len(content) > validation.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the configured {validation.max_file_size_mb} MB limit.",
        )

    try:
        rows = source.read_rows(content)
        return service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=feed,
                rows=rows,
                source_type="file_upload",
                source_ref=filename,
            ),
        )
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/{knowledge_base_id}/push",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecordIngestReceipt,
    dependencies=[Depends(require_role("analyst"))],
)
async def push_records(
    knowledge_base_id: str,
    payload: RecordPushRequest,
    service: RecordsServiceProtocol = Depends(get_records_service),
) -> RecordIngestReceipt:
    """Ingest a JSON array of record rows into the named feed."""
    try:
        return service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=payload.feed_name,
                rows=payload.rows,
                source_type="api_push",
                source_ref=None,
            ),
        )
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
```

`ApiPushSource` is imported but the JSON body is already parsed by FastAPI, so the push endpoint passes `payload.rows` directly. Remove the `ApiPushSource` import line — it is unused and `ruff`/`pyright` will flag it. The final import block must not import `ApiPushSource`.

> **Correction to apply:** delete the line `from records.adapters.sources.api_push_source import ApiPushSource` from the router. The api-push endpoint receives already-structured rows from FastAPI's JSON parsing and does not need the source adapter.

- [ ] **Step 5: Register the router in `api/app.py`**

In `backend/api/app.py`, add the import after `from api.routers.rag import router as rag_router`:

```python
from api.routers.rag import router as rag_router
from api.routers.records import router as records_router
from api.routers.workflows import router as workflows_router
```

Add the registration in `create_app`, after `app.include_router(rag_router)`:

```python
    app.include_router(rag_router)
    app.include_router(records_router)
    app.include_router(workflows_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_records_router.py -v`
Expected: the unknown-feed (`404`), invalid-rows (`422`), and unsupported-file (`415`) cases PASS. The valid `claims_feed` cases (`202`) PASS only once Task 16 has added the `claims_feed` example to `medicare_fraud.yaml`. If Task 16 has not run yet, re-run this command after Task 16.

- [ ] **Step 7: Type-check and run an API regression check**

Run: `pyright api/routers/records.py api/dependencies.py api/app.py tests/api/test_records_router.py`
Expected: 0 errors.

Run: `pytest tests/api/test_policy_registry.py tests/api/test_production_guardrail.py -v`
Expected: PASS — the policy registry's `assert_complete` still passes, confirming both new routes declare `require_role`.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routers/records.py backend/api/dependencies.py backend/api/app.py backend/tests/api/test_records_router.py
git commit -m "feat: add records ingestion API router"
```

---

## Task 16: Example feed definitions in the default configs

**Files:**
- Modify: `backend/config/defaults/medicare_fraud.yaml`
- Modify: `backend/config/defaults/medicare_fraud_dev.yaml`
- Modify: `backend/config/defaults/food_supply_chain.yaml`

- [ ] **Step 1: Enable `structured_ingestion` and add the feed to `medicare_fraud.yaml`**

In `backend/config/defaults/medicare_fraud.yaml`, add `structured_ingestion: true` to the `capabilities` block:

```yaml
capabilities:
  timeseries: true
  gnn: true
  risk_scoring: true
  rag_chat: true
  explainability: true
  structured_ingestion: true
```

Add a new top-level `records` block immediately after the `ingestion:` block (before the commented-out `# graph:` block):

```yaml
records:
  feeds:
    - name: claims_feed
      record_type: claim_record
      source: file_upload
      id_field: claim_id
      record_schema:
        claim_id: { type: string, display: "Claim ID", required: true }
        provider_npi: { type: string, display: "Provider NPI", required: true, pattern: "^[0-9]{10}$" }
        billed_amount: { type: decimal, display: "Billed Amount", required: true, min_value: 0 }
        service_date: { type: date, display: "Date of Service", required: true }
        anomaly_score: { type: decimal, display: "Anomaly Score", required: true, min_value: 0, max_value: 1 }
      entities:
        - entity_type: claim
          id_field: claim_id
          property_fields:
            claim_id: claim_id
            amount: billed_amount
            service_date: service_date
        - entity_type: provider
          id_field: provider_npi
          property_fields:
            npi: provider_npi
      relationships:
        - relationship_type: submitted_by
          source_entity_type: claim
          target_entity_type: provider
      observations:
        - metric_name: claim_anomaly
          entity_type: claim
          score_field: anomaly_score
          rationale: "Anomaly score derived from the structured claims feed."
```

- [ ] **Step 2: Mirror the change in `medicare_fraud_dev.yaml`**

In `backend/config/defaults/medicare_fraud_dev.yaml`, add `structured_ingestion: true` to `capabilities` (same as Step 1) and add the identical `records:` block immediately after the `ingestion:` block (before the `graph:` block).

- [ ] **Step 3: Add a feed to `food_supply_chain.yaml`**

In `backend/config/defaults/food_supply_chain.yaml`, add `structured_ingestion: true` to `capabilities`:

```yaml
capabilities:
  timeseries: true
  gnn: false
  risk_scoring: true
  rag_chat: true
  explainability: false
  structured_ingestion: true
```

Add this `records` block immediately after the `ingestion:` block (before the commented-out `# graph:` block):

```yaml
records:
  feeds:
    - name: shipments_feed
      record_type: shipment_record
      source: file_upload
      id_field: tracking_id
      record_schema:
        tracking_id: { type: string, display: "Tracking ID", required: true }
        supplier_id: { type: string, display: "Supplier ID", required: true }
        ship_date: { type: date, display: "Ship Date", required: true }
        spoilage_score: { type: decimal, display: "Spoilage Score", required: true, min_value: 0, max_value: 1 }
      entities:
        - entity_type: shipment
          id_field: tracking_id
          property_fields:
            tracking_id: tracking_id
            ship_date: ship_date
        - entity_type: supplier
          id_field: supplier_id
          property_fields:
            supplier_id: supplier_id
      relationships:
        - relationship_type: shipped_by
          source_entity_type: shipment
          target_entity_type: supplier
      observations:
        - metric_name: shipment_spoilage
          entity_type: shipment
          score_field: spoilage_score
          rationale: "Spoilage score derived from the structured shipments feed."
```

- [ ] **Step 4: Verify all three configs load cleanly**

Run (from `backend/`):
```bash
for cfg in medicare_fraud medicare_fraud_dev food_supply_chain; do
  CHILI_CONFIG_PATH=config/defaults/$cfg.yaml CHILI_ENV=local \
    python -c "from config.loader import load_config; c = load_config(); print(c.domain.name, len((c.records.feeds if c.records else [])))"
done
```
Expected: prints `medicare_fraud 1`, `medicare_fraud 1`, `food_supply_chain 1` — each config loads and exposes one feed with no cross-validation errors.

- [ ] **Step 5: Re-run the records router test in full**

Run: `pytest tests/api/test_records_router.py -v`
Expected: PASS (5 tests) — the `claims_feed` example now exists, so the `202` cases pass.

- [ ] **Step 6: Commit**

```bash
git add backend/config/defaults/medicare_fraud.yaml backend/config/defaults/medicare_fraud_dev.yaml backend/config/defaults/food_supply_chain.yaml
git commit -m "feat: add example structured-ingestion feeds to default configs"
```

---

## Task 17: Documentation

**Files:**
- Create: `backend/records/README.md`
- Modify: `backend/README.md`
- Modify: `docs/architecture.md`
- Modify: `.github/copilot-instructions.md`

- [ ] **Step 1: Write the module README**

Create `backend/records/README.md`:

```markdown
# records — Structured / Tabular Ingestion

The structured-ingestion counterpart to `ingestion/` (documents). `records/`
accepts tabular feeds (CSV / JSONL file uploads, JSON api-push), validates
rows against a config-declared feed schema, lands canonical rows in the
`raw_records` Postgres table, and publishes a `RecordsIngestedEvent`. The
worker's Flow 1 handler then fans each batch out to the knowledge graph and
the `observations` table.

## Layout

- `models.py` — `RawRecord`, `RecordBatch`, `content_hash_for` (idempotency digest).
- `service_models.py` — `RecordSubmission`, `RecordIngestReceipt` (API boundary).
- `validation.py` — `coerce_row` / `validate_rows`: coerce string-encoded
  values and validate each row against the feed schema (reuses
  `shared.types.validate_entity` via a synthetic `EntityDefinition`).
- `mappers/feed_mapper.py` — config-driven `map_batch` (rows → entities +
  relationships) and `map_observations` (rows → scored observations).
- `service.py` — `RecordsService.register_records()`: validate → persist →
  publish `RecordsIngestedEvent`.
- `protocols.py` — `RecordsServiceProtocol` (service boundary).
- `adapters/protocols.py` — `RawRecordStore`, `RecordSourceProtocol`.
- `adapters/in_memory.py` — `InMemoryRawRecordStore` (local/test backend).
- `adapters/postgres.py` — `PostgresRawRecordStore` (`raw_records` table).
- `adapters/sources/` — `CsvFileSource`, `JsonlFileSource`, `ApiPushSource`.

`records/` communicates downstream only by publishing events — it never
imports `graph` or `analytics` internals.

## Feed configuration

Feeds are declared in `DomainConfig.records.feeds` — adding a domain's tabular
feeds requires config changes only, no code. Each `RecordFeedConfig` declares
a `record_schema`, `entities` (row → entity mappings), `relationships`, and
`observations`. See `config/defaults/medicare_fraud.yaml` for a worked example.

## Flow 1

```
records source (CSV/JSONL/api-push)
  → RecordsService.register_records()   # validate vs feed schema
  → RawRecordStore.persist()            # raw_records (canonical)
  → publish RecordsIngestedEvent
  → worker handle_records_ingested:
       1. map rows → entities/relationships → GraphService.upsert_records_graph()
       2. derive observations → observations table (PostgresObservationStore)
```

Every write is an idempotent upsert, so the worker's retry/DLQ wrapper can
re-run the handler safely.

## Commands

```bash
pip install -e ".[dev,postgres]"
pytest tests/records -m "not integration"   # fast unit tests
pytest tests/records -m integration           # needs a migrated TimescaleDB
```
```

- [ ] **Step 2: Update `backend/README.md`**

In `backend/README.md`, in the "What's functional" / module list, add an entry after the `database/` entry:

```markdown
- **`records/`** — structured/tabular ingestion (CSV/JSONL/api-push). Validates rows against config-declared feed schemas, lands canonical rows in `raw_records`, and publishes `RecordsIngestedEvent`. Parallel to `ingestion/` for documents.
```

In the "Target Module Structure" tree, add a `records/` line next to `ingestion/`:

```
├── records/         # structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing
```

If the README documents API routes, add the records routes: `POST /records/{kb}/files`, `POST /records/{kb}/push`.

- [ ] **Step 3: Update `docs/architecture.md`**

In `docs/architecture.md`:
- In the §5.1 package tree, add `records/` with the note `# structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing`.
- In the §5.2 module responsibility matrix, add a `records` row: Owns "Structured-record validation, raw_records persistence, feed mapping"; Depends on "`config`, `shared`, `events`, `database`, `monitoring.models`"; Forbidden "imports of `graph`/`analytics` internals — communicates downstream only by publishing `RecordsIngestedEvent`".
- In the data-flow section, add Flow 1: `records source → RecordsService → raw_records → RecordsIngestedEvent → worker handle_records_ingested → graph + observations`.
- Note that `GraphService.upsert_records_graph` is the records-specific graph entry point (no document artifacts, no `GraphUpdatedEvent`), and that the `observations` table now has a write-side adapter (`monitoring/adapters/postgres.py`).

- [ ] **Step 4: Update `.github/copilot-instructions.md`**

In `.github/copilot-instructions.md`, wherever the backend module list appears, add `records/` (structured/tabular ingestion, parallel to `ingestion/`). Keep the entry consistent with `CLAUDE.md`'s "Backend Module Map" — if the module map there omits `records/`, add it to `CLAUDE.md` too so the two stay consistent.

- [ ] **Step 5: Commit**

```bash
git add backend/records/README.md backend/README.md docs/architecture.md .github/copilot-instructions.md
git commit -m "docs: document the records structured-ingestion module"
```

---

## Final Verification

- [ ] **Step 1: Run the full backend unit suite**

Run (from `backend/`): `.venv/bin/pytest -m "not integration"`
Expected: all tests pass, including the new `tests/records`, `tests/agent/test_records_handler.py`, `tests/graph/test_records_graph.py`, `tests/events/test_records_event.py`, `tests/monitoring/test_observation_writer.py`, and `tests/api/test_records_router.py`. No regressions in existing suites.

- [ ] **Step 2: Run the integration suite against a migrated TimescaleDB**

Run (with the dev stack up and migrations applied):
```bash
docker compose -f docker-compose.dev.yaml up -d postgres
make migrate
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili .venv/bin/pytest -m integration \
  tests/records/test_postgres_store.py tests/monitoring/test_postgres_observation_store.py -v
```
Expected: both Postgres adapter integration tests pass.

- [ ] **Step 3: Confirm per-package coverage**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili .venv/bin/pytest --cov`
Expected: the `records` package reports ≥ 85% coverage (Postgres adapter lines are exercised by the integration tests included in this run).

- [ ] **Step 4: Type-check**

Run (from `backend/`): `.venv/bin/pyright`
Expected: 0 errors across all included paths (`records`, `tests/records`, `api/routers/records.py`, `tests/api/test_records_router.py`, `tests/monitoring/test_postgres_observation_store.py`, plus the modified `agent`, `graph`, `monitoring`, `events`, `config`).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check records tests/records api/routers/records.py`
Expected: 0 errors (import-order warnings may be ignored per `CLAUDE.md`).

- [ ] **Step 6: End-to-end smoke test against the running API**

Run (with the dev stack up, `medicare_fraud_dev.yaml` active so the `postgres` database backend is selected):
```bash
curl -s -X POST http://localhost:8000/records/kb-smoke/push \
  -H 'Content-Type: application/json' \
  -d '{"feed_name":"claims_feed","rows":[{"claim_id":"c1","provider_npi":"1234567890","billed_amount":99.0,"service_date":"2026-01-15","anomaly_score":0.8}]}'
```
Expected: HTTP 202 with a receipt (`accepted_count: 1`). After the worker processes the `records.ingested` event, confirm a `claim:c1` graph entity exists and an `observations` row was written:
```bash
docker compose -f docker-compose.dev.yaml exec postgres \
  psql -U chili -d chili -c "SELECT entity_id, metric_name, score FROM observations WHERE knowledge_base_id='kb-smoke';"
```
Expected: one row — `claim:c1 | claim_anomaly | 0.8`.

---

## Plan Self-Review Notes

- **Spec coverage:** §5.2 `records/` module layout → Tasks 4–11 (exceptions, models, service_models, store protocols/adapters, sources, validation, mappers, service); §6.1 `raw_records` / §6.2 `observations` — no migration needed, Plan A's `0001_persistence_baseline` already created both tables (Task 7 / Task 12 write to them); §7 config (`RecordFeedConfig`, `RecordsConfig`, `CapabilitiesConfig.structured_ingestion`) → Task 3; §8 Flow 1 + §8.1 `RecordsIngestedEvent` + §8.2 `handle_records_ingested` → Tasks 2, 14; domain-config example feeds → Task 16; §14 docs → Task 17.
- **Approved deviations from the literal spec:** (1) Flow 1 uses the new `GraphService.upsert_records_graph` (Task 13) instead of `upsert_task()` — `upsert_task` requires document-pipeline artifacts and emits a `GraphUpdatedEvent` the existing `handle_graph_updated` handler would crash on. (2) The observation writer is a write-only `PostgresObservationStore` behind a new `ObservationWriter` protocol (Task 12); Plan C extends `monitoring/adapters/postgres.py` with the read-side `ObservationSourceProtocol`. (3) A `records` API router is included (Task 15). All three were confirmed with the requester before this plan was written.
- **Deferred to Plan C (correctly out of scope):** per-consumer read-side Postgres adapters (`monitoring` `ObservationSourceProtocol`, `analytics/timeseries`, `analytics/risk`), the `analytics/metrics/` package, and Flows 2/3/4. Flow 1's graph writes deliberately publish no `GraphUpdatedEvent`, so triggering metric recompute from records is a Plan C concern.
- **Type consistency:** `RawRecordStore`, `RecordSourceProtocol`, `RawRecord`, `RecordBatch`, `RecordSubmission`, `RecordIngestReceipt`, `RecordFeedConfig`, `RecordsConfig`, `MappedGraph`, `ObservationWriter`, and `RecordsIngestedEvent` are each defined once and used unchanged downstream. `handle_records_ingested` keyword parameters (`records_config`, `raw_record_store`, `graph_service`, `observation_writer`) match the names threaded through `_dispatch_event` → `handle_event` → `drain_ingestion_events` and the `WorkerDependencies` fields. `register_records(knowledge_base_id, submission)` has one signature used by both API endpoints.
- **Idempotency:** `raw_records` inserts use `ON CONFLICT (pk) DO NOTHING` keyed on `content_hash`-bearing rows; graph upserts use deterministic `"{type}:{id}"` entity ids; `observations` inserts use `ON CONFLICT (kb, entity_id, metric_name, observed_at) DO NOTHING` with `observed_at` pinned to the source record's `ingested_at` — so the worker's existing retry/DLQ wrapper can replay `handle_records_ingested` safely.
- **Cross-task dependency:** `tests/api/test_records_router.py` (Task 15) needs the `claims_feed` example added to `medicare_fraud.yaml` (Task 16) for its `202` cases. Both tasks note this; in subagent-driven execution, run Task 16 before treating Task 15's full suite as green.
