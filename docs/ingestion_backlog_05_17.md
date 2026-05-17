# Ingestion Production Readiness Backlog - 2026-05-17

## Scope

This backlog covers the remaining work to move `backend/ingestion` from a strict-typed, tested prototype into a production-ready ingestion subsystem.

Current baseline:

- `ingestion` and `tests/ingestion` are included in backend pyright strict scope.
- HTML, PDF, DOCX, XLSX, TXT, CSV, and JSON have registered local parsers.
- The event-driven parse -> chunk -> extract -> validate -> graph pipeline is wired through `backend/agent/coordinator.py`.
- Current verification from the latest ingestion pass: `pyright` clean, `ruff check ingestion tests/ingestion` clean, `tests/ingestion` passing with 95% ingestion coverage.

Primary remaining gaps:

- The default extractor is regex/property-label based and is not sufficient for real narrative claims, letters, PDFs, or mixed clinical/administrative documents.
- Registration lacks idempotency, upload policy enforcement, durable publish recovery, and async/backpressure behavior.
- Validation lacks production confidence gating, entity deduplication, calibrated warnings, and richer provenance.
- Remote fetch and parser behavior need production security and malformed-input hardening.

## Priority Map

| Priority | Story | Why It Matters |
| --- | --- | --- |
| P0 | Stories 1-5 | Prevent duplicate, unsafe, or unrecoverable ingestion jobs. |
| P0 | Stories 6-8 | Make extraction quality usable on real documents. |
| P1 | Stories 9-13 | Improve correctness, provenance, parser durability, and remote-source security. |
| P1 | Stories 14-16 | Add operational readiness: observability, deletion/reindex support, and complete config docs. |
| P2 | Story 17 | Broaden certification tests and load/performance gates. |

---

## Story 1: Add Content Hash Idempotency And Deduplication

**As an operator**, I need repeated uploads of the same document to resolve to one canonical source document per knowledge base so users do not create duplicate graph entities, duplicate vectors, and duplicate workflow work.

**Current State**

- `IngestionService.register_documents()` always creates a new `SourceDocument.id`.
- `SourceDocument.checksum` exists but is not populated during registration.
- There is no durable lookup by `(knowledge_base_id, checksum)` before storage or event publication.

**Implementation Notes**

- Compute SHA-256 for byte uploads before storing content.
- For URI submissions, compute SHA-256 after fetch or store a remote-reference idempotency key until bytes are fetched.
- Add an ingestion document registry/repository abstraction rather than relying only on object-store keys.
- Return an existing `DocumentReceipt` when the same checksum already exists for the same knowledge base.
- Preserve reprocessing as an explicit option, not the default.

**Acceptance Criteria**

- Registering the same byte content twice for the same KB returns the same `source_document_id`.
- Registering the same byte content for different KBs creates separate source documents.
- The computed checksum is present on `SourceDocument`, event references, and stored object metadata.
- Duplicate registration does not publish a second `DocumentsUploadedEvent` unless an explicit `force_reprocess` option is set.
- Tests cover same-KB duplicate, cross-KB same content, different content same filename, and explicit reprocess.
- `pyright`, `ruff`, and ingestion tests pass.

---

## Story 2: Enforce Upload Policy At Registration

**As a platform owner**, I need ingestion to reject unsafe or unsupported submissions before they enter the pipeline.

**Current State**

- `DocumentSubmission` accepts either content bytes or URI, and currently allows both.
- `IngestionService.register_documents()` has no configured max size, allowed media types, allowed formats, filename rules, or per-KB upload limits.
- Local byte uploads use the submitted content type without independent validation.

**Implementation Notes**

- Extend `IngestionConfig` with upload policy fields:
  - `max_upload_bytes`
  - `allowed_content_types`
  - `allowed_formats`
  - `allow_remote_uris`
  - `allow_mixed_content_and_uri` defaulting to false
- Enforce exactly one source mode by default: content bytes or URI.
- Validate declared `document_format`, filename extension, and content type consistency.
- Reject empty byte payloads before storage.
- Keep parser-level errors for structurally invalid files; registration policy should handle obvious unsafe submissions only.

**Acceptance Criteria**

- Oversized byte submissions fail before object storage writes occur.
- Unsupported content types fail before events are published.
- Submissions with both `content` and `uri` fail unless explicitly enabled by config.
- Empty byte submissions fail with a structured registration error.
- Allowed formats are enforced consistently for file extension, content type, and explicit `document_format`.
- API-facing errors are deterministic and do not leak internal stack traces.
- Tests prove no storage side effects and no event publication on policy rejection.

---

