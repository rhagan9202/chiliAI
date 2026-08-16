# Ingestion Module

`ingestion/` handles document parsing, chunking, entity/relationship extraction, and registration for the chiliAI platform. It is the document-pipeline counterpart to `records/` (tabular feeds).

## Extractors

### PatternDocumentExtractor (default for the `local` LLM stub)

Regex/heuristic extractor. Used when no LLM client is configured or as a fast fallback. Produces lower-recall extractions suitable for smoke tests and offline environments. The worker selects it via `agent.coordinator.build_document_extractor` whenever `llm.provider` is `local` (the echo stub cannot produce extraction JSON); any real provider routes extraction through `LlmDocumentExtractor`.

### LlmDocumentExtractor

Schema-driven LLM extractor introduced in the `feature/ingestion-pipeline-e2e-demo` branch. Key behaviors:

- **Schema-driven prompts** — Derives the extraction prompt from `DomainConfig.entities` and `DomainConfig.relationships` at construction time, so the same extractor code works for any configured domain.
- **JSON-mode parsing** — Requests a structured JSON response from the LLM. The extractor strips markdown fences (` ```json ... ``` `) before parsing to tolerate models that wrap the payload.
- **Required-property validation** — After parsing, validates that each extracted entity has all required properties declared in the domain config. Entities failing validation are logged and dropped rather than propagated as malformed data.
- **Document-wide natural-key deduplication** — Entities that map to the same natural key (type + identifying property values) are merged across the whole document, keeping the first occurrence as the survivor. Surviving candidates accumulate `metadata["merged_chunk_ids"]` so provenance reflects every chunk that mentioned the entity (`ingestion.31`).
- **Model-sourced relationships** — The extractor uses the `relationships` array the model returns (each entry keyed by `source_index`/`target_index` into that chunk's `entities` array) rather than fabricating every source-type × target-type pair. Relationships whose endpoints fall out of range, were dropped during entity validation, name an unknown type, or whose endpoint types mismatch the `RelationshipDefinition` are dropped with a warning, never silently created (`ingestion.30`). Each emitted edge carries the model's supporting quote as evidence where available. Endpoints are then re-pointed onto the surviving deduplicated candidate, so an edge found in a later chunk that references an entity first seen (and deduplicated) in an earlier chunk is preserved rather than lost; edges that collapse onto a single survivor are dropped as self-loops (`ingestion.31`).
- **Fallback** — `create_document_extractor` returns `PatternDocumentExtractor` when no `llm_client` is injected. The worker's `build_document_extractor(config, llm_client)` (agent/coordinator.py) passes the client for every provider except `local`, whose echo stub cannot produce extraction JSON.

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

- **Type-aware normalization before schema checks** (`ingestion.14`) — `ingestion/normalization.py` converts raw extractor values against `PropertyDefinition.type` before `validate_entity` runs: string decimals (period or comma separator) → `float` (the platform's canonical decimal type), integer strings → `int`, `yes/no/true/false/1/0` → `bool`, common regional date formats → ISO 8601, enum values → the canonical config casing, and strings are whitespace-stripped. This is what lets CSV-sourced records (where every value is a string) produce typed entities. Unconvertible values land in `entity_errors` with a `normalization_failed` category so operators can distinguish them from schema rejections. `list`/`nested` pass through — `PropertyDefinition` declares no element type.
- **Unknown-property stripping** — When an entity's only fault is an unrecognized/hallucinated property, the unknown keys are relocated to `metadata["extra_properties"]` and the entity is admitted on its schema-known properties instead of being dropped wholesale. Each relocation is recorded on `ValidationReport.warnings`. Unknown entity types, missing required properties, and value-type violations still drop the candidate (recorded in `entity_errors`). The LLM prompt is also hardened to ask the model to use only schema-listed property names.
- **Durable extraction-warning signal** — During `handle_entities_extracted`, any document that produces zero valid entities OR had dropped/stripped candidates emits a per-document `DocumentsExtractionWarningEvent` (carrying valid/dropped counts, `stripped_property_count`, an `empty_extraction` flag, a bounded `sample_reasons` list, and the `validation_storage_key` for full detail) plus a structured worker log line. The zero-entity "ready" path additionally stamps `empty_extraction=True` and `source_document_id` on `KnowledgeBaseReadyReference`, so an empty knowledge base is no longer indistinguishable from a successful one.
- **Per-document surfacing** — The worker persists warning counts and a bounded reason sample onto `DocumentRecord` (`KnowledgeBaseRepository.record_document_warnings`): parse warnings from `ParsedDocumentReference.warning_count`/`warning_samples`, extraction/validation reasons from the warning event data (including extraction-stage warnings such as "LLM returned non-JSON"). `GET /knowledgebases/{id}/documents` exposes them as `DocumentSummary.warning_count`/`warning_reasons`, and the knowledge-bases workspace's Data section renders a warning chip plus a reasons list per document. Prometheus counters (`ingestion.17`, below) are now delivered; OTEL spans / Grafana dashboards remain tracked separately.

**Stage telemetry (BL-043):** each pipeline stage emits a structured `ingestion_stage` log line (logger `chili.ingestion.stage`) with fields `stage=` (`parse`|`chunk`|`extract`|`validate`), `source_document_id=`, `kb_id=`, `duration_ms=`, `outcome=` (`success`|`failed`|`empty`). `parse` is logged in `ingestion/service.py`; `chunk`/`extract`/`validate` in the worker handlers (`agent/coordinator.py`). Parse failures increment `ingestion_documents_failed_total{stage,error_class}` adjacent to the `DocumentsFailedEvent` publish — any new emission point of that event must add the same one-line increment. Dedup suppressions (document re-upload, identical record batch) increment `ingestion_dedup_suppressed_total{kind}`. Counters live in `shared/metrics.py`.

## Durable Document Status Projection (BL-041)

`SourceDocumentStatusStore` (`ingestion/adapters/protocols.py`) is the abstract contract for a durable, per-document ingestion status projection, distinct from the ephemeral `SourceDocument.status` field that only lives for the duration of a single service call. Two adapters implement it:

- `InMemorySourceDocumentStatusStore` (`ingestion/adapters/in_memory.py`) — process-local, used by tests and the `in_memory` backend selection.
- `PostgresSourceDocumentStatusStore` (`ingestion/adapters/postgres.py`) — backed by the `source_document_status` table (migration `0009_document_status`), selected via `build_document_status_store` in `agent/coordinator.py` (API side: `get_document_status_store` in `api/dependencies.py`).

**Status set and monotonic ordering.** `IngestionStatus` (`ingestion/models.py`) carries `PENDING`, `PARSING`, `PARSED`, `CHUNKED`, `EXTRACTED`, `VALIDATED`, `EXTRACTED_EMPTY`, and `FAILED`. `STATUS_RANK` assigns each a numeric rank (gaps of 10, so future stages can be inserted without renumbering) with `EXTRACTED_EMPTY` ranked just below `FAILED`. `EXTRACTED_EMPTY` is a **status value only** — no new event type was introduced; it is derived from the existing `DocumentsExtractionWarningEvent` when `document.empty_extraction` is `True` (`agent/status_projection.py`), keeping the hand-maintained event codec registry untouched.

**`apply()` monotonicity contract** — both adapters implement identical semantics, verified by shared test parametrization:
- `current_status`/`status_rank` advance only when the incoming transition's rank is **strictly greater** than the stored rank; a stale or redelivered event (e.g. a `PARSED` event arriving after `FAILED`) is a no-op.
- `dropped_entity_count`, `dropped_relationship_count`, and `sample_reasons` are absolute values that overwrite whenever the transition carries them (non-`None`), independent of rank.
- `last_error` (and `updated_at`) refresh whenever the transition advances the rank, **or** when the transition's status is `FAILED` and its rank is `>=` the stored rank — a second, newer failure redelivery replaces the recorded error even though it does not advance `status_rank` — provided the transition's `error_message` is not `None`. A lower-rank event arriving after `FAILED` never touches `last_error`, and a `FAILED` transition with a `None` error message never wipes a stored one. The Postgres adapter enforces this with a single `INSERT … ON CONFLICT DO UPDATE` using `CASE`/`GREATEST` expressions (no read-then-write race); the in-memory adapter mirrors the same branching in Python.

**Event consumer.** `agent/status_projection.py::project_document_status` maps four subscribed event types onto `DocumentStatusTransition`s and applies each via the store: `DocumentsUploadedEvent` → `PENDING`, `DocumentsParsedEvent` → `PARSED`, `DocumentsFailedEvent` → `FAILED` (carrying `error_message`), `DocumentsExtractionWarningEvent` → `EXTRACTED_EMPTY` or `VALIDATED` (carrying drop counts + a bounded `sample_reasons` list). The worker's `_dispatch_event` (`agent/coordinator.py`) calls this projector for every drained event, so the projection stays current without a dedicated consumer process or polling Redis Streams.

**API surface.** `GET /knowledgebases/{kb_id}/documents` reads the projection per document and exposes `current_status`, `last_error`, `dropped_entity_count`, `dropped_relationship_count`, and `drop_sample_reasons`; the endpoint also supports `?status=` filtering against `current_status`.

**Deletes.** `SourceDocumentStatusStore.delete_by_kb` is one step in the shared `knowledgebases.cleanup.kb_deletion_steps` KB-delete cascade (replayed identically by the API's synchronous path and the worker's `KnowledgeBaseDeletedEvent(cleanup_pending=True)` retry). `delete_by_document` purges a single row on `DELETE /knowledgebases/{kb_id}/documents/{document_id}` and on the changed-content reupload path (`_cleanup_replaced_document` in `api/routers/knowledgebases.py`), so a status-filtered `GET .../documents?status=...` list's `total` never counts a document that no longer exists.

**Orphan resurrection race.** The delete-time purge above is not the only line of defense: an in-flight pipeline event (e.g. a redelivered `DocumentsParsedEvent` for a document deleted/replaced mid-flight) can re-create a status row *after* the purge ran, leaving a row with no matching registered document. `list_knowledge_base_documents`'s status-filtered branch (`api/routers/knowledgebases.py`) treats this as expected: any returned row whose `source_document_id` has no matching document is excluded from both `items` and `total` (decrementing `total` by the reaped count) and opportunistically re-deleted via `delete_by_document`, so the orphan is cleaned up on the next read that surfaces it rather than permanently inflating `total`.

## Parser Registry

Parsers for PDF, DOCX, HTML, TXT, JSON, CSV, and XLSX are registered in `parsers/registry.py`.

The HTML parser (`parsers/html.py`, v2.0) preserves structural signal beyond flat visible text (`ingestion.02`): headings carry a markdown `#`/`##`/`###` marker so chunking can detect section boundaries; anchors keep their target as `[text](url)`; and tables are emitted as markdown pipe tables (nested tables are flattened into their parent cell). `parser_metadata` carries `heading_count`, `link_count`, and `table_count` for observability. `script`/`style`/`title` content is ignored.

**Optional PDF OCR fallback** (`ingestion.03`): `PdfParser(ocr_adapter=...)` accepts any `OcrAdapterProtocol` (`parsers/protocols.py`). When configured, pages that extract no text are OCR'd page-by-page (filling only the empty pages) and `parser_metadata["ocr_used"]` is set to `True`. OCR is **opt-in per deployment** — with no adapter a text-less PDF still raises `ParserError` (unchanged). The concrete `TesseractOcrAdapter` (`parsers/adapters/tesseract.py`) lives behind the optional `[ocr]` extra (`pdf2image` + `pytesseract`, plus system Tesseract/Poppler) and imports those deps lazily, so a default install never requires them.

## Parser Warnings

Parsers surface **non-fatal** diagnostics through a typed `ParsedDocument.warnings: list[ParserWarning]` channel (`ingestion.24`) instead of stuffing them into free-form `parser_metadata`. Each `ParserWarning` carries a stable `code`, a human `message`, a `severity` (`info`/`warning`/`error`), and optional location fields (`row_index`, `page_number`, `column_name`) so the knowledge-bases workspace can group, count, and link warnings to categories. Every in-tree parser emits warnings on its soft-failure paths — e.g. `pdf.empty_page`, `docx.empty_paragraph_skipped`, `csv.ragged_row` / `csv.dialect_fallback`, `xlsx.blank_row_skipped` / `xlsx.ragged_row`, `json.heterogeneous_array` / `json.scalar_root`, and `<parser>.charset_fallback` when a non-UTF-8 fallback encoding is used. The per-document `DocumentsParsedEvent` reference carries a `warning_count` so consumers can route on warnings without loading the payload.

## Commands

```bash
uv pip install -e ".[dev]"
pytest tests/ingestion -m "not integration"    # fast unit tests
pytest tests/ingestion -m integration          # needs a configured LLM adapter
```

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the end-to-end demo context.
