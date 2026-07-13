# BL-041 — Ingestion Document-Status Projection + Failure-Path Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every source document a durable, monotonic ingestion status (including a new `EXTRACTED_EMPTY` state and per-document failure isolation in the coordinator), projected from existing pipeline events into Postgres and served by `GET /knowledgebases/{kb_id}/documents`.

**Architecture:** A new `SourceDocumentStatusStore` protocol lives in `ingestion/` (protocol in `ingestion/adapters/protocols.py` with a re-export from `ingestion/protocols.py`, adapters in `ingestion/adapters/` — this mirrors the freshest exemplars `records/` and `scorecards/` exactly). The worker projects `documents.uploaded` / `documents.parsed` / `documents.failed` / `documents.extraction_warning` events into the store inside `_dispatch_event` (so projection writes are covered by the existing retry/DLQ wrapper and are replay-safe because transitions are monotonic). The API reads the store via DI. **No new event types are introduced and `events/codec.py` `EVENT_TYPE_REGISTRY` is not touched** — `EXTRACTED_EMPTY` is a status transition derived from the existing `DocumentsExtractionWarningEvent.empty_extraction` flag.

**Module placement decision:** The status store lives in `ingestion/` because it is the durable read-model of the ingestion lifecycle (`IngestionStatus` already lives in `ingestion/models.py`), and both the worker (`agent/`) and the gateway (`api/`) may import `ingestion` protocols — the same sharing pattern already used for `records.adapters.protocols.RawRecordStore` and `scorecards.adapters.protocols.ScorecardRunRepository`. This honors the 3-path rule: `api/` and `agent/` never import each other; they meet only at the shared protocol + events.

**Status semantics (used consistently in every task):**

| Event | Transition | Rank |
|---|---|---|
| `documents.uploaded` | `PENDING` | 0 |
| (reserved) | `PARSING` | 10 |
| `documents.parsed` | `PARSED` | 20 |
| (reserved) | `CHUNKED` / `EXTRACTED` | 30 / 40 |
| `documents.extraction_warning`, `empty_extraction=False` | `VALIDATED` + drop counts/reasons | 50 |
| `documents.extraction_warning`, `empty_extraction=True` | `EXTRACTED_EMPTY` + drop counts/reasons | 60 |
| `documents.failed` | `FAILED` + `last_error` | 70 |

A transition only changes `current_status` when its rank is **strictly greater** than the stored rank (so a stale `parsing`/`parsed` arriving after `failed` is ignored, and redelivered events are no-ops). Drop counts and sample reasons are absolute values from the validation report, so they overwrite (idempotent) whenever the transition carries them, regardless of rank. Clean documents durably rest at `PARSED` (the projection deliberately subscribes only to the four event types in AC 2); the API keeps returning the existing computed `status` field alongside the new durable `current_status`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg via `database.protocols.ConnectionProvider`, Alembic (raw-SQL migrations), pytest, pyright strict.

## Global Constraints

- `pyright` (bare, from `backend/`, i.e. `backend/.venv/bin/pyright`) must be **zero errors**; no `Any`; `tool.pyright.include` already covers `ingestion`, `agent`, `events`, `database`, `api/routers/knowledgebases.py`, `tests/agent`, `tests/ingestion`, `tests/database` — new test files in those dirs are strict-checked too. Never import private `_helpers` into included test dirs.
- Lint: `backend/.venv/bin/ruff check --no-cache .` (ruff's cache dir is not writable in the sandbox).
- pytest coverage ≥ 85% per touched package (`ingestion`, `agent`, `api`, `knowledgebases`); run `backend/.venv/bin/pytest --cov` before declaring done.
- Host pytest against Postgres needs `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test` (integration-marked tests skip when unset).
- Frontend contracts MUST be regenerated after ANY frontend-consumed Pydantic change: from repo root `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`, then `cd chili_app && npm run codegen:api`. CI fails on drift. (Task 9 changes `DocumentSummary` → regen is mandatory.)
- Worker containers do NOT hot-reload — after backend changes, the worker must be restarted (`docker compose -f docker-compose.dev.yaml restart chili-worker`). This is a main-session concern only.
- E2E / full-stack verification runs in the MAIN session, not in implementation subagents. **No docker commands inside implementation tasks** — stack-level verification is collected in the final "Main-session verification" task.
- The hand-maintained event codec registry (`events/codec.py`) must NOT change. No new event types in `events/types.py`.
- Frontend Ingestion Studio wiring is explicitly OUT of scope (contracts regen only).
- All file paths below are relative to `/home/rdhagan92/chiliAI` unless prefixed with `backend/` commands that say "from `backend/`".
- Commit after every task (small, green commits).

---

### Task 1: Coordinator residue — per-document `DocumentsFailedEvent` instead of batch-poisoning `ValueError` (AC 4)

This is deliberately first: it is small and unblocks BL-043's failure counter (the workflow tracker already treats `documents.failed` as a terminal-failure event type via `_TERMINAL_FAILURE_EVENT_TYPES` in `agent/workflow_tracking.py`).

**Files:**
- Modify: `backend/agent/coordinator.py` (`handle_documents_parsed` at ~1151-1213, `handle_documents_chunked` at ~1224-1277, plus its event imports)
- Test: `backend/tests/agent/test_coordinator.py` (replace `test_handle_documents_parsed_raises_when_storage_key_missing` at ~2599 and `test_handle_documents_chunked_raises_when_storage_key_missing` at ~2621; add batch-isolation tests)

**Interfaces:**
- Consumes: existing `DocumentsFailedEvent` / `DocumentFailureReference` from `events.types` (already registered in the codec; already published by `ingestion/service.py:365-377` on parse failure — imitate that shape).
- Produces: `handle_documents_parsed` / `handle_documents_chunked` never raise for a missing storage key or an unreadable/invalid stored artifact; they publish one `DocumentsFailedEvent` (same `correlation_id` as the incoming event) carrying every failed document, continue processing the rest of the batch, and still return the count of successfully processed documents. Chunker/extractor/`put_bytes` exceptions still propagate (those may be transient and belong to retry/DLQ).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/agent/test_coordinator.py`, DELETE the two existing tests `test_handle_documents_parsed_raises_when_storage_key_missing` (~line 2599) and `test_handle_documents_chunked_raises_when_storage_key_missing` (~line 2621), and add these four tests in their place (all imports used below — `DocumentsFailedEvent`, `DocumentsChunkedEvent`, `EntitiesExtractedEvent`, `DocumentsParsedEvent`, `ParsedDocumentReference`, `ChunkedDocumentReference`, `ParsedDocument`, `ChunkingResult`, `InMemoryEventBus`, `InMemoryObjectStore`, `create_document_chunker`, `create_document_extractor`, `handle_documents_parsed`, `handle_documents_chunked` — already exist at the top of this test module):

```python
def test_handle_documents_parsed_publishes_failure_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()

    processed = handle_documents_parsed(
        DocumentsParsedEvent(
            correlation_id="corr-fail-1",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test",
                )
            ]
        ),
        document_chunker=chunker,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].correlation_id == "corr-fail-1"
    failure = failed_events[0].documents[0]
    assert failure.knowledge_base_id == "kb-1"
    assert failure.source_document_id == "doc-1"
    assert "parsed_document_storage_key" in failure.error_message
    assert not any(
        isinstance(event, DocumentsChunkedEvent)
        for event in event_bus.published_events
    )


def test_handle_documents_parsed_isolates_bad_document_from_batch() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    good_key = "knowledgebases/kb-1/parsed/parsed-good.json"
    object_store.put_bytes(
        good_key,
        ParsedDocument(
            id="parsed-good",
            source_document_id="doc-good",
            text_content="Claim 42 was filed by provider A.",
            parser_name="test-parser",
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_parsed(
        DocumentsParsedEvent(
            correlation_id="corr-mixed",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-bad",
                    parsed_document_id="parsed-bad",
                    parser_name="test-parser",
                    parsed_document_storage_key="knowledgebases/kb-1/parsed/missing.json",
                ),
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-good",
                    parsed_document_id="parsed-good",
                    parser_name="test-parser",
                    parsed_document_storage_key=good_key,
                ),
            ]
        ),
        document_chunker=chunker,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    chunked_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsChunkedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert len(chunked_events) == 1
    assert chunked_events[0].correlation_id == "corr-mixed"
    assert chunked_events[0].documents[0].source_document_id == "doc-good"


def test_handle_documents_chunked_publishes_failure_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extractor = create_document_extractor([])

    processed = handle_documents_chunked(
        DocumentsChunkedEvent(
            correlation_id="corr-fail-2",
            documents=[
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    chunk_count=0,
                    strategy="x",
                )
            ]
        ),
        document_extractor=extractor,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].correlation_id == "corr-fail-2"
    assert failed_events[0].documents[0].source_document_id == "doc-1"
    assert "chunks_storage_key" in failed_events[0].documents[0].error_message
    assert not any(
        isinstance(event, EntitiesExtractedEvent)
        for event in event_bus.published_events
    )


