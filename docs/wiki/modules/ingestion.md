# Module: ingestion

**Verified against codebase:** 2026-06-16
**Source:** `backend/ingestion/`

## Purpose

Document registration, parsing, chunking, and entity/relationship extraction. Accepts raw file bytes or URIs, produces `DocumentReceipt` / `DocumentsUploadedEvent`, then `ParsedDocument` -> `ChunkingResult` -> `ExtractionResult` -> `ValidationReport`. Worker parsing is triggered by `DocumentsUploadedEvent`.

Does **not** own: graph writes (graph module) or vector indexing (vectorstore/embeddings modules). The ingestion service does publish document upload, parse-success, and parse-failure events; later pipeline events are emitted by the worker/coordinator and downstream services.

---

## Protocols (`ingestion/protocols.py`)

### `IngestionServiceProtocol`
```python
class IngestionServiceProtocol(Protocol):
    def register_documents(
        self,
        knowledge_base_id: str,
        submissions: list[DocumentSubmission],
        *,
        correlation_id: str | None = None,
    ) -> list[DocumentReceipt]: ...

    def ingest_task(self, task: IngestionTask) -> ParseResult | DocumentParseFailure: ...

    def process_documents_uploaded(
        self,
        event: DocumentsUploadedEvent,
    ) -> list[ParseResult | DocumentParseFailure]: ...
```

### `DocumentChunkerProtocol`
```python
class DocumentChunkerProtocol(Protocol):
    def chunk_document(
        self,
        parsed_document: ParsedDocument,
        source_document_id: str,
    ) -> ChunkingResult: ...
```

### `DocumentExtractorProtocol`
```python
class DocumentExtractorProtocol(Protocol):
    def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult: ...
```

### `DocumentValidatorProtocol`
```python
class DocumentValidatorProtocol(Protocol):
    def validate_extraction(self, extraction_result: ExtractionResult) -> ValidationReport: ...
```

---

## Service Models (`ingestion/service_models.py`)

### `DocumentSubmission`
```python
class DocumentSubmission(BaseModel):
    filename: str | None = None
    content: bytes | None = None
    content_type: str | None = None
    uri: str | None = None
    document_format: DocumentFormat | None = None
    source_type: SourceType | None = None
    # Requires content OR uri (validated)
```

### `DocumentReceipt`
```python
class DocumentReceipt(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    filename: str | None
    status: IngestionStatus
    storage_key: str | None
    uri: str | None
    document_format: DocumentFormat | None
    replaced_document_id: str | None = None
    enqueued: bool = False
    created_at: datetime
```

### `IngestionTask`
```python
class IngestionTask(BaseModel):
    knowledge_base_id: str
    source_document: SourceDocument
    storage_key: str | None
    content_type: str | None
```

---

## Models (`ingestion/models.py`)

Key types:
- `DocumentFormat` — enum: `PDF`, `DOCX`, `HTML`, `TXT`, `JSON`, `CSV`, `XLSX`
- `IngestionStatus` — enum for document lifecycle status
- `SourceType` — enum: file_upload, api_push, remote_url
- `ParsedDocument` — parsed text content + metadata
- `ExtractionResult` — extracted entity + relationship candidates
- `ValidationReport` — pass/fail counts + error details

---

## Extractor Classes (`ingestion/extractor.py`)

Last verified: 2026-06-16

Two concrete implementations of `DocumentExtractorProtocol`:

### `PatternDocumentExtractor`
Baseline config-driven extractor using property label matching patterns (regex). Iterates chunks, matches property names in text, builds `CandidateEntity` and `CandidateRelationship` objects based on co-occurrence.

Constructor:
```python
PatternDocumentExtractor(
    entity_definitions: list[EntityDefinition],
    relationship_definitions: list[RelationshipDefinition] | None = None,
    *,
    extraction_method: str = "pattern_v1",
)
```

### `LlmDocumentExtractor`
Schema-driven LLM extractor. Generates per-chunk prompts from `EntityDefinition`/`RelationshipDefinition` schemas, calls `LlmClientProtocol.generate()` requesting JSON output, strips markdown fences, validates required properties, and deduplicates entities across chunks using configured natural keys. Runs an intra-chunk relationship pass after dedup.

Constructor:
```python
LlmDocumentExtractor(
    entity_definitions: list[EntityDefinition],
    relationship_definitions: list[RelationshipDefinition] | None = None,
    *,
    llm_client: LlmClientProtocol,
    natural_keys: dict[str, list[str]] | None = None,
    extraction_method: str = "llm_v1",
    model_name: str = "extractor-model",
)
```

- `natural_keys`: maps entity type name → list of property names that form the dedup key. When two chunks produce entities with the same natural key values, the second is silently dropped.
- LLM failures (4xx, transport errors) are caught as `LlmProviderError` and surfaced as `ExtractionResult.warnings` — no exception is raised to the caller.
- Malformed or unknown-type entities from the LLM are similarly warned and skipped.