## Story 3: Add Durable Publish Recovery For Registration And Parse Results

**As an operator**, I need ingestion to recover when storage succeeds but event publication fails, so documents do not disappear into an inconsistent state.

**Current State**

- `register_documents()` stores bytes and then publishes `DocumentsUploadedEvent`.
- `ingest_task()` stores parsed output and then publishes `DocumentsParsedEvent` or `DocumentsFailedEvent`.
- If event publish fails after storage, no retry record is persisted by ingestion itself.

**Implementation Notes**

- Add an ingestion outbox table/store for pending event publications.
- Write the outbox record in the same logical unit as the source/parsed metadata write where possible.
- Add a replay method for unpublished events.
- Ensure replay is idempotent by event id/correlation id.
- Keep event bus retry/dead-letter behavior in `events`/worker layers; ingestion owns the storage-to-publication recovery boundary.

**Acceptance Criteria**

- If `DocumentsUploadedEvent` publish fails, a pending outbox record remains with the document references.
- A replay call republishes the event and marks the outbox record delivered.
- Replaying an already delivered outbox record is a no-op.
- Parsed-document storage and `DocumentsParsedEvent` publication have the same recovery behavior.
- Failed parse events are also recorded when publication fails.
- Tests simulate event bus failure at registration and parsing boundaries.

---

## Story 4: Add Document-Level Status And Progress Tracking

**As an analyst**, I need reliable per-document ingestion status so the UI can show whether a document is uploaded, parsed, chunked, extracted, validated, failed, or ready.

**Current State**

- `SourceDocument.status` exists, but it is not backed by a durable status store.
- Workflow tracking exists outside ingestion, but ingestion does not expose a document-level progress projection.
- Stage events contain enough references to build progress, but the module does not own a status model.

**Implementation Notes**

- Add a `SourceDocumentStatusStore` protocol with in-memory and persistent implementations.
- Record status transitions for registration, parse started, parsed, failed, chunked, extracted, validated, graph updated, vector indexed, and ready.
- Include timestamps, error detail, parser metadata, and storage keys.
- Expose a read method for one document and a list method per KB.

**Acceptance Criteria**

- Every ingestion stage writes a monotonic status transition.
- Parse failures include a safe error type and safe message.
- Retried events do not regress a terminal status.
- A KB document listing can show current stage, last update, size, format, and error detail.
- Tests cover success flow, parse failure flow, duplicate/replay event flow, and status ordering.

---

## Story 5: Introduce Async I/O And Backpressure Boundaries

**As a platform operator**, I need ingestion workers to avoid blocking event loops or exhausting resources under large uploads and remote fetches.

**Current State**

- Object-store and event-bus calls are synchronous from `IngestionService`.
- `HttpxRemoteDocumentFetcher` uses `httpx.Client`, not `AsyncClient`.
- Downloads read full response content into memory.

**Implementation Notes**

- Add async protocols or async variants for object-store, event-bus, and remote fetch.
- Stream remote downloads with byte-count enforcement rather than loading unbounded content.
- Add worker-level concurrency limits for parse/chunk/extract stages.
- Keep sync adapters for tests and simple local mode if needed.

**Acceptance Criteria**

- Async ingestion paths are available for API/worker use.
- Remote downloads enforce max bytes while streaming.
- Worker concurrency is configurable and defaults to a conservative value.
- Large-file tests prove memory does not scale linearly beyond configured chunk/download buffering.
- Existing sync tests continue to pass or are migrated cleanly to async test equivalents.

---

## Story 6: Implement `LlmDocumentExtractor`

**As an analyst**, I need extraction to work on real narrative PDFs, DOCX letters, and notes where field names do not appear verbatim.

**Current State**

- `PatternDocumentExtractor` only matches configured property names in chunk text.
- The TODO in `backend/ingestion/extractor.py` calls out the missing LLM extractor.
- LLM clients and config exist elsewhere, but ingestion does not use them for extraction.

**Implementation Notes**

- Add an extractor that accepts:
  - entity definitions
  - relationship definitions
  - an LLM client/service
  - prompt templates
  - max chunks per request
  - retry/timeout settings
- Use structured output with a schema derived from config-defined entities and relationships.
- Preserve `ExtractionEvidence` with chunk id, quote, and rationale.
- Validate model output before creating candidates.
- Keep `PatternDocumentExtractor` as a deterministic fallback/test extractor.

**Acceptance Criteria**