def test_handle_documents_chunked_isolates_unreadable_artifact_from_batch() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extractor = create_document_extractor([])
    good_key = "knowledgebases/kb-1/chunks/parsed-good.json"
    object_store.put_bytes(
        good_key,
        ChunkingResult(
            source_document_id="doc-good",
            parsed_document_id="parsed-good",
            strategy_used="StructuredRecordChunker",
            chunks=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    bad_key = "knowledgebases/kb-1/chunks/parsed-bad.json"
    object_store.put_bytes(
        bad_key,
        b"{not valid json at all",
        media_type="application/json",
    )

    processed = handle_documents_chunked(
        DocumentsChunkedEvent(
            correlation_id="corr-mixed-2",
            documents=[
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-bad",
                    parsed_document_id="parsed-bad",
                    chunk_count=0,
                    strategy="x",
                    chunks_storage_key=bad_key,
                ),
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-good",
                    parsed_document_id="parsed-good",
                    chunk_count=0,
                    strategy="StructuredRecordChunker",
                    chunks_storage_key=good_key,
                ),
            ]
        ),
        document_extractor=extractor,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    extracted_events = [
        event for event in event_bus.published_events
        if isinstance(event, EntitiesExtractedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert len(extracted_events) == 1
    assert extracted_events[0].documents[0].source_document_id == "doc-good"
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/test_coordinator.py -k "publishes_failure or isolates" -v`
Expected: 4 FAILED (the first two with `ValueError` raised instead of a published event; the batch tests with raised exceptions).

- [ ] **Step 3: Implement per-document failure isolation**

In `backend/agent/coordinator.py`, ensure the events import block includes `DocumentFailureReference` and `DocumentsFailedEvent` (add to the existing `from events.types import (...)` / `from events import (...)` list if not present).

Replace the body of `handle_documents_parsed` (~lines 1151-1213) with:

```python
def handle_documents_parsed(
    event: DocumentsParsedEvent,
    *,
    document_chunker: DocumentChunker,
    object_store: ObjectStore,
    event_bus: EventBus,
    kb_repository: KnowledgeBaseRepository | None = None,
) -> int:
    """Chunk parsed documents and publish the next workflow event.

    Per-document isolation (BL-041): a missing ``parsed_document_storage_key``
    or an unreadable/invalid parsed artifact fails only that document (a
    ``DocumentsFailedEvent`` is published) instead of poisoning the batch and
    burning retries to the DLQ. Chunker and object-store *write* errors still
    propagate to the retry/DLQ wrapper — they may be transient.
    """
    references: list[ChunkedDocumentReference] = []
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        if kb_repository is not None and document.warning_count > 0:
            kb_repository.record_document_warnings(
                document.knowledge_base_id,
                document.source_document_id,
                additional_count=document.warning_count,
                reasons=list(document.warning_samples),
            )
        if document.parsed_document_storage_key is None:
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        "DocumentsParsedEvent reference is missing "
                        "parsed_document_storage_key; cannot chunk."
                    ),
                    storage_key=document.storage_key,
                )
            )
            continue
        try:
            stored = object_store.get_bytes(document.parsed_document_storage_key)
            parsed_document = ParsedDocument.model_validate_json(stored.content)
        except Exception as exc:  # noqa: BLE001 - per-document isolation (BL-041)
            logger.error(
                "Failed to load parsed artifact. source_document_id=%s "
                "storage_key=%s error_class=%s: %s",
                document.source_document_id,
                document.parsed_document_storage_key,
                type(exc).__name__,
                exc,
            )
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        f"Failed to load parsed artifact "
                        f"'{document.parsed_document_storage_key}': {exc}"
                    ),
                    storage_key=document.storage_key,
                )
            )
            continue
        result = document_chunker.chunk_document(
            parsed_document,
            source_document_id=document.source_document_id,
        )
        chunks_storage_key = _build_chunks_storage_key(
            document.knowledge_base_id,
            document.parsed_document_id,
        )
        object_store.put_bytes(
            chunks_storage_key,
            result.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "chunk_count": len(result.chunks),
            },
        )
        references.append(
            ChunkedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                chunk_count=len(result.chunks),
                strategy=result.strategy_used,
                storage_key=document.storage_key,
                parsed_document_storage_key=document.parsed_document_storage_key,
                chunks_storage_key=chunks_storage_key,
            )
        )
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
            )
        )
    if references:
        event_bus.publish(
            DocumentsChunkedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)