### `create_document_extractor` factory

```python
def create_document_extractor(
    entity_definitions: list[EntityDefinition],
    relationship_definitions: list[RelationshipDefinition] | None = None,
    *,
    llm_client: LlmClientProtocol | None = None,
    natural_keys: dict[str, list[str]] | None = None,
) -> PatternDocumentExtractor | LlmDocumentExtractor:
```

Returns `LlmDocumentExtractor` when `llm_client` is provided; otherwise returns `PatternDocumentExtractor`. When `llm_client` is provided and `natural_keys` is `None`, auto-derives natural keys from `EntityDefinition.natural_key` for any entity definition that has them set. Explicit `natural_keys` always take precedence.

---

## Provenance Stamping (`ingestion/validator.py`)

Last verified: 2026-06-16

`_entity_from_candidate` and `_relationship_from_candidate` helpers (called by `ExtractionResultValidator`) stamp the following provenance metadata on every validated `Entity` and `Relationship` using constants from [`shared/provenance.py`](shared.md#provenancepy):

| Key | Value |
|-----|-------|
| `SOURCE_KIND_KEY` | `SOURCE_KIND_DOCUMENT` (`"document"`) |
| `SOURCE_DOCUMENT_ID_KEY` | `candidate.source_document_id` |
| `SOURCE_CHUNK_ID_KEY` | `candidate.chunk_id` |

---

## Service Models (`ingestion/service_models.py`)

### `DocumentReceipt` (updated 2026-05-22)
```python
class DocumentReceipt(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    filename: str | None
    status: IngestionStatus
    storage_key: str | None
    uri: str | None
    document_format: DocumentFormat | None
    created_at: datetime
    replaced_document_id: str | None = None
    enqueued: bool = False
```

`enqueued` is set by `IngestionService.register_documents` only for references that were included in the published `documents.uploaded` event. The API router (`POST /knowledgebases/{id}/documents`) uses it to decide whether to start a workflow and whether it is safe to clean up a replacement candidate. `replaced_document_id` is populated by the API router when an existing document with the same content hash was a replacement candidate.

## Registration Safety

Local file submissions are stored at `knowledgebases/{kb_id}/documents/{source_document_id}/source`. Duplicate content checks that exact source key with `object_store.exists()`; unrelated artifacts under the same document prefix do not suppress ingestion. If publishing `documents.uploaded` fails after storage, a configured `IngestionRecoveryStore` writes a durable marker under `recovery/ingestion/`. `replay_recovery_markers()` removes a marker only after the event bus accepts the reconstructed event.

The KB upload route reads incoming files in 64 KiB chunks and raises 413 immediately after the configured byte cap is exceeded. For re-upload cleanup, it records the replacement candidate before registration but deletes old graph/vector/object-store artifacts only after an enqueued receipt is returned.

## Remote Fetch Safety

`HttpxRemoteDocumentFetcher` streams remote responses, supports HTTPS only, re-validates the final redirected URL scheme, enforces `max_bytes` while iterating chunks, and turns malformed or negative `content-length` values into `RemoteFetchError` so the service can publish `DocumentsFailedEvent`.

---

## Directory Structure

```
ingestion/
  service.py          # IngestionService: orchestrates register + ingest
  recovery.py         # Durable recovery markers for storage-then-publish failures
  service_models.py   # DocumentSubmission, DocumentReceipt, IngestionTask
  protocols.py        # IngestionServiceProtocol + sub-protocols
  models.py           # DocumentFormat, ParsedDocument, ExtractionResult, etc.
  chunker.py          # ChunkingResult; implements DocumentChunkerProtocol
  extractor.py        # PatternDocumentExtractor, LlmDocumentExtractor, create_document_extractor
  validator.py        # ValidationReport + provenance stamping helpers
  orchestrators/      # Batch + source-document orchestration helpers
    protocols.py      # ParseResult, DocumentParseFailure
  parsers/
    registry.py       # ParserRegistry, create_default_registry()
    format_resolver.py
    protocols.py
    pdf.py, docx.py, html.py, txt.py, json.py, csv.py, xlsx.py
    remote.py         # Fetch-and-parse for remote URIs
```

**Gap:** `HtmlParser` is registered and extracts normalized visible text. Richer preservation of headings, links, and table structure is tracked in `docs/backlog/ingestion.md` as `ingestion.02`.

---

## Module Dependencies

- `shared/types.py` — `Entity`, `Relationship`, `EntityDefinition`
- `events/types.py` — `DocumentsUploadedEvent`, pipeline event types
- `llm/` — via `DocumentExtractorProtocol` (LLM-powered extraction)
- `storage/` — reads/writes artifact bytes
- `config/schema.py` — `ChunkingConfig`, `DomainConfig`

---

## Tests

Location: `backend/tests/ingestion/`
