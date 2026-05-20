# Module: ingestion

**Verified against codebase:** 2026-05-20
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

## Directory Structure

```
ingestion/
  service.py          # IngestionService: orchestrates register + ingest
  service_models.py   # DocumentSubmission, DocumentReceipt, IngestionTask
  protocols.py        # IngestionServiceProtocol + sub-protocols
  models.py           # DocumentFormat, ParsedDocument, ExtractionResult, etc.
  chunker.py          # ChunkingResult; implements DocumentChunkerProtocol
  extractor.py        # Entity/relationship extraction (uses LLM adapter)
  validator.py        # ValidationReport; implements DocumentValidatorProtocol
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