```

Replace the body of `handle_documents_chunked` (~lines 1224-1277) with:

```python
def handle_documents_chunked(
    event: DocumentsChunkedEvent,
    *,
    document_extractor: DocumentExtractorProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Extract entity candidates from persisted chunks and publish the next event.

    Per-document isolation (BL-041): a missing ``chunks_storage_key`` or an
    unreadable/invalid chunks artifact fails only that document via a
    ``DocumentsFailedEvent`` instead of poisoning the batch.
    """
    references: list[ExtractedDocumentReference] = []
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        if document.chunks_storage_key is None:
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        "DocumentsChunkedEvent reference is missing "
                        "chunks_storage_key; cannot extract."
                    ),
                    storage_key=document.storage_key,
                )
            )
            continue
        try:
            stored = object_store.get_bytes(document.chunks_storage_key)
            chunking_result = ChunkingResult.model_validate_json(stored.content)
        except Exception as exc:  # noqa: BLE001 - per-document isolation (BL-041)
            logger.error(
                "Failed to load chunks artifact. source_document_id=%s "
                "storage_key=%s error_class=%s: %s",
                document.source_document_id,
                document.chunks_storage_key,
                type(exc).__name__,
                exc,
            )
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        f"Failed to load chunks artifact "
                        f"'{document.chunks_storage_key}': {exc}"
                    ),
                    storage_key=document.storage_key,
                )
            )
            continue
        extraction_result = document_extractor.extract_document(chunking_result)
        extraction_storage_key = _build_extraction_storage_key(
            document.knowledge_base_id,
            extraction_result.id,
        )
        object_store.put_bytes(
            extraction_storage_key,
            extraction_result.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "extraction_result_id": extraction_result.id,
                "entity_count": len(extraction_result.candidate_entities),
                "relationship_count": len(extraction_result.candidate_relationships),
            },
        )
        references.append(
            ExtractedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=extraction_result.id,
                entity_count=len(extraction_result.candidate_entities),
                relationship_count=len(extraction_result.candidate_relationships),
                storage_key=document.storage_key,
                parsed_document_storage_key=document.parsed_document_storage_key,
                chunks_storage_key=document.chunks_storage_key,
                extraction_storage_key=extraction_storage_key,
            )
        )
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
            )
        )
    if references:
        event_bus.publish(
            EntitiesExtractedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/test_coordinator.py -v`
Expected: ALL PASS (including the pre-existing `test_handle_documents_parsed_publishes_chunked_event`, `test_handle_documents_parsed_persists_parser_warnings`, and drain tests — the happy path is unchanged).

- [ ] **Step 5: Type-check and lint**

From `backend/`:
Run: `.venv/bin/pyright` — Expected: 0 errors.
Run: `.venv/bin/ruff check --no-cache .` — Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "fix(agent): per-document DocumentsFailedEvent instead of batch-poisoning ValueError (BL-041 AC4)"
```

---

### Task 2: `IngestionStatus.EXTRACTED_EMPTY`, status ranks, and projection models

**Files:**
- Modify: `backend/ingestion/models.py` (extend `IngestionStatus`, add `STATUS_RANK`, `DocumentStatusTransition`, `SourceDocumentStatusRecord`; extend `__all__`)
- Test: `backend/tests/ingestion/test_models.py` (append tests)

**Interfaces:**
- Produces (used by Tasks 3-9):
  - `IngestionStatus.EXTRACTED_EMPTY` with value `"extracted_empty"`.
  - `STATUS_RANK: dict[IngestionStatus, int]` — total, covers every enum member, `FAILED` is the maximum, `EXTRACTED_EMPTY` sits between `VALIDATED` and `FAILED`.
  - `DocumentStatusTransition(knowledge_base_id: str, source_document_id: str, status: IngestionStatus, error_message: str | None = None, dropped_entity_count: int | None = None, dropped_relationship_count: int | None = None, sample_reasons: list[str] | None = None, occurred_at: datetime = utc_now())` — `None` count/reason fields mean "leave stored value unchanged".
  - `SourceDocumentStatusRecord(knowledge_base_id: str, source_document_id: str, current_status: IngestionStatus, status_rank: int, last_error: str | None, dropped_entity_count: int, dropped_relationship_count: int, sample_reasons: list[str], first_event_at: datetime, updated_at: datetime)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/ingestion/test_models.py`:

```python
from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)


def test_ingestion_status_includes_extracted_empty() -> None:
    assert IngestionStatus.EXTRACTED_EMPTY.value == "extracted_empty"


def test_status_rank_is_total_and_monotonic() -> None:
    assert set(STATUS_RANK) == set(IngestionStatus)
    assert STATUS_RANK[IngestionStatus.FAILED] == max(STATUS_RANK.values())
    assert (
        STATUS_RANK[IngestionStatus.PENDING]
        < STATUS_RANK[IngestionStatus.PARSING]
        < STATUS_RANK[IngestionStatus.PARSED]
        < STATUS_RANK[IngestionStatus.CHUNKED]
        < STATUS_RANK[IngestionStatus.EXTRACTED]
        < STATUS_RANK[IngestionStatus.VALIDATED]
        < STATUS_RANK[IngestionStatus.EXTRACTED_EMPTY]
        < STATUS_RANK[IngestionStatus.FAILED]
    )


def test_document_status_transition_defaults_leave_counts_unset() -> None:
    transition = DocumentStatusTransition(
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        status=IngestionStatus.PARSED,
    )
    assert transition.error_message is None
    assert transition.dropped_entity_count is None
    assert transition.dropped_relationship_count is None
    assert transition.sample_reasons is None


def test_source_document_status_record_round_trips() -> None:
    record = SourceDocumentStatusRecord(
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        current_status=IngestionStatus.EXTRACTED_EMPTY,
        status_rank=STATUS_RANK[IngestionStatus.EXTRACTED_EMPTY],
        last_error=None,
        dropped_entity_count=3,
        dropped_relationship_count=1,
        sample_reasons=["entity cand-1: unknown type"],
        first_event_at=utc_now(),
        updated_at=utc_now(),
    )
    assert (
        SourceDocumentStatusRecord.model_validate_json(record.model_dump_json())
        == record
    )
```

(`utc_now` is imported in this test module already via `shared.utils`; if not, add `from shared.utils import utc_now`.)

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/ingestion/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'STATUS_RANK'`.

- [ ] **Step 3: Implement the models**

In `backend/ingestion/models.py`:

Add `EXTRACTED_EMPTY` to `IngestionStatus` (after `VALIDATED`):

```python
class IngestionStatus(str, Enum):
    """Lifecycle states for a source document during ingestion."""

    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKED = "chunked"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    EXTRACTED_EMPTY = "extracted_empty"
    FAILED = "failed"
```

Directly below the enum, add:

```python
# Monotonic ordering for the durable per-document status projection (BL-041).
# A transition only changes the stored status when its rank is strictly
# greater, so a stale `parsing` arriving after `failed` is ignored and event
# redelivery is a no-op. Gaps of 10 leave room for future stages.
STATUS_RANK: dict[IngestionStatus, int] = {
    IngestionStatus.PENDING: 0,
    IngestionStatus.PARSING: 10,
    IngestionStatus.PARSED: 20,
    IngestionStatus.CHUNKED: 30,
    IngestionStatus.EXTRACTED: 40,
    IngestionStatus.VALIDATED: 50,
    IngestionStatus.EXTRACTED_EMPTY: 60,
    IngestionStatus.FAILED: 70,
}
```

Add the two models (place after `SourceDocument`):

```python
class DocumentStatusTransition(BaseModel):
    """One projected status observation for a source document.

    ``None`` count/reason fields mean "leave the stored value unchanged";
    populated fields carry absolute values from the validation report and
    overwrite (idempotent on redelivery).
    """

    knowledge_base_id: str
    source_document_id: str
    status: IngestionStatus
    error_message: str | None = None
    dropped_entity_count: int | None = Field(default=None, ge=0)
    dropped_relationship_count: int | None = Field(default=None, ge=0)
    sample_reasons: list[str] | None = None
    occurred_at: datetime = Field(default_factory=utc_now)


class SourceDocumentStatusRecord(BaseModel):
    """Durable current-status projection row for a source document."""

    knowledge_base_id: str
    source_document_id: str
    current_status: IngestionStatus
    status_rank: int = Field(ge=0)
    last_error: str | None = None
    dropped_entity_count: int = Field(default=0, ge=0)
    dropped_relationship_count: int = Field(default=0, ge=0)
    sample_reasons: list[str] = Field(default_factory=list)
    first_event_at: datetime
    updated_at: datetime
```

Extend `__all__` with `"STATUS_RANK"`, `"DocumentStatusTransition"`, `"SourceDocumentStatusRecord"` (keep alphabetical order).

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/ingestion/test_models.py tests/ingestion/test_service.py tests/api/test_knowledgebases_router.py -v`
Expected: ALL PASS (the enum extension is additive; existing users at `ingestion/orchestrators/source_documents.py` only reference existing members).

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/ingestion/models.py backend/tests/ingestion/test_models.py
git commit -m "feat(ingestion): EXTRACTED_EMPTY status, rank map, and status-projection models (BL-041)"
```

---

### Task 3: `SourceDocumentStatusStore` protocol + in-memory adapter + exceptions

**Files:**
- Create: `backend/ingestion/exceptions.py`
- Create: `backend/ingestion/adapters/__init__.py`
- Create: `backend/ingestion/adapters/protocols.py`
- Create: `backend/ingestion/adapters/in_memory.py`
- Modify: `backend/ingestion/protocols.py` (re-export, mirroring `scorecards/protocols.py`)
- Test: `backend/tests/ingestion/test_status_store_in_memory.py`

**Interfaces:**
- Consumes: Task 2 models (`DocumentStatusTransition`, `SourceDocumentStatusRecord`, `STATUS_RANK`, `IngestionStatus`).
- Produces (used by Tasks 5-9):

```python
class SourceDocumentStatusStore(Protocol):
    def apply(self, transition: DocumentStatusTransition) -> SourceDocumentStatusRecord: ...
    def get_many(self, *, knowledge_base_id: str, source_document_ids: list[str]) -> dict[str, SourceDocumentStatusRecord]: ...
    def list(self, *, knowledge_base_id: str, limit: int, offset: int, status: IngestionStatus | None = None) -> tuple[list[SourceDocumentStatusRecord], int]: ...
    def delete_by_kb(self, knowledge_base_id: str) -> int: ...
```

  plus `InMemorySourceDocumentStatusStore` (implements it) and `DocumentStatusPersistenceError` (raised by the Postgres adapter in Task 5). `list` orders newest-first by `(updated_at, source_document_id)` descending.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/ingestion/test_status_store_in_memory.py`:

```python
"""Monotonic-transition semantics of the in-memory document status store."""

from __future__ import annotations

from datetime import UTC, datetime

from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
)

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 1, 12, 1, tzinfo=UTC)
T2 = datetime(2026, 7, 1, 12, 2, tzinfo=UTC)


def _transition(
    status: IngestionStatus,
    *,
    doc: str = "doc-1",
    occurred_at: datetime = T0,
    error: str | None = None,
    dropped_entities: int | None = None,
    dropped_relationships: int | None = None,
    reasons: list[str] | None = None,
) -> DocumentStatusTransition:
    return DocumentStatusTransition(
        knowledge_base_id="kb-1",
        source_document_id=doc,
        status=status,
        error_message=error,
        dropped_entity_count=dropped_entities,
        dropped_relationship_count=dropped_relationships,
        sample_reasons=reasons,
        occurred_at=occurred_at,
    )


def test_satisfies_protocol() -> None:
    assert isinstance(InMemorySourceDocumentStatusStore(), SourceDocumentStatusStore)


def test_apply_inserts_first_transition() -> None:
    store = InMemorySourceDocumentStatusStore()
    record = store.apply(_transition(IngestionStatus.PENDING))
    assert record.current_status == IngestionStatus.PENDING
    assert record.status_rank == STATUS_RANK[IngestionStatus.PENDING]
    assert record.first_event_at == T0
    assert record.updated_at == T0
    assert record.dropped_entity_count == 0
    assert record.sample_reasons == []


def test_forward_transition_advances_status() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PENDING, occurred_at=T0))
    record = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    assert record.current_status == IngestionStatus.PARSED
    assert record.first_event_at == T0
    assert record.updated_at == T1


def test_stale_transition_after_failed_is_ignored() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="parse exploded")
    )
    record = store.apply(_transition(IngestionStatus.PARSING, occurred_at=T2))
    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "parse exploded"
    assert record.status_rank == STATUS_RANK[IngestionStatus.FAILED]


def test_redelivery_is_idempotent() -> None:
    store = InMemorySourceDocumentStatusStore()
    first = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    replay = store.apply(_transition(IngestionStatus.PARSED, occurred_at=T1))
    assert replay == first


def test_warning_counts_overwrite_without_status_regression() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            dropped_relationships=2,
            reasons=["entity cand-1: unknown type"],
        )
    )
    # A later transition without counts leaves them untouched.
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T2, error="late failure")
    )
    assert record.current_status == IngestionStatus.FAILED
    assert record.dropped_entity_count == 4
    assert record.dropped_relationship_count == 2
    assert record.sample_reasons == ["entity cand-1: unknown type"]
    assert record.last_error == "late failure"


def test_get_many_returns_only_known_documents() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))
    store.apply(_transition(IngestionStatus.FAILED, doc="doc-2", error="x"))
    found = store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1", "doc-2", "doc-3"]
    )
    assert set(found) == {"doc-1", "doc-2"}
    assert found["doc-2"].current_status == IngestionStatus.FAILED


def test_list_filters_by_status_and_paginates_newest_first() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-2", occurred_at=T1, error="x")
    )
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-3", occurred_at=T2, error="y")
    )

    all_items, all_total = store.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert all_total == 3
    assert [item.source_document_id for item in all_items] == [
        "doc-3", "doc-2", "doc-1"
    ]

    failed, failed_total = store.list(
        knowledge_base_id="kb-1", limit=1, offset=1, status=IngestionStatus.FAILED
    )
    assert failed_total == 2
    assert [item.source_document_id for item in failed] == ["doc-2"]

    other_kb, other_total = store.list(knowledge_base_id="kb-9", limit=10, offset=0)
    assert other_kb == [] and other_total == 0


def test_delete_by_kb_removes_all_rows_for_kb() -> None:
    store = InMemorySourceDocumentStatusStore()
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1"))
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-2"))
    assert store.delete_by_kb("kb-1") == 2
    assert store.delete_by_kb("kb-1") == 0
    assert store.list(knowledge_base_id="kb-1", limit=10, offset=0) == ([], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/ingestion/test_status_store_in_memory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.adapters'`.

- [ ] **Step 3: Implement exceptions, protocol, and in-memory adapter**

Create `backend/ingestion/exceptions.py`:

```python
"""Ingestion module exceptions."""

from __future__ import annotations

__all__ = ["DocumentStatusPersistenceError"]


class DocumentStatusPersistenceError(RuntimeError):
    """Raised when the document status store cannot read or write a row."""
```

Create `backend/ingestion/adapters/__init__.py`:

```python
"""Adapter implementations for ingestion persistence protocols."""
```

Create `backend/ingestion/adapters/protocols.py`:

```python
"""Adapter-level protocol for the durable document status projection (BL-041)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ingestion.models import (
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["SourceDocumentStatusStore"]


@runtime_checkable
class SourceDocumentStatusStore(Protocol):
    """Persist and query the per-document ingestion status projection.

    ``apply`` is monotonic: a transition only changes ``current_status`` when
    its ``STATUS_RANK`` is strictly greater than the stored rank, so stale or
    redelivered events are no-ops. Drop counts / sample reasons are absolute
    values and overwrite whenever the transition carries them.
    """

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        """Upsert one status observation; return the resulting current row."""
        ...

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        """Return known rows keyed by source_document_id (missing ids omitted)."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        """Return a page of rows (newest first) plus the total match count."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all rows for a knowledge base; return the count removed."""
        ...
```

Create `backend/ingestion/adapters/in_memory.py`:

```python
"""In-memory document status store for tests and DB-less development."""

from __future__ import annotations

from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["InMemorySourceDocumentStatusStore"]

_Key = tuple[str, str]


class InMemorySourceDocumentStatusStore:
    """A dict-backed status store with the same monotonic semantics as Postgres."""

    def __init__(self) -> None:
        self._records: dict[_Key, SourceDocumentStatusRecord] = {}

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        key = (transition.knowledge_base_id, transition.source_document_id)
        new_rank = STATUS_RANK[transition.status]
        existing = self._records.get(key)
        if existing is None:
            record = SourceDocumentStatusRecord(
                knowledge_base_id=transition.knowledge_base_id,
                source_document_id=transition.source_document_id,
                current_status=transition.status,
                status_rank=new_rank,
                last_error=transition.error_message,
                dropped_entity_count=transition.dropped_entity_count or 0,
                dropped_relationship_count=(
                    transition.dropped_relationship_count or 0
                ),
                sample_reasons=list(transition.sample_reasons or []),
                first_event_at=transition.occurred_at,
                updated_at=transition.occurred_at,
            )
            self._records[key] = record
            return record
        advanced = new_rank > existing.status_rank
        record = existing.model_copy(
            update={
                "current_status": (
                    transition.status if advanced else existing.current_status
                ),
                "status_rank": max(existing.status_rank, new_rank),
                "last_error": (
                    transition.error_message
                    if advanced and transition.error_message is not None
                    else existing.last_error
                ),
                "dropped_entity_count": (
                    transition.dropped_entity_count
                    if transition.dropped_entity_count is not None
                    else existing.dropped_entity_count
                ),
                "dropped_relationship_count": (
                    transition.dropped_relationship_count
                    if transition.dropped_relationship_count is not None
                    else existing.dropped_relationship_count
                ),
                "sample_reasons": (
                    list(transition.sample_reasons)
                    if transition.sample_reasons is not None
                    else existing.sample_reasons
                ),
                "updated_at": max(existing.updated_at, transition.occurred_at),
            }
        )
        self._records[key] = record
        return record

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        found: dict[str, SourceDocumentStatusRecord] = {}
        for document_id in source_document_ids:
            record = self._records.get((knowledge_base_id, document_id))
            if record is not None:
                found[document_id] = record
        return found

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and (status is None or record.current_status == status)
        ]
        matches.sort(
            key=lambda record: (record.updated_at, record.source_document_id),
            reverse=True,
        )
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._records if key[0] == knowledge_base_id]
        for key in keys:
            del self._records[key]
        return len(keys)