- Narrative fixture documents produce entity candidates without literal JSON-style labels.
- Extractor output is valid `ExtractionResult`.
- Invalid or malformed LLM output is rejected with a safe extraction failure, not a crash.
- Prompts include domain entity and relationship definitions without hard-coded Medicare assumptions.
- Tests include deterministic fake LLM responses for success, invalid JSON, unsupported entity type, missing evidence, and retryable provider failure.
- The worker can select pattern or LLM extractor from config.

---

## Story 7: Add Entity Deduplication And Coreference Resolution

**As an analyst**, I need repeated mentions of the same provider, beneficiary, claim, or organization to become one canonical entity candidate.

**Current State**

- Each matched chunk can emit a separate `CandidateEntity`.
- There is no same-document duplicate merge step before validation.
- There is no cross-chunk coreference handling.

**Implementation Notes**

- Add a deduplication stage between extraction and validation.
- Use entity type plus configured key properties when present.
- Support fuzzy matching as a secondary strategy for entities without stable ids.
- Merge evidence lists and preserve contributing chunk ids.
- Record merge metadata for auditability.

**Acceptance Criteria**

- Multiple mentions with the same configured key property merge into one candidate.
- Conflicting values are preserved in metadata or surfaced as validation warnings.
- Evidence from all merged candidates remains available.
- Deduplication is deterministic.
- Tests cover exact-key merge, fuzzy non-key merge, conflicting property values, and no-merge for different entity types.

---

## Story 8: Add Confidence Thresholds And Calibration

**As a risk analyst**, I need low-confidence extraction candidates to be filtered or flagged before they become graph data.

**Current State**

- `PatternDocumentExtractor` assigns heuristic confidence in `backend/ingestion/extractor.py`.
- `ExtractionResultValidator` accepts candidates with any confidence from 0.0 to 1.0 if schema validation passes.
- There is no configured threshold per entity or relationship type.

**Implementation Notes**

- Extend ingestion config with default and per-type confidence thresholds.
- Apply thresholds in validation or a dedicated candidate filtering stage.
- Return filtered candidates in `ValidationReport` metadata or warnings, not silently discard them.
- Calibrate LLM extractor confidence separately from pattern extractor confidence.

**Acceptance Criteria**

- Candidates below the configured threshold do not appear in `valid_entities` or `valid_relationships`.
- Filtered candidates are reported with candidate id, type, confidence, and threshold.
- Per-type thresholds override the global threshold.
- Existing tests with high-confidence candidates still pass.
- Tests cover entity filtering, relationship filtering, per-type override, and threshold disabled mode.

---

## Story 9: Add Cross-Chunk Relationship Extraction

**As an investigator**, I need relationships to be detected when related entities are mentioned in different chunks of the same document.

**Current State**

- Relationship extraction only considers candidates emitted from the same chunk.
- `candidate_pairs()` ranks intra-chunk source/target pairs by span distance and confidence.

**Implementation Notes**

- Add a document-level relationship pass after all entity candidates are known.
- Use chunk order, source document id, entity key properties, and LLM relationship prompts where needed.
- Avoid all-to-all pair explosion by limiting candidate windows and using relationship definitions.
- Preserve evidence for both source and target mentions.

**Acceptance Criteria**

- A fixture with source entity in chunk 1 and target entity in chunk 2 produces a relationship when supported by text.
- Relationship candidates include evidence from both chunks.
- Same-chunk relationship behavior remains unchanged.
- Candidate windows are bounded and configurable.
- Tests cover adjacent chunks, distant chunks outside the window, self-referential relationships, and duplicate relationship suppression.

---

## Story 10: Strengthen Type-Aware Validation And Normalization

**As a downstream graph/vector consumer**, I need validated entities to contain normalized values that obey the domain schema.

**Current State**

- `shared.types.validate_entity()` enforces many constraints, including required fields, unexpected fields, patterns, and numeric bounds.
- Ingestion validation does not normalize dates, decimals, booleans, enums, nested objects, or lists before creating runtime `Entity` objects.
- Validator TODO still calls out richer type-aware validation.

**Implementation Notes**

- Add an ingestion normalization pass before `validate_entity()`.
- Normalize date strings to ISO date strings or date objects consistently with runtime serialization.
- Normalize decimal/integer/boolean values when safe.
- Reject ambiguous conversions with validation errors.
- Preserve original raw values in metadata when a conversion occurs.

**Acceptance Criteria**

- Date, integer, decimal, boolean, enum, list, and nested properties are normalized or rejected deterministically.
- Invalid conversions produce candidate-specific errors.
- Original values are available in metadata for audit.
- Tests cover valid and invalid values for every `PropertyType`.
- Runtime JSON serialization remains stable for validated reports.

---

## Story 11: Improve Parser Durability And Fidelity

