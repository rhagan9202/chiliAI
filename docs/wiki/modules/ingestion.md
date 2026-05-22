# Module: ingestion

**Verified against codebase:** 2026-05-22
**Source:** `backend/ingestion/`

## Purpose

Document parsing, chunking, and entity/relationship extraction. Accepts raw file bytes or URIs, produces `ParsedDocument` → `ChunkingResult` → `ExtractionResult` → `ValidationReport`. Triggered by the worker via `DocumentsUploadedEvent`.

Does **not** own: graph writes (graph module), vector indexing (vectorstore/embeddings modules), event publishing (those happen in the worker/coordinator).

---

## Protocols (`ingestion/protocols.py`)

### `IngestionServiceProtocol`
```python
class IngestionServiceProtocol(Protocol):
    def register_documents(
        self,
        knowledge_base_id: str,
        submissions: list[DocumentSubmission],
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
    created_at: datetime
    replaced_document_id: str | None = None  # set when content-hash idempotent re-upload replaced a prior doc
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
- `DocumentFormat` — enum: `PDF`, `DOCX`, `TXT`, `JSON`, `CSV`, `XLSX`, `HTML` (HTML enum value exists but no HTML parser registered — architecture.md note)
- `IngestionStatus` — enum for document lifecycle status
- `SourceType` — enum: file_upload, api_push, remote_url
- `ParsedDocument` — parsed text content + metadata
- `ExtractionResult` — extracted entity + relationship candidates
- `ValidationReport` — pass/fail counts + error details

---

## Extractor Classes (`ingestion/extractor.py`)

Last verified: 2026-05-22

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

Last verified: 2026-05-22

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
    replaced_document_id: str | None = None  # set when a prior doc with same content hash was replaced
```

`replaced_document_id` is populated by the API router (`POST /knowledgebases/{id}/documents`) when a content-hash idempotent re-upload replaces an existing document.

---

## Directory Structure

```
ingestion/
  service.py          # IngestionService: orchestrates register + ingest
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
    pdf.py, docx.py, txt.py, json.py, csv.py, xlsx.py
    remote.py         # Fetch-and-parse for remote URIs
```

**Gap:** `DocumentFormat.HTML` exists in the enum but no `html.py` parser is registered in `parsers/registry.py`.

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