```

Append to `backend/ingestion/protocols.py` (mirrors how `scorecards/protocols.py` re-exports its adapter protocol):

```python
from ingestion.adapters.protocols import SourceDocumentStatusStore
```

and add `"SourceDocumentStatusStore"` to its `__all__` list. (Place the import with the other `ingestion.*` imports at the top of the file, not at the bottom.)

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/ingestion/ -v`
Expected: ALL PASS.

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/ingestion/exceptions.py backend/ingestion/adapters backend/ingestion/protocols.py backend/tests/ingestion/test_status_store_in_memory.py
git commit -m "feat(ingestion): SourceDocumentStatusStore protocol + in-memory adapter (BL-041 AC1)"
```

---

### Task 4: Alembic migration `0009_document_status`

**Files:**
- Create: `backend/database/migrations/versions/0009_document_status.py`
- Test: `backend/tests/database/test_migration_0009.py` (mirrors `test_migration_0006.py`: no DB needed)

**Interfaces:**
- Produces: table `source_document_status` with PK `(knowledge_base_id, source_document_id)` and index `ix_source_document_status_kb_status` — column names exactly match `SourceDocumentStatusRecord` fields (Task 2) and the Postgres adapter SQL (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/database/test_migration_0009.py`:

```python
"""Unit checks for the 0009 source_document_status migration (no DB needed)."""

from __future__ import annotations

from importlib import import_module

import pytest

_MODULE = "database.migrations.versions.0009_document_status"


def test_revision_chain() -> None:
    migration = import_module(_MODULE)
    assert migration.revision == "0009_document_status"
    assert migration.down_revision == "0008_scorecards"


def test_upgrade_creates_source_document_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    normalized = " ".join(" ".join(statements).split()).lower()
    assert "create table if not exists source_document_status" in normalized
    assert "primary key (knowledge_base_id, source_document_id)" in normalized
    assert "current_status text not null" in normalized
    assert "status_rank integer not null" in normalized
    assert "last_error text" in normalized
    assert "sample_reasons jsonb not null default '[]'::jsonb" in normalized
    assert "ix_source_document_status_kb_status" in normalized


def test_downgrade_drops_table(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.downgrade()
    joined = " ".join(statements).lower()
    assert "drop index if exists ix_source_document_status_kb_status" in joined
    assert "drop table if exists source_document_status" in joined
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/database/test_migration_0009.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the migration**

Create `backend/database/migrations/versions/0009_document_status.py`:

```python
"""Durable per-document ingestion status projection (BL-041).

Revision ID: 0009_document_status
Revises: 0008_scorecards
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_document_status"
down_revision: str | None = "0008_scorecards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document_status (
            knowledge_base_id text NOT NULL,
            source_document_id text NOT NULL,
            current_status text NOT NULL,
            status_rank integer NOT NULL,
            last_error text,
            dropped_entity_count integer NOT NULL DEFAULT 0,
            dropped_relationship_count integer NOT NULL DEFAULT 0,
            sample_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            first_event_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (knowledge_base_id, source_document_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_source_document_status_kb_status
        ON source_document_status (knowledge_base_id, current_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_source_document_status_kb_status")
    op.execute("DROP TABLE IF EXISTS source_document_status")
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/database/ -v`
Expected: `test_migration_0009.py` PASSES; `test_migrations.py` tests SKIP unless `DATABASE_URL` is set (that full up/down cycle is exercised in Task 5 Step 5 and in main-session verification).

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/database/migrations/versions/0009_document_status.py backend/tests/database/test_migration_0009.py
git commit -m "feat(database): 0009 source_document_status projection table (BL-041 AC1)"
```

---

### Task 5: Postgres adapter with SQL-level monotonic guard

**Files:**
- Create: `backend/ingestion/adapters/postgres.py`
- Test: `backend/tests/database/test_document_status_postgres.py` (integration-marked; real-DB proof of the monotonic upsert — this is the heart of AC 1, so it is NOT faked)

**Interfaces:**
- Consumes: `database.protocols.ConnectionProvider` / `Row`; Task 2 models; Task 3 protocol + `DocumentStatusPersistenceError`.
- Produces: `PostgresSourceDocumentStatusStore(provider: ConnectionProvider)` implementing `SourceDocumentStatusStore`. Single-statement upsert with `ON CONFLICT ... DO UPDATE` + `RETURNING` enforces monotonicity in SQL (safe under concurrent workers).

- [ ] **Step 1: Write the failing integration tests**

Create `backend/tests/database/test_document_status_postgres.py` (reuses the `database_url` fixture from `backend/tests/database/conftest.py`, which skips when `DATABASE_URL` is unset):

```python
"""Integration tests: Postgres document status store monotonic upsert (BL-041)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore
from ingestion.models import DocumentStatusTransition, IngestionStatus

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 1, 12, 1, tzinfo=UTC)
T2 = datetime(2026, 7, 1, 12, 2, tzinfo=UTC)


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(
        DatabaseConfig(backend="postgres")
    )
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute("DELETE FROM source_document_status")
        conn.commit()
    yield connection_provider
    connection_provider.close()