**As an operator**, I need parsers to handle malformed and real-world documents with deterministic failures and useful metadata.

**Current State**

- Parsers are intentionally compact and unit tested.
- PDF support extracts text from digital PDFs; scanned/OCR workflows are absent.
- CSV and XLSX parsing are basic and do not expose row-level malformed-data warnings.
- HTML parsing extracts visible text but does not preserve links, headings as structured metadata, or tables.

**Implementation Notes**

- Add parser warnings to `ParsedDocument` or parser metadata.
- Add malformed row handling for CSV/XLSX with configurable strict/permissive modes.
- Add OCR adapter boundary for scanned PDFs.
- Preserve selected HTML structure such as headings, links, and table rows.
- Keep parser failures typed as `ParserError` subclasses where helpful.

**Acceptance Criteria**

- Malformed CSV rows are either rejected or recorded as warnings depending on config.
- XLSX rows shorter/longer than headers are handled deterministically.
- Scanned PDFs produce a typed “OCR required/unavailable” failure when OCR is disabled.
- HTML links and headings can be traced in parser metadata.
- Tests cover strict and permissive parser modes.

---

## Story 12: Harden Remote Document Fetching

**As a security owner**, I need remote ingestion to avoid SSRF, unsafe schemes, oversized downloads, and ambiguous source identity.

**Current State**

- `HttpxRemoteDocumentFetcher` requires HTTPS.
- There is no allowlist/blocklist for hosts or IP ranges.
- Response content is read fully into memory after checking content length.
- There is no support for authenticated fetches, signed URLs metadata, or remote checksum validation.

**Implementation Notes**

- Add remote fetch policy config:
  - allowed schemes
  - allowed host patterns
  - blocked private IP ranges
  - max redirects
  - max bytes
  - optional checksum
  - optional auth header secret env var
- Validate DNS/IP resolution before fetch and after redirects.
- Stream downloads with max-byte enforcement.
- Persist final URL, redirect count, response content type, size, and checksum.

**Acceptance Criteria**

- Private network targets are rejected by default.
- Non-HTTPS remains rejected unless config explicitly allows it.
- Redirects to blocked hosts are rejected.
- Oversized streaming responses stop before full download.
- Auth headers can be supplied from an env var without logging secret values.
- Tests cover allowed URL, blocked scheme, blocked host, blocked redirect, oversized response, and checksum mismatch.

---

## Story 13: Add First-Class Provenance And Evidence Storage

**As an auditor**, I need every graph entity and relationship created by ingestion to point back to the exact document, chunk, span, parser record, and extraction rationale.

**Current State**

- Candidate models contain evidence and chunk metadata.
- Validated runtime entities only copy some source metadata.
- Graph/vector deletion and evidence-pack work rely on provenance becoming more complete.

**Implementation Notes**

- Define a stable provenance model for parsed records, chunks, candidates, validated entities, and graph upserts.
- Carry provenance through `ValidationReport` into graph tasks.
- Persist evidence records addressable by `knowledge_base_id`, `source_document_id`, and entity/relationship id.
- Ensure provenance supports document deletion and reindexing.

**Acceptance Criteria**

- Every valid entity includes source document id, parsed document id, extraction result id, validation report id, chunk ids, and evidence spans when available.
- Every valid relationship includes provenance for both endpoints and relationship evidence.
- Evidence records can be queried by source document id and runtime entity id.
- Provenance survives serialization/deserialization through object storage.
- Tests prove graph upsert tasks receive complete provenance.

---

## Story 14: Add Observability, Metrics, And Audit Logs

**As an operator**, I need ingestion health and failures to be visible in logs, metrics, and traces.

**Current State**

- Worker-level tracing and metrics exist elsewhere.
- Ingestion module logic does not emit stage-specific metrics or structured audit records itself.

**Implementation Notes**

- Emit structured logs with KB id, source document id, stage, parser, duration, size, and outcome.
- Add metrics for documents registered, parsed, failed, bytes processed, parse duration, extraction duration, validation errors, and duplicate suppression.
- Add trace spans around storage, fetch, parse, chunk, extract, validate, and publish operations.
- Avoid logging document content or secrets.

**Acceptance Criteria**

- Successful and failed ingestion paths emit structured log records.
- Metrics are emitted with bounded cardinality labels.
- Trace spans include stage names and safe identifiers.
- Tests or smoke checks verify no raw document content appears in logs.
- Operational documentation lists metric names and expected labels.

---

## Story 15: Support Document Deletion, Reindexing, And Cleanup

