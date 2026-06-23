# Ingestion Module

`ingestion/` handles document parsing, chunking, entity/relationship extraction, and registration for the chiliAI platform. It is the document-pipeline counterpart to `records/` (tabular feeds).

## Extractors

### PatternDocumentExtractor (default)

Regex/heuristic extractor. Used when no LLM client is configured or as a fast fallback. Produces lower-recall extractions suitable for smoke tests and offline environments.

### LlmDocumentExtractor

Schema-driven LLM extractor introduced in the `feature/ingestion-pipeline-e2e-demo` branch. Key behaviors:

- **Schema-driven prompts** — Derives the extraction prompt from `DomainConfig.entities` and `DomainConfig.relationships` at construction time, so the same extractor code works for any configured domain.
- **JSON-mode parsing** — Requests a structured JSON response from the LLM. The extractor strips markdown fences (` ```json ... ``` `) before parsing to tolerate models that wrap the payload.
- **Required-property validation** — After parsing, validates that each extracted entity has all required properties declared in the domain config. Entities failing validation are logged and dropped rather than propagated as malformed data.
- **Document-wide natural-key deduplication** — Entities that map to the same natural key (type + identifying property values) are merged across the whole document, keeping the first occurrence as the survivor. Surviving candidates accumulate `metadata["merged_chunk_ids"]` so provenance reflects every chunk that mentioned the entity (`ingestion.31`).
- **Model-sourced relationships** — The extractor uses the `relationships` array the model returns (each entry keyed by `source_index`/`target_index` into that chunk's `entities` array) rather than fabricating every source-type × target-type pair. Relationships whose endpoints fall out of range, were dropped during entity validation, name an unknown type, or whose endpoint types mismatch the `RelationshipDefinition` are dropped with a warning, never silently created (`ingestion.30`). Each emitted edge carries the model's supporting quote as evidence where available. Endpoints are then re-pointed onto the surviving deduplicated candidate, so an edge found in a later chunk that references an entity first seen (and deduplicated) in an earlier chunk is preserved rather than lost; edges that collapse onto a single survivor are dropped as self-loops (`ingestion.31`).
- **Fallback** — When `IngestionService` is constructed without an `LlmClientProtocol` dependency, it falls back to `PatternDocumentExtractor` automatically. No config change is needed; the fallback is determined by whether a client is injected.

## Content-Hash Idempotency

Document registration is idempotent per knowledge base. The ingestion service derives a deterministic `source_document_id` from the SHA-256 hash of file content (or a URI hash for remote sources). Re-uploading the same bytes produces the same ID and does not publish a duplicate `documents.uploaded` event; the returned `DocumentReceipt.enqueued` flag is `False` for that suppressed duplicate. The KB upload route starts a workflow only when at least one receipt is enqueued.

The id uses the **full 64-character SHA-256 hex digest** — `doc-sha256-<64 hex>` for content uploads and `doc-uri-<64 hex>` for remote URIs (`ingestion.33`). It previously used only a 24-hex (96-bit) prefix, which could collide and silently route a new upload into the dedup path, returning another document's bytes. **Compat note:** the change alters the `source_document_id` value (and therefore the `knowledgebases/{kb_id}/documents/{id}/...` storage keys) for new uploads. There is no production data store to migrate — local/dev object stores and the gitignored `sample_data/` corpus are ephemeral and re-ingested; any document carrying an old `doc-sha256-<24 hex>` id is simply re-registered under its full-digest id on next upload. No one-time migration script is required for the prototype.

The KB upload route computes the content hash before registration and records any existing `DocumentRecord` as a replacement candidate. Destructive replacement cleanup is deferred until `register_documents()` returns an enqueued receipt. Registration failures and deduplicated `enqueued=False` receipts preserve the existing document, graph/vector provenance, and object-store artifacts. When cleanup does run, graph/vector source-document data and old document-prefix objects are removed while the receipt's current `storage_key` is protected.

## Upload and Remote Fetch Safety

`POST /knowledgebases/{kb_id}/documents` validates the declared content type against `ValidationConfig.allowed_content_types` and reads uploads in 64 KiB chunks, raising 413 as soon as `max_file_size_mb` is exceeded. The ingestion-service layer still trusts `DocumentSubmission` inputs; MIME sniffing and service-level policy enforcement remain tracked in `docs/backlog/ingestion.md`.

`HttpxRemoteDocumentFetcher` accepts HTTPS URIs only, follows redirects through `httpx.Client.stream()`, re-checks that the final URL is still HTTPS, validates malformed or negative `content-length` as `RemoteFetchError`, and enforces the byte cap while iterating response chunks.

## Publish Recovery

When a `documents.uploaded` publish fails after source bytes were stored, `IngestionService` can persist `IngestionRecoveryMarker` records through `IngestionRecoveryStore`. `replay_recovery_markers()` reconstructs `DocumentsUploadedEvent` from the marker and stored object metadata, and removes the marker only after the event bus accepts the replayed publish. The broader transactional outbox remains backlog work.

## Failure Handling

Every parse-stage failure is converted into a per-document `DocumentsFailedEvent` rather than escaping uncaught. `safe_parse_content`/`safe_parse_source` catch **any** exception (not only `ParserError`): a parser that raises mid-iteration (PDF `extract_text`, CSV/XLSX row iteration), an empty-content `ValidationError` from `ParsedDocument`, and any other unexpected error all become a typed `DocumentParseFailure`. The chosen approach is the **wrapper-level catch** in `orchestrators/parser.py` — individual parsers are not required to widen their own try-blocks. `IngestionService.ingest_task` additionally guards the object-store read so a missing/deleted source object (`KeyError`) produces a `DocumentParseFailure` and a published `DocumentsFailedEvent` instead of an uncaught exception. Unexpected (non-`ParserError`) failures are logged at error level with the `source_document_id` and exception class so they stay debuggable. One malformed document in a batch fails on its own; the rest of the batch is unaffected.

## Provenance Metadata

Every `Entity` and `Relationship` emitted by the extractor carries provenance fields (`source_kind`, `source_document_id`, `source_chunk_id`) so downstream cascade-delete and audit queries can trace data back to its source. See `backend/graph/README.md` for the full provenance contract.

`source_kind` reflects each candidate's **actual origin**, not a fixed value: text-derived chunks are stamped `source_kind="document"` and structured-record chunks (emitted by `StructuredRecordChunker`) are stamped `source_kind="record"` (`ingestion.34`). The discriminator is threaded explicitly via `ChunkMetadata.source_kind` (set by the chunker) and read back per candidate in `validate_extraction` using the candidate's `chunk_id`; a candidate whose chunk is absent falls back to `source_kind="document"`. This lets cascade-delete and audit queries correctly distinguish record-derived from document-derived data when records are ingested through the document pipeline.

## Extraction Validation and Empty-Extraction Visibility

`ExtractionResultValidator.validate_extraction` converts candidates into validated runtime objects and now surfaces, rather than silently swallows, degraded extractions (`ingestion.35`):

- **Unknown-property stripping** — When an entity's only fault is an unrecognized/hallucinated property, the unknown keys are relocated to `metadata["extra_properties"]` and the entity is admitted on its schema-known properties instead of being dropped wholesale. Each relocation is recorded on `ValidationReport.warnings`. Unknown entity types, missing required properties, and value-type violations still drop the candidate (recorded in `entity_errors`). The LLM prompt is also hardened to ask the model to use only schema-listed property names.
- **Durable extraction-warning signal** — During `handle_entities_extracted`, any document that produces zero valid entities OR had dropped/stripped candidates emits a per-document `DocumentsExtractionWarningEvent` (carrying valid/dropped counts, `stripped_property_count`, an `empty_extraction` flag, a bounded `sample_reasons` list, and the `validation_storage_key` for full detail) plus a structured worker log line. The zero-entity "ready" path additionally stamps `empty_extraction=True` and `source_document_id` on `KnowledgeBaseReadyReference`, so an empty knowledge base is no longer indistinguishable from a successful one.
- **Deferred surfacing** — The per-document status projection / `GET .../documents` API (`ingestion.18`) and Prometheus counters / OTEL spans (`ingestion.17`) are tracked separately; the durable event and full `ValidationReport` (persisted to the object store) carry the data those surfaces will consume.

## Parser Registry

Parsers for PDF, DOCX, HTML, TXT, JSON, CSV, and XLSX are registered in `parsers/registry.py`. The HTML parser currently normalizes visible text; richer heading/link/table fidelity is tracked separately in `docs/backlog/ingestion.md` as `ingestion.02`.

## Parser Warnings

Parsers surface **non-fatal** diagnostics through a typed `ParsedDocument.warnings: list[ParserWarning]` channel (`ingestion.24`) instead of stuffing them into free-form `parser_metadata`. Each `ParserWarning` carries a stable `code`, a human `message`, a `severity` (`info`/`warning`/`error`), and optional location fields (`row_index`, `page_number`, `column_name`) so the Ingestion Studio can group, count, and link warnings to categories. Every in-tree parser emits warnings on its soft-failure paths — e.g. `pdf.empty_page`, `docx.empty_paragraph_skipped`, `csv.ragged_row` / `csv.dialect_fallback`, `xlsx.blank_row_skipped` / `xlsx.ragged_row`, `json.heterogeneous_array` / `json.scalar_root`, and `<parser>.charset_fallback` when a non-UTF-8 fallback encoding is used. The per-document `DocumentsParsedEvent` reference carries a `warning_count` so consumers can route on warnings without loading the payload.

## Commands

```bash
pip install -e ".[dev]"
pytest tests/ingestion -m "not integration"    # fast unit tests
pytest tests/ingestion -m integration          # needs a configured LLM adapter
```

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the end-to-end demo context.