def _transition(
    status: IngestionStatus,
    *,
    doc: str = "doc-1",
    occurred_at: datetime = T0,
    error: str | None = None,
    dropped_entities: int | None = None,
    reasons: list[str] | None = None,
) -> DocumentStatusTransition:
    return DocumentStatusTransition(
        knowledge_base_id="kb-pg",
        source_document_id=doc,
        status=status,
        error_message=error,
        dropped_entity_count=dropped_entities,
        sample_reasons=reasons,
        occurred_at=occurred_at,
    )


def test_stale_parsing_after_failed_is_ignored(provider: ConnectionProvider) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="boom")
    )
    record = store.apply(_transition(IngestionStatus.PARSING, occurred_at=T2))

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "boom"
    assert record.first_event_at == T0


def test_warning_counts_persist_and_overwrite(provider: ConnectionProvider) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            reasons=["entity cand-1: unknown type"],
        )
    )
    replay = store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            reasons=["entity cand-1: unknown type"],
        )
    )
    assert replay.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert replay.dropped_entity_count == 4
    assert replay.sample_reasons == ["entity cand-1: unknown type"]

    fetched = store.get_many(
        knowledge_base_id="kb-pg", source_document_ids=["doc-1"]
    )
    assert fetched["doc-1"] == replay


def test_list_filters_by_status_and_delete_by_kb(
    provider: ConnectionProvider,
) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-2", occurred_at=T1, error="x")
    )

    failed, total = store.list(
        knowledge_base_id="kb-pg",
        limit=10,
        offset=0,
        status=IngestionStatus.FAILED,
    )
    assert total == 1
    assert failed[0].source_document_id == "doc-2"

    everything, all_total = store.list(
        knowledge_base_id="kb-pg", limit=10, offset=0
    )
    assert all_total == 2
    assert [row.source_document_id for row in everything] == ["doc-2", "doc-1"]

    assert store.delete_by_kb("kb-pg") == 2
    assert store.list(knowledge_base_id="kb-pg", limit=10, offset=0) == ([], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_document_status_postgres.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.adapters.postgres'`. (If Postgres is not running, start the dev stack in the MAIN session first; if that is impossible right now, note it and rely on the main-session verification task — do not fake this test.)

- [ ] **Step 3: Implement the Postgres adapter**

Create `backend/ingestion/adapters/postgres.py`:

```python
"""Postgres-backed document status store (BL-041)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from ingestion.exceptions import DocumentStatusPersistenceError
from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["PostgresSourceDocumentStatusStore"]

_COLUMNS = (
    "knowledge_base_id, source_document_id, current_status, status_rank, "
    "last_error, dropped_entity_count, dropped_relationship_count, "
    "sample_reasons, first_event_at, updated_at"
)

# Monotonic upsert: the status/rank/error only advance when the incoming rank
# is strictly greater than the stored rank; counts and reasons are absolute
# values that overwrite whenever provided (NULL params mean "keep existing").
_APPLY_SQL = f"""
    INSERT INTO source_document_status ({_COLUMNS})
    VALUES (
        %s, %s, %s, %s, %s, COALESCE(%s, 0), COALESCE(%s, 0),
        COALESCE(%s::jsonb, '[]'::jsonb), %s, %s
    )
    ON CONFLICT (knowledge_base_id, source_document_id) DO UPDATE SET
        current_status = CASE
            WHEN EXCLUDED.status_rank > source_document_status.status_rank
            THEN EXCLUDED.current_status
            ELSE source_document_status.current_status
        END,
        last_error = CASE
            WHEN EXCLUDED.status_rank > source_document_status.status_rank
                 AND EXCLUDED.last_error IS NOT NULL
            THEN EXCLUDED.last_error
            ELSE source_document_status.last_error
        END,
        status_rank = GREATEST(
            source_document_status.status_rank, EXCLUDED.status_rank
        ),
        dropped_entity_count = COALESCE(
            %s, source_document_status.dropped_entity_count
        ),
        dropped_relationship_count = COALESCE(
            %s, source_document_status.dropped_relationship_count
        ),
        sample_reasons = COALESCE(
            %s::jsonb, source_document_status.sample_reasons
        ),
        updated_at = GREATEST(
            source_document_status.updated_at, EXCLUDED.updated_at
        )
    RETURNING {_COLUMNS}
"""

_GET_MANY_SQL = f"""
    SELECT {_COLUMNS} FROM source_document_status
    WHERE knowledge_base_id = %s AND source_document_id = ANY(%s)
"""

_DELETE_BY_KB_SQL = """
    DELETE FROM source_document_status
    WHERE knowledge_base_id = %s
"""


class PostgresSourceDocumentStatusStore:
    """A ``SourceDocumentStatusStore`` backed by ``source_document_status``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        reasons_json = (
            json.dumps(transition.sample_reasons)
            if transition.sample_reasons is not None
            else None
        )
        params: tuple[object, ...] = (
            transition.knowledge_base_id,
            transition.source_document_id,
            transition.status.value,
            STATUS_RANK[transition.status],
            transition.error_message,
            transition.dropped_entity_count,
            transition.dropped_relationship_count,
            reasons_json,
            transition.occurred_at,
            transition.occurred_at,
            transition.dropped_entity_count,
            transition.dropped_relationship_count,
            reasons_json,
        )
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_APPLY_SQL, params).fetchone()
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to apply document status transition."
            ) from exc
        if row is None:
            raise DocumentStatusPersistenceError(
                "Document status upsert returned no row."
            )
        return _row_to_record(row)

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        if not source_document_ids:
            return {}
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _GET_MANY_SQL, (knowledge_base_id, source_document_ids)
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to read document status rows."
            ) from exc
        records = [_row_to_record(row) for row in rows]
        return {record.source_document_id: record for record in records}

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        where = "WHERE knowledge_base_id = %s"
        params: list[object] = [knowledge_base_id]
        if status is not None:
            where += " AND current_status = %s"
            params.append(status.value)
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM source_document_status {where}",
                    tuple(params),
                ).fetchone()
                total = cast(int, total_row[0]) if total_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM source_document_status {where} "
                    "ORDER BY updated_at DESC, source_document_id DESC "
                    "LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to list document status rows."
            ) from exc
        return [_row_to_record(row) for row in rows], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to delete document status rows for knowledge base."
            ) from exc


def _row_to_record(row: Row) -> SourceDocumentStatusRecord:
    return SourceDocumentStatusRecord(
        knowledge_base_id=cast(str, row[0]),
        source_document_id=cast(str, row[1]),
        current_status=IngestionStatus(cast(str, row[2])),
        status_rank=cast(int, row[3]),
        last_error=cast(str | None, row[4]),
        dropped_entity_count=cast(int, row[5]),
        dropped_relationship_count=cast(int, row[6]),
        sample_reasons=_decode_reasons(row[7]),
        first_event_at=cast(datetime, row[8]),
        updated_at=cast(datetime, row[9]),
    )


def _decode_reasons(value: object) -> list[str]:
    raw = json.loads(value) if isinstance(value, (str, bytes)) else value
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DocumentStatusPersistenceError(
            "source_document_status.sample_reasons is not a list."
        )
    return [str(item) for item in cast(list[object], raw)]
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_document_status_postgres.py -v -m integration`
Expected: 3 PASSED (or SKIPPED with a clear note if Postgres is unavailable — then this MUST pass in main-session verification).

- [ ] **Step 5: Run the full migration cycle against the test DB**

From `backend/`:
Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_migrations.py -v -m integration`
Expected: PASS (0009 upgrades and downgrades cleanly in the chain).

- [ ] **Step 6: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/ingestion/adapters/postgres.py backend/tests/database/test_document_status_postgres.py
git commit -m "feat(ingestion): Postgres document status store with SQL monotonic guard (BL-041 AC1)"
```

---

### Task 6: Projection consumer — events → status transitions (AC 2, AC 5)

**Files:**
- Create: `backend/agent/status_projection.py`
- Test: `backend/tests/agent/test_status_projection.py`

**Interfaces:**
- Consumes: Task 3 `SourceDocumentStatusStore`; existing event types (`DocumentsUploadedEvent`, `DocumentsParsedEvent`, `DocumentsFailedEvent`, `DocumentsExtractionWarningEvent`).
- Produces: `project_document_status(event: AnyEvent, status_store: SourceDocumentStatusStore) -> int` — applies one transition per document reference, returns the transition count, returns 0 for any other event type. Task 7 wires it into `_dispatch_event`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/agent/test_status_projection.py`:

```python
"""Event-to-status-transition mapping for the document projection (BL-041)."""

from __future__ import annotations

from agent.status_projection import project_document_status
from events.types import (
    DocumentFailureReference,
    DocumentReference,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    ExtractionWarningReference,
    KnowledgeBaseCreatedEvent,
    ParsedDocumentReference,
)
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.models import IngestionStatus


def _get(store: InMemorySourceDocumentStatusStore, doc: str = "doc-1"):
    return store.get_many(knowledge_base_id="kb-1", source_document_ids=[doc])[doc]


def test_uploaded_projects_pending() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        DocumentsUploadedEvent(
            documents=[
                DocumentReference(
                    knowledge_base_id="kb-1", source_document_id="doc-1"
                )
            ]
        ),
        store,
    )
    assert applied == 1
    assert _get(store).current_status == IngestionStatus.PENDING