**As a KB maintainer**, I need to remove or reprocess a document without leaving stale graph nodes, vectors, parsed artifacts, chunks, or extraction records.

**Current State**

- Architecture docs call out document-level graph/vector cleanup as future work.
- Ingestion stores source and parsed artifacts but does not own a cleanup/reindex contract.
- Provenance is not yet complete enough for safe cascading deletion.

**Implementation Notes**

- Add document lifecycle commands:
  - delete source document
  - reparse source document
  - re-extract source document
  - full reindex source document
- Use provenance records to identify downstream graph/vector/artifact data.
- Mark deleted documents before physical cleanup to avoid race conditions.
- Make cleanup idempotent.

**Acceptance Criteria**

- Deleting a document removes or tombstones source, parsed, chunk, extraction, validation, graph, and vector outputs.
- Reindexing a document replaces previous derived outputs without duplicate graph/vector records.
- Replaying an old event for a deleted document is ignored or dead-lettered safely.
- Tests cover delete, delete retry, reindex, and stale event replay.

---

## Story 16: Complete Configuration And Documentation For Production Modes

**As an engineer deploying chiliAI**, I need ingestion behavior to be configured and documented without reading source code.

**Current State**

- `ChunkingConfig` exists with strategy, size, overlap, minimum size, and record template.
- Upload policy, remote fetch policy, extractor selection, confidence thresholds, parser strictness, OCR, and tokenizer choice are not all represented in config.
- `docs/architecture.md` still has stale text saying HTML parser registration is future work.

**Implementation Notes**

- Extend `IngestionConfig` with production policy fields introduced by earlier stories.
- Update default YAML configs.
- Update architecture/onboarding docs with supported formats, policy defaults, and operational guidance.
- Document which defaults are safe for production and which are local/dev only.

**Acceptance Criteria**

- Every production ingestion behavior introduced by this backlog is configurable or explicitly documented as fixed.
- `docs/architecture.md` no longer lists completed HTML parser work as future work.
- Default configs validate.
- Config tests cover defaults and invalid policy combinations.
- Operator docs include example configs for local, internal-dev, and production modes.

---

## Story 17: Add Production Certification Test Suite

**As a release owner**, I need objective gates that prove ingestion is production-ready.

**Current State**

- `tests/ingestion` has strong unit coverage.
- E2E coverage exists through the worker pipeline, but production fixtures, load tests, and adversarial remote-fetch cases are limited.

**Implementation Notes**

- Add a production certification test target that runs:
  - parser fixture corpus
  - extraction quality fixtures
  - duplicate/idempotency tests
  - remote-fetch security tests
  - provenance round-trip tests
  - cleanup/reindex tests
  - pyright
  - ruff
  - coverage gate
- Add domain fixture sets for narrative PDF/DOCX/TXT, tabular CSV/XLSX, HTML, malformed files, and scanned-PDF/OCR-required files.
- Define minimum extraction quality metrics for deterministic fixture cases.

**Acceptance Criteria**

- A single documented command runs the ingestion production gate.
- Gate fails on pyright errors, ruff errors, coverage regression, parser fixture failure, provenance loss, or policy bypass.
- Fixture corpus includes at least one real-world-style narrative document per enabled target domain.
- CI can run fast unit gates on every PR and slower production certification gates on scheduled/pre-release jobs.
- Results are documented in release notes or a generated report.

---

## Suggested Execution Order

1. Story 2: upload policy enforcement.
2. Story 1: content hash idempotency.
3. Story 3: durable publish recovery.
4. Story 4: document status tracking.
5. Story 8: confidence thresholds.
6. Story 6: LLM extractor.
7. Story 7: deduplication/coreference.
8. Story 9: cross-chunk relationships.
9. Story 10: type-aware normalization.
10. Story 12: remote fetch hardening.
11. Story 11: parser durability and fidelity.
12. Story 13: provenance/evidence storage.
13. Story 15: deletion/reindex cleanup.
14. Story 14: observability.
15. Story 16: configuration/docs.
16. Story 17: production certification suite.
17. Story 5: async I/O and backpressure, unless production load requirements force this earlier.

## Production Readiness Definition

The ingestion module should be considered production-ready only when:

- Duplicate submissions are idempotent by default.
- Unsafe uploads and remote sources are rejected before pipeline execution.
- Storage/event publication boundaries are recoverable.
- Real narrative documents extract useful candidates through an LLM-backed extractor.
- Candidates are deduplicated, confidence-gated, normalized, and fully provenance-linked.
- Deletion and reindexing remove stale derived data.
- Operators have status, logs, metrics, traces, and documented configuration.
- The production certification suite passes in CI.