def test_parsed_projects_parsed() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        DocumentsParsedEvent(
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test",
                )
            ]
        ),
        store,
    )
    assert applied == 1
    assert _get(store).current_status == IngestionStatus.PARSED


def test_failed_projects_failed_with_error() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsFailedEvent(
            documents=[
                DocumentFailureReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    error_message="parser exploded",
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "parser exploded"


def test_empty_extraction_warning_projects_extracted_empty_status() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsExtractionWarningEvent(
            documents=[
                ExtractionWarningReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    valid_entity_count=0,
                    valid_relationship_count=0,
                    dropped_entity_count=4,
                    dropped_relationship_count=2,
                    stripped_property_count=0,
                    empty_extraction=True,
                    sample_reasons=["entity cand-1: unknown type"],
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert record.dropped_entity_count == 4
    assert record.dropped_relationship_count == 2
    assert record.sample_reasons == ["entity cand-1: unknown type"]


def test_non_empty_warning_projects_validated_with_counts() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsExtractionWarningEvent(
            documents=[
                ExtractionWarningReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    valid_entity_count=7,
                    valid_relationship_count=3,
                    dropped_entity_count=2,
                    dropped_relationship_count=0,
                    stripped_property_count=1,
                    empty_extraction=False,
                    sample_reasons=["entity cand-9: missing required field"],
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.VALIDATED
    assert record.dropped_entity_count == 2
    assert record.sample_reasons == ["entity cand-9: missing required field"]


def test_unrelated_event_projects_nothing() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1"), store
    )
    assert applied == 0
    assert store.list(knowledge_base_id="kb-1", limit=10, offset=0) == ([], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/test_status_projection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.status_projection'`.

- [ ] **Step 3: Implement the projection**

Create `backend/agent/status_projection.py`:

```python
"""Durable per-document status projection from pipeline events (BL-041).

Maps the four subscribed event types onto monotonic ``IngestionStatus``
transitions. ``EXTRACTED_EMPTY`` is intentionally a *status transition*
derived from the existing ``DocumentsExtractionWarningEvent`` — no new event
type exists, and the event codec registry is untouched.
"""

from __future__ import annotations

from events.types import (
    AnyEvent,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
)
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import DocumentStatusTransition, IngestionStatus

__all__ = ["project_document_status"]


def project_document_status(
    event: AnyEvent,
    status_store: SourceDocumentStatusStore,
) -> int:
    """Apply status transitions for a pipeline event; return the count applied."""

    transitions = _transitions_for_event(event)
    for transition in transitions:
        status_store.apply(transition)
    return len(transitions)


def _transitions_for_event(event: AnyEvent) -> list[DocumentStatusTransition]:
    if isinstance(event, DocumentsUploadedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.PENDING,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsParsedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.PARSED,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsFailedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.FAILED,
                error_message=document.error_message,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsExtractionWarningEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=(
                    IngestionStatus.EXTRACTED_EMPTY
                    if document.empty_extraction
                    else IngestionStatus.VALIDATED
                ),
                dropped_entity_count=document.dropped_entity_count,
                dropped_relationship_count=document.dropped_relationship_count,
                sample_reasons=list(document.sample_reasons),
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    return []
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/test_status_projection.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/agent/status_projection.py backend/tests/agent/test_status_projection.py
git commit -m "feat(agent): document status projection consumer (BL-041 AC2/AC5)"
```

---

### Task 7: Worker wiring — subscribe, dispatch, and build the store

**Files:**
- Modify: `backend/agent/coordinator.py`:
  - `WORKER_EVENT_TYPES` (~line 298): add `"documents.extraction_warning"`
  - `WorkerDependencies` (~line 322): add field
  - new builder `build_document_status_store` (next to `build_raw_record_store`, ~line 608)
  - `build_worker_dependencies` (~line 895): build + pass the store
  - `handle_event` (~line 2951): new kwarg, pass through
  - `_dispatch_event` (~line 3048): new kwarg, projection call at top
  - `drain_ingestion_events` (~line 3370 signature): new kwarg, pass to `handle_event`
  - `_drain_once` (~line 3534): pass `deps.document_status_store`
- Test: `backend/tests/agent/test_coordinator.py` (append)

**Interfaces:**
- Consumes: Task 6 `project_document_status`; Task 3/5 adapters.
- Produces: `build_document_status_store(provider: ConnectionProvider | None) -> SourceDocumentStatusStore`; every dispatch of `documents.uploaded/parsed/failed/extraction_warning` also writes the projection. Projection failures propagate to the existing retry/DLQ wrapper (safe: transitions are idempotent/monotonic, so replays are no-ops).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/agent/test_coordinator.py` (add imports `from agent.coordinator import WORKER_EVENT_TYPES, build_document_status_store` — extend the existing `from agent.coordinator import (...)` block — plus `from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore` and `from events.types import DocumentsExtractionWarningEvent, ExtractionWarningReference` if not already imported; `IngestionStatus` via `from ingestion.models import IngestionStatus`):

```python
def test_worker_subscribes_to_extraction_warning_events() -> None:
    assert "documents.extraction_warning" in WORKER_EVENT_TYPES


def test_build_document_status_store_falls_back_to_in_memory() -> None:
    store = build_document_status_store(None)
    assert isinstance(store, InMemorySourceDocumentStatusStore)


def test_handle_event_projects_extraction_warning_to_status_store() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=DocumentsExtractionWarningEvent(
                documents=[
                    ExtractionWarningReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        valid_entity_count=0,
                        valid_relationship_count=0,
                        dropped_entity_count=3,
                        dropped_relationship_count=0,
                        stripped_property_count=0,
                        empty_extraction=True,
                        sample_reasons=["entity cand-1: unknown type"],
                    )
                ]
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        document_status_store=status_store,
    )

    assert processed == 0
    projected = status_store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1"]
    )["doc-1"]
    assert projected.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert projected.dropped_entity_count == 3


def test_handle_event_projects_failed_documents_to_status_store() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    handle_event(
        EventDelivery(
            event=DocumentsFailedEvent(
                documents=[
                    DocumentFailureReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        error_message="parse exploded",
                    )
                ]
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        document_status_store=status_store,
    )

    projected = status_store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1"]
    )["doc-1"]
    assert projected.current_status == IngestionStatus.FAILED
    assert projected.last_error == "parse exploded"
```

(`DocumentFailureReference` import: add to the existing `events.types` import block in the test module if missing.)

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/test_coordinator.py -k "extraction_warning or status_store" -v`
Expected: FAIL (`ImportError` for `build_document_status_store`, unexpected keyword `document_status_store`).

- [ ] **Step 3: Wire the worker**

In `backend/agent/coordinator.py`:

1. Imports: add near the other ingestion imports —

```python
from agent.status_projection import project_document_status
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.protocols import SourceDocumentStatusStore
```

(`DocumentsExtractionWarningEvent` is already imported for `handle_entities_extracted`; add it to the import list if missing.) Add `"build_document_status_store"` to `__all__`.

2. `WORKER_EVENT_TYPES`: add `"documents.extraction_warning",` after `"documents.failed",`.

3. `WorkerDependencies`: add field (with the other protocol-typed fields, before the `graph_embeddings_enabled: bool = False` defaulted field):

```python
    document_status_store: SourceDocumentStatusStore
```

4. Builder (place next to `build_raw_record_store`, ~line 608):

```python
def build_document_status_store(
    provider: ConnectionProvider | None,
) -> SourceDocumentStatusStore:
    """Select a document status store: Postgres when a provider exists."""

    if provider is None:
        return InMemorySourceDocumentStatusStore()
    from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore

    return PostgresSourceDocumentStatusStore(provider)
```

(Module-level import of the Postgres adapter is also fine — it only imports `database.protocols`, no driver — prefer the module-level import if ruff flags the local one; then it is `from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore` at the top.)

5. `build_worker_dependencies`: after `raw_record_store = build_raw_record_store(connection_provider)` add

```python
    document_status_store = build_document_status_store(connection_provider)
```

and add `document_status_store=document_status_store,` to the `WorkerDependencies(...)` constructor call.

6. `handle_event`: add keyword parameter (with the other `| None = None` params, e.g. after `kb_deletion_stores`):

```python
    document_status_store: SourceDocumentStatusStore | None = None,
```

and pass `document_status_store=document_status_store,` in its `_dispatch_event(...)` call.

7. `_dispatch_event`: add the same keyword parameter `document_status_store: SourceDocumentStatusStore | None = None,` and replace the top of the body:

```python
    del delivery  # reserved for future stream offsets / dlq metadata
    # BL-041: durable per-document status projection. Runs inside the retry/DLQ
    # wrapper; transitions are monotonic + idempotent so replays are no-ops.
    if document_status_store is not None:
        project_document_status(event, document_status_store)
    if isinstance(event, DocumentsExtractionWarningEvent):
        return 0  # projection-only event; no pipeline stage follows
    if isinstance(event, DocumentsUploadedEvent):
        ...
```

(keep every existing branch unchanged below).

8. `drain_ingestion_events`: add keyword parameter `document_status_store: SourceDocumentStatusStore | None = None,` (next to `kb_repository`) and pass `document_status_store=document_status_store,` inside `_run_handler`'s `handle_event(...)` call.

9. `_drain_once`: pass `document_status_store=deps.document_status_store,` in the `drain_ingestion_events(...)` call.

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/agent/ -v`
Expected: ALL PASS (existing `WorkerDependencies` constructions in tests may need the new `document_status_store=InMemorySourceDocumentStatusStore()` field — fix any `TypeError: missing keyword argument` the same way; do NOT make the field optional to dodge them).

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "feat(agent): wire document status projection into worker dispatch (BL-041 AC2)"
```

---

### Task 8: KB-delete cascade covers the new table

**Files:**
- Modify: `backend/knowledgebases/cleanup.py` (field + step)
- Modify: `backend/api/_kb_cleanup.py` (`get_kb_deletion_stores` assembly)
- Modify: `backend/agent/coordinator.py` (`build_kb_deletion_stores` assembly)
- Modify: `backend/api/dependencies.py` (new `get_document_status_store` — also needed by Task 9)
- Test: `backend/tests/api/test_kb_cleanup.py` (`_STORE_FIELDS` / `_EXPECTED_STEP_NAMES`)

**Interfaces:**
- Consumes: Task 3/5 adapters; Task 7 `build_document_status_store`.
- Produces: `KbDeletionStores.document_status_store: SourceDocumentStatusStore`; cascade step named `"document_status"` (before `"object_store"`); `api.dependencies.get_document_status_store() -> SourceDocumentStatusStore`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/api/test_kb_cleanup.py`: add `"document_status_store"` to `_STORE_FIELDS` (after `"scorecard_run_repository"`) and `"document_status"` to `_EXPECTED_STEP_NAMES` (after `"scorecards"`); in the per-store assertion loop at the bottom of `test_kb_deletion_steps_purges_every_durable_store`, add `"document_status_store"` to the `delete_by_kb`-backed field tuple.

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/api/test_kb_cleanup.py -v`
Expected: FAIL (step list mismatch).

- [ ] **Step 3: Implement**

In `backend/knowledgebases/cleanup.py`:
- Import: `from ingestion.adapters.protocols import SourceDocumentStatusStore` (protocol-only import — allowed per the module docstring).
- Add field to `KbDeletionStores` after `scorecard_run_repository`:

```python
    document_status_store: SourceDocumentStatusStore
```

- Add the step in `kb_deletion_steps` after the `"scorecards"` entry:

```python
        ("document_status", lambda: stores.document_status_store.delete_by_kb(kb)),
```

In `backend/api/dependencies.py` (place next to `get_raw_record_store`, and add `"get_document_status_store"` to `__all__`; imports: `from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore`, `from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore`, `from ingestion.adapters.protocols import SourceDocumentStatusStore`):

```python
@lru_cache(maxsize=1)
def get_document_status_store() -> SourceDocumentStatusStore:
    """Return the durable document status store (Postgres when configured)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemorySourceDocumentStatusStore()
    return PostgresSourceDocumentStatusStore(provider)
```

Check whether `api/dependencies.py` has a cache-reset helper that clears `lru_cache`d providers between tests (search for `cache_clear`); if a reset list exists, add `get_document_status_store` to it.

In `backend/api/_kb_cleanup.py`: add to `get_kb_deletion_stores` a parameter

```python
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
```

(import the protocol from `ingestion.adapters.protocols` and the getter from `api.dependencies`), and pass `document_status_store=document_status_store,` into the `KbDeletionStores(...)` constructor.

In `backend/agent/coordinator.py` `build_kb_deletion_stores`: add `document_status_store=build_document_status_store(provider),` to its `KbDeletionStores(...)` constructor. (Alternatively accept it as a keyword argument and pass the already-built store from `build_worker_dependencies` — pick the simpler direct build; both use the same provider.)

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/api/test_kb_cleanup.py tests/api/test_kb_delete_cascade.py tests/agent/test_handle_knowledge_base_deleted.py tests/api/test_dependencies.py -v`
Expected: ALL PASS (fix any other test constructing `KbDeletionStores` by adding the new field with an `InMemorySourceDocumentStatusStore()` — search: `grep -rn "KbDeletionStores(" backend/tests`).

- [ ] **Step 5: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/knowledgebases/cleanup.py backend/api/_kb_cleanup.py backend/api/dependencies.py backend/agent/coordinator.py backend/tests/api/test_kb_cleanup.py
git commit -m "feat(knowledgebases): purge source_document_status in KB-delete cascade (BL-041)"
```

---

### Task 9: API — durable fields + status filter on `GET /knowledgebases/{kb_id}/documents`, contracts regen (AC 3)

**Files:**
- Modify: `backend/api/routers/knowledgebases.py` (`DocumentSummary` at ~82, `list_knowledge_base_documents` at ~311-359)
- Modify: `chili_app/openapi.json` + `chili_app/src/lib/api/schema.ts` (generated — via commands only, never by hand)
- Test: `backend/tests/api/test_knowledgebases_router.py` (append)

**Interfaces:**
- Consumes: Task 3 protocol + in-memory adapter; Task 8 `get_document_status_store`.
- Produces: `DocumentSummary` gains `current_status: str | None`, `last_error: str | None`, `dropped_entity_count: int`, `dropped_relationship_count: int`, `drop_sample_reasons: list[str]`. Endpoint gains `?status=<IngestionStatus value>` filter (422 on unknown values via enum validation). The legacy computed `status` field is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_knowledgebases_router.py` (module already imports `create_app`, `InMemoryKnowledgeBaseRepository`, `InMemoryObjectStore`, `DocumentRecord`, `KnowledgeBase`, `utc_now`, `TestClient`, `GraphMetrics`, `_MetricsOnlyGraphService`, `_build_config`, and the dependency getters; add `get_document_status_store` to the `api.dependencies` import list, plus `from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore` and `from ingestion.models import DocumentStatusTransition, IngestionStatus`):

```python
def _status_projection_harness() -> tuple[
    FastAPI, InMemoryKnowledgeBaseRepository, InMemorySourceDocumentStatusStore
]:
    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    repository.create(
        KnowledgeBase(
            id="kb-proj",
            name="Projection KB",
            description="",
            status="active",
            created_at=utc_now(),
        )
    )
    for document_id in ("doc-failed", "doc-empty", "doc-clean"):
        repository.add_document(
            DocumentRecord(
                id=document_id,
                knowledge_base_id="kb-proj",
                filename=f"{document_id}.txt",
                content_type="text/plain",
                size_bytes=10,
                status="pending",
            )
        )
    status_store.apply(
        DocumentStatusTransition(
            knowledge_base_id="kb-proj",
            source_document_id="doc-failed",
            status=IngestionStatus.FAILED,
            error_message="parser exploded",
        )
    )
    status_store.apply(
        DocumentStatusTransition(
            knowledge_base_id="kb-proj",
            source_document_id="doc-empty",
            status=IngestionStatus.EXTRACTED_EMPTY,
            dropped_entity_count=4,
            dropped_relationship_count=1,
            sample_reasons=["entity cand-1: unknown type"],
        )
    )
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_document_status_store] = lambda: status_store
    return app, repository, status_store


def test_documents_endpoint_returns_durable_projection_fields() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert items["doc-failed"]["current_status"] == "failed"
    assert items["doc-failed"]["last_error"] == "parser exploded"
    assert items["doc-empty"]["current_status"] == "extracted_empty"
    assert items["doc-empty"]["dropped_entity_count"] == 4
    assert items["doc-empty"]["dropped_relationship_count"] == 1
    assert items["doc-empty"]["drop_sample_reasons"] == [
        "entity cand-1: unknown type"
    ]
    assert items["doc-clean"]["current_status"] is None
    assert items["doc-clean"]["last_error"] is None
    assert items["doc-clean"]["dropped_entity_count"] == 0


def test_documents_endpoint_filters_by_durable_status() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents?status=failed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == ["doc-failed"]
    assert payload["items"][0]["current_status"] == "failed"


def test_documents_endpoint_rejects_unknown_status_filter() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents?status=bogus")

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`:
Run: `.venv/bin/pytest tests/api/test_knowledgebases_router.py -k projection -v` and `-k "filters_by_durable or rejects_unknown"`
Expected: FAIL (`ImportError` for `get_document_status_store` before Task 8 — Task 8 provides it, so this task must run after Task 8; then `KeyError: 'current_status'`).

- [ ] **Step 3: Implement the endpoint changes**

In `backend/api/routers/knowledgebases.py`:

1. Imports: add `get_document_status_store` to the `api.dependencies` import block; add

```python
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import IngestionStatus, SourceDocumentStatusRecord
```

2. Extend `DocumentSummary`:

```python
class DocumentSummary(BaseModel):
    """Summary projection of a registered document."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str
    created_at: datetime
    warning_count: int = Field(default=0, ge=0)
    warning_reasons: list[str] = Field(default_factory=list)
    # Durable ingestion projection (BL-041). ``current_status`` is None when
    # no pipeline event has been projected for the document yet.
    current_status: str | None = None
    last_error: str | None = None
    dropped_entity_count: int = Field(default=0, ge=0)
    dropped_relationship_count: int = Field(default=0, ge=0)
    drop_sample_reasons: list[str] = Field(default_factory=list)
```

3. Replace `list_knowledge_base_documents`:

```python
@router.get(
    "/{knowledge_base_id}/documents",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_knowledge_base_documents(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: IngestionStatus | None = Query(default=None, alias="status"),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
) -> DocumentListResponse:
    """Return registered documents, enriched with the durable status projection.

    ``status`` filters on the durable projection: documents without a
    projected status row never match a filter.
    """
    knowledge_base = repository.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    hydrated_knowledge_base = project_knowledge_base(
        knowledge_base,
        repository,
        graph_service,
        object_store,
    )

    projection_by_id: dict[str, SourceDocumentStatusRecord]
    if status_filter is not None:
        status_rows, total = document_status_store.list(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
            status=status_filter,
        )
        projection_by_id = {row.source_document_id: row for row in status_rows}
        records = [
            record
            for record in (
                repository.get_document(knowledge_base_id, row.source_document_id)
                for row in status_rows
            )
            if record is not None
        ]
    else:
        records, total = repository.list_documents(
            knowledge_base_id, limit=limit, offset=offset
        )
        projection_by_id = document_status_store.get_many(
            knowledge_base_id=knowledge_base_id,
            source_document_ids=[record.id for record in records],
        )

    items = [
        _document_summary(
            record,
            hydrated_knowledge_base,
            repository,
            projection_by_id.get(record.id),
        )
        for record in records
    ]
    return DocumentListResponse(items=items, total=total)


def _document_summary(
    record: DocumentRecord,
    knowledge_base: KnowledgeBase,
    repository: KnowledgeBaseRepository,
    projection: SourceDocumentStatusRecord | None,
) -> DocumentSummary:
    """Merge the registered-document record with its durable status projection."""
    return DocumentSummary(
        id=record.id,
        knowledge_base_id=record.knowledge_base_id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        status=document_status_for_knowledge_base(record, knowledge_base, repository),
        created_at=record.created_at,
        warning_count=record.warning_count,
        warning_reasons=record.warning_reasons,
        current_status=(
            projection.current_status.value if projection is not None else None
        ),
        last_error=projection.last_error if projection is not None else None,
        dropped_entity_count=(
            projection.dropped_entity_count if projection is not None else 0
        ),
        dropped_relationship_count=(
            projection.dropped_relationship_count if projection is not None else 0
        ),
        drop_sample_reasons=(
            list(projection.sample_reasons) if projection is not None else []
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`:
Run: `.venv/bin/pytest tests/api/test_knowledgebases_router.py tests/api/test_kb_projection.py tests/api/test_document_reupload.py -v`
Expected: ALL PASS (new fields are additive with defaults; existing assertions on `status`/`warning_count` unchanged).

- [ ] **Step 5: Regenerate frontend contracts**

From repo root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run lint && npm run build
```

Expected: openapi.json shows the new `DocumentSummary` fields and the `status` query enum; codegen rewrites `src/lib/api/schema.ts`; lint and `tsc -b`-backed build stay clean (frontend consumers are untouched — the new fields are additive, and Ingestion Studio wiring is explicitly out of scope).

- [ ] **Step 6: Type-check, lint, commit**

From `backend/`: `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .` (clean).

```bash
git add backend/api/routers/knowledgebases.py backend/tests/api/test_knowledgebases_router.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(api): durable current_status/last_error/drop counts + status filter on KB documents (BL-041 AC3)"
```

---

### Task 10: Full gates + documentation reconciliation

**Files:**
- Modify: `backend/ingestion/README.md`, `backend/README.md`, `docs/architecture.md`, `.github/copilot-instructions.md` (only if any contradicts the change), `docs/project/planning/sprints/2026-26.md` (mark BL-041 progress if the sprint file tracks status), `docs/backlog/README.md` + linked ingestion backlog file (BL-041 status)

- [ ] **Step 1: Run every backend gate**

From `backend/`:

```bash
.venv/bin/pytest --cov
.venv/bin/pyright
.venv/bin/ruff check --no-cache .
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest -m integration tests/database
```

Expected: full green, coverage ≥ 85% per touched package (`ingestion`, `agent`, `api`, `knowledgebases`, `database`), zero pyright errors, ruff clean. **Fix anything red before proceeding — including failures you merely surfaced.**

- [ ] **Step 2: Update docs**

- `backend/ingestion/README.md`: document the status projection — `IngestionStatus.EXTRACTED_EMPTY`, `STATUS_RANK` monotonicity, `SourceDocumentStatusStore` protocol, `ingestion/adapters/{in_memory,postgres}.py`, table `source_document_status` (migration `0009`).
- `backend/README.md` § Current State: note the durable document-status projection and per-document failure isolation in the coordinator.
- `docs/architecture.md`: add `source_document_status` to the persistence/table inventory; describe the projection consumer path (worker `_dispatch_event` → `agent/status_projection.py` → `ingestion` store) and the four subscribed event types; note the KB-delete cascade now includes `document_status`.
- Cross-check `.github/copilot-instructions.md` and `docs/testing/DATA.md` for contradictions (none expected — no new fixtures or bulk data).
- Update BL-041 status in the sprint 2026-26 plan / backlog files per their existing convention.

- [ ] **Step 3: Commit**

```bash
git add backend/ingestion/README.md backend/README.md docs/architecture.md docs/project docs/backlog .github 2>/dev/null
git commit -m "docs: document status projection architecture + BL-041 status"
```

---

### Task 11: Main-session verification (RUN IN MAIN SESSION ONLY — not a subagent task)

No code changes. The main session (which may run docker) verifies the full story end-to-end per CLAUDE.md ("run the API and worker locally, verify logs, database state, and API responses"):

1. `make dev` (or restart if already up). **Worker containers do not hot-reload — restart the worker:** `docker compose -f docker-compose.dev.yaml restart chili-worker`.
2. Apply the migration in the dev stack: `docker compose -f docker-compose.dev.yaml exec chili-api alembic upgrade head` (verify `0009_document_status` in output or via `alembic current`).
3. Create a KB and upload a document that parses cleanly; poll `GET /knowledgebases/{kb_id}/documents` → item shows `current_status: "parsed"` (durable) while the computed `status` continues to progress to `ready`.
4. Upload a document that yields zero valid entities (e.g. a text file whose content matches no configured entity type) → after the worker logs the extraction warning, the endpoint shows `current_status: "extracted_empty"` with `dropped_*` counts and `drop_sample_reasons`.
5. Upload a document that fails parsing (e.g. corrupt PDF bytes with a `.pdf` name) → `current_status: "failed"` with `last_error`; verify the worker logs show a published `documents.failed` and NO DLQ entry for the batch.
6. Filter check: `GET /knowledgebases/{kb_id}/documents?status=failed` returns only the failed document; `?status=bogus` → 422.
7. Database state: `docker compose -f docker-compose.dev.yaml exec postgres psql -U chili -d chili -c "SELECT source_document_id, current_status, status_rank, last_error FROM source_document_status;"` — rows match the API.
8. Restart the API container and re-issue the list request — statuses survive (durability, the point of BL-041).
9. Delete the KB; confirm `source_document_status` rows for it are gone (cascade step `document_status`).
10. Run the Playwright e2e suite against the running stack (`cd chili_app && npm run test:e2e`) to confirm no regression in existing document-list flows (Ingestion Studio wiring itself is out of scope).

---

## Self-Review (performed while writing)

- **AC 1** — protocol + Postgres adapter + migration `0009` + monotonic transitions: Tasks 2-5 (stale-`parsing`-after-`failed` is an explicit test in both adapters).
- **AC 2** — projection consumer subscribes to `documents.uploaded/parsed/failed` + extraction-warning on the worker side: Tasks 6-7 (`WORKER_EVENT_TYPES` gains only `documents.extraction_warning`; the other three were already consumed, projection hooks into `_dispatch_event`).
- **AC 3** — durable `current_status`, `last_error`, drop counts/sample reasons, status filter, contracts regen: Task 9.
- **AC 4** — coordinator residue first, per-document `DocumentsFailedEvent`: Task 1.
- **AC 5** — `EXTRACTED_EMPTY` via status transition, no new event type, codec untouched: Tasks 2 & 6 (grep the diff for `EVENT_TYPE_REGISTRY` — must be absent).
- **AC 6** — frontend wiring out of scope: only generated files under `chili_app/` change.
- Placeholder scan: every code step contains complete code; no TBD/TODO markers.
- Type consistency: `SourceDocumentStatusStore.apply/get_many/list/delete_by_kb`, `DocumentStatusTransition`, `SourceDocumentStatusRecord`, `build_document_status_store`, `get_document_status_store`, and `project_document_status` are named identically across Tasks 3-9.
