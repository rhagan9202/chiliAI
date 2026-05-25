# ingestion backlog

> **Scope:** Document parsing (PDF/DOCX/HTML/JSON/TXT), chunking, LLM extraction, fallback chain, idempotency, observability.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story ingestion.01: Reconcile architecture.md HTML-parser milestone with shipped registration

**ID:** ingestion.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** platform maintainer,
**I need** `docs/architecture.md` to stop describing HTML-parser registration as a "Next milestone" when the parser is already wired,
**so that** new contributors do not chase a phantom gap and the parser inventory remains a trustworthy onboarding reference.

### Current State
- `HtmlParser` is implemented at `backend/ingestion/parsers/html.py:99-125` and registered in `backend/ingestion/parsers/registry.py:47-57` via `create_default_registry()`.
- `docs/architecture.md` §14.3 still lists HTML parser registration as future work (verify exact line during execution; the milestone bullet predates the shipped registration).
- The real residual HTML gap (table/heading fidelity) is captured separately as `ingestion.02`; this story is purely a doc reconcile.

### Acceptance Criteria
- [ ] `docs/architecture.md` §14.3 no longer claims HTML parser registration is pending; the bullet is either deleted or rewritten to point at `ingestion.02` as the live follow-on.
- [ ] `backend/ingestion/README.md` parser inventory section lists HTML alongside PDF/DOCX/CSV/XLSX/JSON/TXT with the correct registration status.
- [ ] No other doc (root `README.md`, `backend/README.md`, `CLAUDE.md`, `.github/copilot-instructions.md`) repeats the stale "HTML parser pending" claim.

### Verification
- `rg -n "HTML parser" docs/ backend/ CLAUDE.md .github/` returns only the rewritten bullet plus the `ingestion.02` follow-on reference.
- Reviewer reads the updated §14.3 paragraph and confirms it matches `parsers/registry.py:47-57`.

### Code touch points
- `docs/architecture.md` (modify)
- `backend/ingestion/README.md` (modify)
- `backend/README.md` (modify, if it cites the stale milestone)
- `.github/copilot-instructions.md` (modify, if it cites the stale milestone)

---

## Story ingestion.02: Strengthen HTML parser fidelity beyond visible text

**ID:** ingestion.02
**Status:** planned
**Prerequisites:** [ingestion.01]
**Unblocks:** []
**Estimated size:** M

**As a** policy/news ingestion operator,
**I need** the HTML parser to preserve headings, links, and table structure (not just visible paragraph text),
**so that** downstream chunking and extraction can use document structure as signal instead of seeing a flattened text blob.

### Current State
- `_VisibleTextParser` at `backend/ingestion/parsers/html.py:14-97` collects only `handle_data` text into block-separated paragraphs.
- `handle_starttag` (`html.py:56-64`) explicitly ignores all attributes (`del attrs`) so anchor `href` targets are dropped.
- Tables are flattened to their text content with no row/column structure; `<h1>`–`<h6>` are demoted to plain paragraph text with no level marker.
- `HtmlParser.parse` (`html.py:106-125`) returns only `text_content` and a single `visible_text_length` metadata field.

### Acceptance Criteria
- [ ] Headings are preserved with a leading marker (e.g. `# `, `## `) so downstream chunking can detect section boundaries.
- [ ] Anchor text retains link targets in a normalized form (e.g. `[text](url)` markdown-style) for entity-extraction context.
- [ ] Tables are emitted as markdown-style pipe tables (or stored as `StructuredRecord` rows on `ParsedDocument.records`) so they survive chunking intact.
- [ ] `ParsedDocument.parser_metadata` carries counts (`heading_count`, `link_count`, `table_count`) for observability.
- [ ] New unit tests cover heading fidelity, link extraction, table preservation, nested-table edge cases, and the existing visible-text behavior remains green.
- [ ] `backend/ingestion/README.md` documents the new fidelity guarantees.

### Verification
- `pytest backend/tests/ingestion/parsers/test_html_parser.py -v` green; coverage ≥ 85% on `backend/ingestion/parsers/html.py`.
- A reviewer runs the parser against a representative news/policy HTML fixture and confirms headings, tables, and links appear in `text_content` or `records`.

### Code touch points
- `backend/ingestion/parsers/html.py` (modify)
- `backend/tests/ingestion/parsers/test_html_parser.py` (new or modify)
- `backend/tests/ingestion/parsers/fixtures/html/` (new fixtures)
- `backend/ingestion/README.md` (modify)

---

## Story ingestion.03: Add PDF OCR fallback adapter boundary for scanned documents

**ID:** ingestion.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L

**As a** Medicare-fraud analyst ingesting scanned policy or claim PDFs,
**I need** the PDF parser to fall back to an OCR adapter when text extraction yields nothing,
**so that** image-only PDFs become parseable instead of failing outright with `ParserError("PDF does not contain extractable text.")`.

### Current State
- `PdfParser.parse` at `backend/ingestion/parsers/pdf.py:23-46` calls `pypdf` and raises `ParserError` (line 34-35) whenever the concatenated page text is empty.
- No OCR adapter boundary exists; `pyproject.toml` declares no OCR optional extra.
- Architecture.md §5/§6 does not currently commit to OCR; this story includes the architectural decision check (Open question 1 from the Wave 1 epic draft).

### Acceptance Criteria
- [ ] `OcrAdapterProtocol` lives in `backend/ingestion/parsers/protocols.py` with a `recognize(content: bytes) -> str` (or page-level) signature, dependency-light.
- [ ] At least one concrete adapter (e.g. `TesseractOcrAdapter`) lives under `backend/ingestion/parsers/adapters/` behind an optional `[ocr]` extra in `pyproject.toml`; the test stub adapter ships in tree for unit tests.
- [ ] `PdfParser` accepts an optional `ocr_adapter` parameter; when text extraction is empty AND an adapter is configured, it OCRs page-by-page and emits the OCR text with `parser_metadata["ocr_used"] = True`.
- [ ] When no adapter is configured the parser continues to raise `ParserError` (unchanged behavior) so opt-in is explicit.
- [ ] `docs/architecture.md` §5/§6 adds a single sentence stating OCR is a supported optional adapter with the operator policy (opt-in per deployment).
- [ ] Unit tests cover: text-PDF (no OCR), image-PDF with adapter (OCR used), image-PDF without adapter (ParserError), mixed-page PDF (OCR fills empty pages only).

### Verification
- `pytest backend/tests/ingestion/parsers/test_pdf_parser.py -v` green.
- `pyright --strict` clean across `backend/ingestion/parsers/`.
- `pytest -m integration backend/tests/ingestion/parsers/test_pdf_ocr_integration.py` skipped when `[ocr]` extra is not installed; green when installed.

### Code touch points
- `backend/ingestion/parsers/pdf.py` (modify)
- `backend/ingestion/parsers/protocols.py` (modify)
- `backend/ingestion/parsers/adapters/__init__.py` (new)
- `backend/ingestion/parsers/adapters/tesseract.py` (new)
- `backend/pyproject.toml` (modify — add `[ocr]` extra)
- `backend/tests/ingestion/parsers/test_pdf_parser.py` (modify)
- `backend/tests/ingestion/parsers/test_pdf_ocr_integration.py` (new)
- `docs/architecture.md` (modify)

---

## Story ingestion.04: Surface per-row parser warnings for CSV and XLSX

**ID:** ingestion.04
**Status:** planned
**Prerequisites:** [ingestion.25]
**Unblocks:** []
**Estimated size:** M

**As a** records-ingestion operator,
**I need** CSV/XLSX parsers to emit typed per-row warnings (malformed rows, charset fallback, blank columns, type-coercion failures) instead of either silently dropping rows or hard-failing the whole file,
**so that** the Ingestion Studio can surface a "12 rows had warnings / 3 rows skipped" summary instead of "file failed."

### Current State
- `backend/ingestion/parsers/csv.py` and `backend/ingestion/parsers/xlsx.py` are basic parsers that produce `StructuredRecord` rows; per-row diagnostics flow only via free-form `parser_metadata`.
- There is no strict/permissive mode flag; behavior on malformed rows is parser-dependent and not surfaced to callers.
- `ParsedDocument.parser_metadata` (`backend/ingestion/models.py:80-101`) is a free-form `dict[str, object]` with no typed warnings channel — `ingestion.25` introduces that channel and this story consumes it.

### Acceptance Criteria
- [ ] `CsvParser` and `XlsxParser` accept a `mode: Literal["strict", "permissive"]` argument (default `permissive`) and emit `ParserWarning` entries (per `ingestion.25` contract) for each non-fatal row issue.
- [ ] Warning categories cover: malformed CSV row, type-coercion failure, blank required cell, charset fallback, header mismatch.
- [ ] `strict` mode raises `ParserError` on the first warning; `permissive` mode continues and reports warnings.
- [ ] Each warning carries `row_index`, `column_name` (when applicable), and a stable `code` (e.g. `csv.malformed_row`, `xlsx.type_coercion_failed`).
- [ ] Unit tests cover both modes for both parsers, including the warning-count summary surfaced to `ParsedDocument`.

### Verification
- `pytest backend/tests/ingestion/parsers/test_csv_parser.py backend/tests/ingestion/parsers/test_xlsx_parser.py -v` green.
- Coverage ≥ 85% on `backend/ingestion/parsers/csv.py` and `backend/ingestion/parsers/xlsx.py`.

### Code touch points
- `backend/ingestion/parsers/csv.py` (modify)
- `backend/ingestion/parsers/xlsx.py` (modify)
- `backend/tests/ingestion/parsers/test_csv_parser.py` (modify)
- `backend/tests/ingestion/parsers/test_xlsx_parser.py` (modify)

---

## Story ingestion.05: Add transactional-outbox recovery for storage-then-publish failures

**ID:** ingestion.05
**Status:** planned
**Prerequisites:** [events.02, database.04]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As a** worker operating the documents flow,
**I need** the storage-write + event-publish path to be atomic via an outbox so that a publish failure after a successful storage write does not strand the document,
**so that** the worker can replay missed events and the Ingestion Studio's per-document status never disagrees with the durable record.

### Current State
- `IngestionService.register_documents` (`backend/ingestion/service.py:46-165`) writes to object storage then publishes `DocumentsUploadedEvent`; a publish failure after the put leaves the document stranded with no replay record (see TODO at `service.py:30-33`).
- `ingest_task` (`service.py:167-236`) has the same shape for parsed and failure events.
- No outbox table exists today; events go straight from in-process publisher to Redis Streams.

### Acceptance Criteria
- [ ] An `ingestion_outbox` table (or equivalent durable record under `backend/database/`) captures `(event_type, payload, status, attempt_count, last_error, created_at, dispatched_at)`.
- [ ] `IngestionService.register_documents`, `ingest_task`, and the failure-publish path write the event to the outbox inside the same transaction (or with the same idempotency key) as the storage write, then dispatch.
- [ ] A relay loop (worker-side) reads `status='pending'` rows, publishes to the event bus, and marks them `dispatched` or increments `attempt_count` with backoff.
- [ ] Dispatch is idempotent: re-publishing an already-dispatched event is a no-op for downstream consumers (relies on existing event correlation IDs).
- [ ] A failure-injection test (mock event-bus raising on `publish`) verifies the outbox row remains `pending` and the relay successfully dispatches on retry.
- [ ] Metrics: `ingestion_outbox_pending_count`, `ingestion_outbox_dispatched_total`, `ingestion_outbox_failed_total` (cross-edge to `_observability.md`).

### Verification
- `pytest backend/tests/ingestion/test_service_outbox.py -v` green including failure-injection cases.
- `pytest backend/tests/integration/test_ingestion_outbox_relay.py -v` green against a real Redis Streams instance.
- Manual: kill the event bus mid-publish, restart it, observe the relay drain pending rows.

### Code touch points
- `backend/database/models/ingestion_outbox.py` (new)
- `backend/database/migrations/` (new Alembic revision)
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/outbox.py` (new — relay loop)
- `backend/agent/coordinator.py` (modify — register relay)
- `backend/tests/ingestion/test_service_outbox.py` (new)
- `backend/tests/integration/test_ingestion_outbox_relay.py` (new)

---

## Story ingestion.06: Move ingestion service and remote fetcher to async I/O with backpressure

**ID:** ingestion.06
**Status:** planned
**Prerequisites:** [ingestion.05, storage.05]
**Unblocks:** []
**Estimated size:** XL

**As a** worker handling large uploads and remote fetches under load,
**I need** the ingestion service and `HttpxRemoteDocumentFetcher` to use async I/O with bounded concurrency,
**so that** a single 200 MB upload does not block the event loop and a slow remote host does not stall the entire worker.

### Current State
- `IngestionService` (`backend/ingestion/service.py:35-274`) is fully synchronous; `register_documents` and `ingest_task` block the calling task on `object_store.put_bytes`, `object_store.get_bytes`, and `event_bus.publish`.
- `HttpxRemoteDocumentFetcher.fetch` (`backend/ingestion/parsers/remote.py:34-68`) uses `httpx.Client.get` (sync), reads the full response into memory (`response.content` at line 49), and offers no concurrency cap.
- No bulkhead, no per-host concurrency limit, no streaming download.

### Acceptance Criteria
- [ ] Story is split into M-sized increments before merge (XL split required by §5 field rules); split plan documented in the implementation plan.
- [ ] `IngestionService` exposes async public methods (`async def register_documents`, `async def ingest_task`); sync callers go through a thin adapter so the FastAPI router and worker can both consume cleanly.
- [ ] `ObjectStoreProtocol` gains async methods (or the service uses `asyncio.to_thread` if the protocol stays sync, documented decision).
- [ ] `HttpxRemoteDocumentFetcher` uses `httpx.AsyncClient`, streams the response body, enforces `max_bytes` mid-stream, and rejects oversized bodies before fully reading.
- [ ] A per-worker `asyncio.Semaphore` caps in-flight ingest tasks (default 16, configurable via `IngestionConfig.max_concurrent_tasks`).
- [ ] Async smoke tests confirm two concurrent 50 MB ingests do not serialize, and remote-fetch streaming aborts mid-stream when size cap is exceeded.

### Verification
- `pytest backend/tests/ingestion/test_service_async.py -v` green.
- `pytest backend/tests/ingestion/parsers/test_remote_async.py -v` green including the streaming-abort case.
- `pyright --strict` clean on `backend/ingestion/`.

### Code touch points
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/parsers/remote.py` (modify)
- `backend/ingestion/protocols.py` (modify, if async surface added)
- `backend/shared/protocols.py` (modify, if `ObjectStoreProtocol` gains async methods)
- `backend/api/routers/knowledgebases.py` (modify — adopt async service)
- `backend/agent/coordinator.py` (modify — adopt async service)
- `backend/tests/ingestion/test_service_async.py` (new)
- `backend/tests/ingestion/parsers/test_remote_async.py` (new)

---

## Story ingestion.07: Harden remote document fetching against SSRF and oversized payloads

**ID:** ingestion.07
**Status:** planned
**Prerequisites:** [ingestion.06, _security.06]
**Unblocks:** []
**Estimated size:** M

**As a** security-conscious operator,
**I need** the remote-fetch path to enforce a host allowlist, block private-IP/loopback/link-local targets, re-check the target after redirects, and refuse to authenticate against unknown hosts,
**so that** a tenant-supplied URL cannot pivot inside the cluster network or exfiltrate credentials.

### Current State
- `HttpxRemoteDocumentFetcher.__init__` (`backend/ingestion/parsers/remote.py:23-32`) accepts a timeout and `max_bytes` only.
- `fetch` (line 34-68) enforces HTTPS via `parsed.scheme.lower() != "https"` and a single `content-length`/body-size cap; no host allowlist, no IP-range deny-list, no redirect-target re-check, no authenticated-fetch story.
- `follow_redirects=True` is set on the default client (line 41) without re-validating the post-redirect target.

### Acceptance Criteria
- [ ] `RemoteFetchPolicy` config object specifies `allowed_hosts: list[str]` (exact + suffix match), `denied_ip_ranges: list[IPv4Network | IPv6Network]` (defaults block RFC 1918, loopback, link-local, multicast, `0.0.0.0/0` if allowlist mode is enforced).
- [ ] Pre-flight DNS resolution checks every resolved IP against the deny-list; redirects re-run the full host + IP check.
- [ ] Credentials (basic auth, bearer tokens) are only attached when the host matches a configured `authenticated_hosts` allowlist; redirects strip credentials by default.
- [ ] `content-length` header is no longer trusted as authoritative — body-size enforcement happens mid-stream (relies on `ingestion.06` async streaming).
- [ ] Audit log entry on every blocked request (cross-edge to `_security.07` audit log).
- [ ] Unit tests cover: blocked private IP, blocked loopback, redirect to private IP, redirect stripping credentials, allowlist hit/miss, oversized streaming abort.

### Verification
- `pytest backend/tests/ingestion/parsers/test_remote_ssrf.py -v` green.
- A reviewer attempts to fetch `http://169.254.169.254/` (cloud metadata) and confirms the request is rejected at policy time with no DNS lookup leak (or with the lookup but no connection).

### Code touch points
- `backend/ingestion/parsers/remote.py` (modify)
- `backend/ingestion/parsers/remote_policy.py` (new)
- `backend/config/schema.py` (modify — `IngestionConfig.remote_fetch_policy`)
- `backend/tests/ingestion/parsers/test_remote_ssrf.py` (new)

---

## Story ingestion.08: Make extractor strategy and natural-key derivation explicit in IngestionConfig

**ID:** ingestion.08
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** []
**Estimated size:** S

**As a** domain-config author,
**I need** to declare extractor strategy (`pattern` | `llm` | `auto`) and per-entity natural keys via `IngestionConfig` rather than via dependency-injection happenstance,
**so that** operators can pin or A/B the extractor without surgery and reproducibly recreate extraction behavior from config alone.

### Current State
- `create_document_extractor` (`backend/ingestion/extractor.py:438-468`) chooses `LlmDocumentExtractor` vs `PatternDocumentExtractor` purely based on whether an `LlmClientProtocol` is injected.
- Natural keys are derived from `EntityDefinition.natural_key` when an LLM client is present (line 458-462), but there is no override hook in `IngestionConfig`.
- There is no `IngestionConfig.extractor.strategy` field; operators cannot force pattern mode while an LLM client is configured.

### Acceptance Criteria
- [ ] `IngestionConfig.extractor` adds a `strategy: Literal["pattern", "llm", "auto"]` field (default `auto`, preserving today's behavior).
- [ ] `IngestionConfig.extractor.natural_key_overrides: dict[str, list[str]]` (default `{}`) lets operators override per-entity natural keys without editing `EntityDefinition`.
- [ ] `create_document_extractor` honors `strategy="pattern"` even when an LLM client is injected (and raises a configuration error if `strategy="llm"` is set without a client).
- [ ] `docs/architecture.md` §5.2 / §6 documents the new strategy field and the precedence (overrides > definition default).
- [ ] Unit tests cover all three strategy values and the natural-key override path.

### Verification
- `pytest backend/tests/ingestion/test_extractor.py -v` green including the new strategy/override cases.
- `pyright --strict` clean.

### Code touch points
- `backend/config/schema.py` (modify)
- `backend/ingestion/extractor.py` (modify)
- `backend/tests/ingestion/test_extractor.py` (modify)
- `docs/architecture.md` (modify)

---

## Story ingestion.09: Version and externalize LLM extractor prompts

**ID:** ingestion.09
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** []
**Estimated size:** M

**As a** prompt engineer iterating on extraction quality,
**I need** the LLM extractor's system/user prompts to live in versioned files under `backend/ingestion/prompts/` and to stamp a `prompt_version` on every candidate,
**so that** prompt edits are reproducible, A/B comparable, and traceable from any candidate back to the exact prompt that produced it.

### Current State
- `LlmDocumentExtractor._build_prompt` (`backend/ingestion/extractor.py:318-346`) hardcodes the system and user prompt strings inline.
- `extraction_method="llm_v1"` is stamped on every candidate (`extractor.py:381`), but there is no separate `prompt_version` field on `CandidateEntity.metadata` — silent prompt edits are indistinguishable downstream.
- No prompt-template directory exists under `backend/ingestion/`.

### Acceptance Criteria
- [ ] Prompts live in `backend/ingestion/prompts/<name>/v<N>/system.txt` and `user.txt` with a `manifest.yaml` carrying `version`, `description`, and `created_at`.
- [ ] `LlmDocumentExtractor` accepts a `prompt_template: PromptTemplate` parameter (default loaded from `IngestionConfig.extractor.prompt_template`).
- [ ] Every `CandidateEntity` and `CandidateRelationship` emitted by the LLM extractor carries `metadata["prompt_version"] = "<name>:v<N>"`.
- [ ] Changing prompt content requires bumping the version (CI lint validates `version` matches the manifest version; mismatch fails).
- [ ] Existing tests pass against the default versioned prompt; a new test verifies `prompt_version` propagation.

### Verification
- `pytest backend/tests/ingestion/test_extractor.py backend/tests/ingestion/test_prompts.py -v` green.
- Coverage ≥ 85% on `backend/ingestion/prompts/`.

### Code touch points
- `backend/ingestion/prompts/__init__.py` (new)
- `backend/ingestion/prompts/extractor/v1/system.txt` (new)
- `backend/ingestion/prompts/extractor/v1/user.txt` (new)
- `backend/ingestion/prompts/extractor/v1/manifest.yaml` (new)
- `backend/ingestion/extractor.py` (modify)
- `backend/config/schema.py` (modify — `IngestionConfig.extractor.prompt_template`)
- `backend/tests/ingestion/test_prompts.py` (new)
- `backend/tests/ingestion/test_extractor.py` (modify)

---

## Story ingestion.10: Add JSON-mode retry, schema coercion, and structured-output guardrails to the LLM extractor

**ID:** ingestion.10
**Status:** planned
**Prerequisites:** [ingestion.09, llm.06]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As an** extraction-pipeline operator,
**I need** the LLM extractor to use provider-native JSON/structured-output mode and to retry once with a stricter prompt on JSON decode failure before dropping a chunk,
**so that** transient prompt-format misses do not silently lose extraction work.

### Current State
- `LlmDocumentExtractor._extract_chunk` (`backend/ingestion/extractor.py:265-316`) issues a single `generate()` call.
- On `JSONDecodeError` (line 290-291) it returns an empty candidate list with a warning string — no retry.
- The only JSON pre-processing is `_strip_json_fences` (`extractor.py:41-50`); no use of provider-native `response_format: json` or structured-output schema.
- Schema coercion is absent: non-dict properties from the LLM (e.g. integer for a string field) propagate to `validate_entity` which then rejects the whole entity.

### Acceptance Criteria
- [ ] `LlmDocumentExtractor` calls `generate()` with a typed structured-output request that opts into provider-native JSON mode where available (cross-edge to `llm.06` which adds the field to `GenerationRequest`).
- [ ] On `JSONDecodeError` or schema mismatch, the extractor performs exactly one retry with a stricter "JSON only — no prose" prompt; on second failure it logs the failure with chunk id and continues.
- [ ] A schema-coercion pass converts simple type mismatches (e.g. integer property declared as string) instead of dropping the whole entity; coercion failures are warnings, not silent drops.
- [ ] Per-chunk metrics: `extraction.json_retry_total`, `extraction.json_failed_total`, `extraction.coercion_total` (cross-edge to `_observability.md`).
- [ ] Unit tests cover: first-try valid JSON, first-try invalid then retry succeeds, both attempts fail (warning emitted, chunk dropped), schema coercion succeeds, coercion fails (entity dropped but chunk continues).

### Verification
- `pytest backend/tests/ingestion/test_llm_extractor.py -v` green including the new retry and coercion cases.
- Coverage ≥ 85% on `backend/ingestion/extractor.py`.

### Code touch points
- `backend/ingestion/extractor.py` (modify)
- `backend/tests/ingestion/test_llm_extractor.py` (modify)

---

## Story ingestion.11: Wire FallbackLlmClient into extractor retry path AND extract cross-chunk relationships

**ID:** ingestion.11
**Status:** planned
**Prerequisites:** [ingestion.10, llm.04, llm.07]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As an** extraction operator,
**I need** the LLM extractor to (a) actually exercise the configured `FallbackLlmClient` chain on transient provider exhaustion and degrade to `PatternDocumentExtractor` as the final fallback, and (b) emit relationships across chunks of the same document (not just within a chunk),
**so that** a provider outage does not drop the whole document and entities that co-occur across chunks still produce graph edges.

### Current State
- `FallbackLlmClient` is implemented at `backend/llm/adapters/fallback.py:15-50` and wired by `backend/llm/factory.py:80-90`; the extractor receives an `LlmClientProtocol` that is already a fallback chain when configured.
- However, `LlmDocumentExtractor._extract_chunk` (`backend/ingestion/extractor.py:285-286`) catches `LlmProviderError` and returns an empty list with a warning — there is no explicit chain-exhausted handling, no degrade to `PatternDocumentExtractor` for the failed chunk, and no record of which provider succeeded.
- `PatternDocumentExtractor._extract_relationships_from_chunk` (`extractor.py:162-203`) and `LlmDocumentExtractor._extract_relationships` (`extractor.py:404-435`) both only consider candidates that share `chunk_id`. Entities in different chunks of the same document never produce relationships.

### Acceptance Criteria
- [ ] Story is split into two sub-stories before merge if combined size exceeds L (target: ingestion.11a = fallback wiring, ingestion.11b = cross-chunk relationships); the split is captured in the implementation plan but both land before this ID flips to `done`.
- [ ] On `LlmProviderError` exhaustion the extractor re-attempts the chunk using `PatternDocumentExtractor` as a final degrade, records `metadata["fallback_used"] = "pattern"` on every candidate produced from the degraded path, and emits a `extraction.provider_chain_exhausted` metric.
- [ ] Every successful LLM candidate carries `metadata["provider"]` identifying which chain member returned the result (requires `llm.07` provider-attribution surface).
- [ ] Both `PatternDocumentExtractor` and `LlmDocumentExtractor` emit a cross-chunk relationship pass: after per-chunk extraction, candidates are grouped by `(type, natural_key)` across the whole document and the configured relationship definitions are applied across the merged set.
- [ ] Cross-chunk relationships carry `metadata["scope"] = "cross_chunk"` and `evidence` referencing both source chunks.
- [ ] Unit tests cover: chain-exhausted degrade, partial chain success, cross-chunk relationship emission, no false positives when entities lack a natural key.

### Verification
- `pytest backend/tests/ingestion/test_llm_extractor.py backend/tests/ingestion/test_pattern_extractor.py -v` green including the new cases.
- Coverage ≥ 85% on `backend/ingestion/extractor.py`.

### Code touch points
- `backend/ingestion/extractor.py` (modify)
- `backend/tests/ingestion/test_llm_extractor.py` (modify)
- `backend/tests/ingestion/test_pattern_extractor.py` (modify)

---

## Story ingestion.12: Add same-document entity dedup and fuzzy coreference for the pattern extractor

**ID:** ingestion.12
**Status:** planned
**Prerequisites:** [ingestion.11, shared.07]
**Unblocks:** []
**Estimated size:** L

**As an** extraction-quality operator,
**I need** the pattern extractor to deduplicate entities across chunks of the same document AND apply fuzzy coreference for entities that do not have a configured natural key,
**so that** a single provider mentioned five times across a document produces one candidate, not five, and "John Q. Smith" and "John Smith" are recognized as the same person without a hardcoded NPI.

### Current State
- `PatternDocumentExtractor._extract_entities_from_chunk` (`backend/ingestion/extractor.py:102-160`) emits a fresh `CandidateEntity` per matching chunk; no dedup pass exists.
- `LlmDocumentExtractor` deduplicates within a single chunk via natural key (`extractor.py:386-402`) but only against the per-document `seen_natural_keys` accumulator — entities without a configured `natural_key` are never merged.
- No coreference module exists; `shared.types` does not expose a coreference contract (Open question 2 from the Wave 1 epic draft is preserved here: the resolver may live under `ingestion/` or be promoted to `analytics/entity_resolution/` — decided during execution).

### Acceptance Criteria
- [ ] Pattern extractor runs a post-pass that merges candidates with matching natural keys (when configured) into a single candidate per `(type, natural_key)` per document.
- [ ] A `FuzzyCoreferenceResolver` (location TBD per open question) performs name-normalization + edit-distance matching for entities lacking a natural key; threshold configurable via `IngestionConfig.extractor.coreference_threshold` (default 0.85).
- [ ] Merged candidates carry `metadata["merged_from"] = [<chunk_ids>]` and the union of evidence spans.
- [ ] Confidence on merged candidates is the max of contributing candidates (not the mean — preserves best-signal).
- [ ] Unit tests cover: exact natural-key merge, fuzzy match above threshold, fuzzy match below threshold (stays separate), conflicting property values (recorded as warning).

### Verification
- `pytest backend/tests/ingestion/test_pattern_extractor.py backend/tests/ingestion/test_coreference.py -v` green.
- Coverage ≥ 85% on the coreference module.

### Code touch points
- `backend/ingestion/extractor.py` (modify)
- `backend/ingestion/coreference.py` (new — or `backend/analytics/entity_resolution/coreference.py` per open question)
- `backend/config/schema.py` (modify — coreference threshold)
- `backend/tests/ingestion/test_pattern_extractor.py` (modify)
- `backend/tests/ingestion/test_coreference.py` (new)

---

## Story ingestion.13: Add confidence thresholds with per-type calibration to extraction validation

**ID:** ingestion.13
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** []
**Estimated size:** M

**As an** extraction-quality operator,
**I need** the validator to drop candidates below a configurable confidence threshold, with per-`EntityDefinition` overrides,
**so that** low-confidence pattern matches never enter the graph and we can tune precision per entity type.

### Current State
- `ExtractionResultValidator.validate_extraction` (`backend/ingestion/validator.py:76-112`) accepts any candidate with `confidence >= 0.0`.
- The model's `confidence` field is `Field(ge=0.0, le=1.0)` (`backend/ingestion/models.py:165`) — the floor is structural, not policy.
- A TODO at `validator.py:62-66` flags the missing confidence-threshold filter explicitly.
- `IngestionConfig` has no `confidence_thresholds` field today.

### Acceptance Criteria
- [ ] `IngestionConfig.validation.confidence_thresholds` adds `default: float` (default 0.5) and `overrides: dict[str, float]` (keyed by `EntityDefinition.name`).
- [ ] `ExtractionResultValidator` drops candidates whose confidence < the applicable threshold; dropped count is reported on `ValidationReport`.
- [ ] Per-entity-type overrides take precedence over the default.
- [ ] Relationship candidates inherit the stricter of source/target entity thresholds.
- [ ] Metric `validation.confidence_drop_total{entity_type}` (cross-edge to `_observability.md`).
- [ ] Unit tests cover: default threshold drops, per-type override kept, override allows lower than default, relationship inherits stricter floor.

### Verification
- `pytest backend/tests/ingestion/test_validator.py -v` green.
- Coverage ≥ 85% on `backend/ingestion/validator.py`.

### Code touch points
- `backend/ingestion/validator.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/ingestion/test_validator.py` (modify)

---

## Story ingestion.14: Add type-aware property normalization before validate_entity

**ID:** ingestion.14
**Status:** planned
**Prerequisites:** [shared.06]
**Unblocks:** []
**Estimated size:** M

**As a** schema steward,
**I need** the validator to normalize extracted property values (dates → ISO 8601, decimals → typed Decimal, booleans → bool, enums → canonical form) against `EntityDefinition.properties[*].type` BEFORE calling `validate_entity`,
**so that** regionally formatted dates, scientific notation, and trailing whitespace stop causing valid entities to be rejected as schema mismatches.

### Current State
- `_entity_from_candidate` (`backend/ingestion/validator.py:23-37`) passes raw extractor `properties` straight into `Entity`.
- `validate_entity` in `shared.types` then enforces the schema; there is no normalization pass between the candidate's raw value and the schema check.
- TODO at `validator.py:62-66` explicitly flags missing property-type-aware value validation (date format, numeric ranges, enum membership).
- No `PropertyNormalizer` module exists today.

### Acceptance Criteria
- [ ] A `PropertyNormalizer` (`backend/ingestion/normalization.py`) accepts a value + `PropertyDefinition.type` and returns either a normalized value or a `NormalizationError`.
- [ ] Supported normalizers: `date` (ISO/regional/Unix epoch → `date`), `datetime` (ISO + common variants → tz-aware `datetime`), `decimal` (comma/period decimal separator → `Decimal`), `boolean` (`yes/no/true/false/1/0`), `enum` (case-insensitive match to allowed values from config), `list[T]` (per-element normalization).
- [ ] `ExtractionResultValidator` runs normalization before `validate_entity`; normalization failures are added to `entity_errors` with a `normalization_failed` category so the operator can distinguish from schema-rejection.
- [ ] Unit tests cover each normalizer success and failure case, plus the validator integration test that proves a regionally formatted date is accepted after this change.

### Verification
- `pytest backend/tests/ingestion/test_normalization.py backend/tests/ingestion/test_validator.py -v` green.
- Coverage ≥ 85% on `backend/ingestion/normalization.py`.

### Code touch points
- `backend/ingestion/normalization.py` (new)
- `backend/ingestion/validator.py` (modify)
- `backend/tests/ingestion/test_normalization.py` (new)
- `backend/tests/ingestion/test_validator.py` (modify)

---

## Story ingestion.15: Enforce upload policy at the ingestion-service layer (size, MIME sniff, format/extension consistency)

**ID:** ingestion.15
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator with non-API ingestion callers (workers, batch loaders),
**I need** the same upload-policy checks the API performs (size, allowed content types, MIME sniff, extension/declared-type consistency) to live at the `IngestionService` boundary,
**so that** a worker or batch loader cannot bypass policy by skipping the FastAPI route.

### Current State
- API enforces `max_file_size_mb` and `allowed_content_types` at `backend/api/routers/knowledgebases.py:402-421`.
- `IngestionService.register_documents` (`backend/ingestion/service.py:46-165`) trusts the submission's declared `content_type` (line 70) with no byte-magic sniff and no consistency check between `document_format`, file extension, and declared content type.
- Non-API callers (worker test harnesses, future batch ingestion) bypass all API-level checks today.

### Acceptance Criteria
- [ ] A `UploadPolicyEnforcer` (`backend/ingestion/policy.py`) consumes `IngestionConfig.validation` and performs: byte-magic MIME sniff via `python-magic` (or pure-Python `magic` extra), max-bytes check, allowed-content-type check, `(declared_content_type, sniffed_content_type, document_format, filename_extension)` consistency check.
- [ ] `IngestionService.register_documents` invokes the enforcer for every submission; mismatch raises a typed `UploadPolicyError` that the API surfaces as 415 or 413 as appropriate.
- [ ] The API router delegates to the service enforcer rather than duplicating checks (single source of truth).
- [ ] Sniffing happens on the first N bytes (default 8 KB) so it works under streaming uploads (cross-edge to `ingestion.23`).
- [ ] Unit tests cover every check: oversized, disallowed type, MIME-sniff mismatch, extension mismatch, no-extension edge case.

### Verification
- `pytest backend/tests/ingestion/test_policy.py backend/tests/ingestion/test_service.py -v` green.
- `pytest backend/tests/api/test_kb_documents_router.py -v` green (router still enforces, now via shared enforcer).
- Coverage ≥ 85% on `backend/ingestion/policy.py`.

### Code touch points
- `backend/ingestion/policy.py` (new)
- `backend/ingestion/service.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify — delegate to enforcer)
- `backend/pyproject.toml` (modify — add `python-magic` or pure-Python `magic` to base deps)
- `backend/tests/ingestion/test_policy.py` (new)

---

## Story ingestion.16: Wire document-level deletion to provenance-based graph/vector cleanup via standalone endpoint

**ID:** ingestion.16
**Status:** planned
**Prerequisites:** [api.09, graph.07, vectorstore.05]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As a** KB operator who needs to remove a single document without dropping the whole KB,
**I need** a standalone `DELETE /knowledgebases/{kb_id}/documents/{document_id}` route that owns the cascade across graph + vector + object store + status projection,
**so that** the architecture.md §14.3 milestone "wire `delete_by_source_document` to the document-delete endpoint" is closed.

### Current State
- The current API path deletes by `(filename, content_hash)` lookup as a side-effect of re-upload and calls `graph_service.delete_by_source_document` / `vector_service.delete_by_source_document` at `backend/api/routers/knowledgebases.py:430-439`.
- There is no standalone document-delete route; ingestion itself owns no `delete_source_document` / `reindex_source_document` contract.
- Architecture.md §14.3 carries this as an open milestone for the dedicated route.

### Acceptance Criteria
- [ ] `IngestionService.delete_source_document(kb_id: str, document_id: str) -> DocumentDeleteReport` exists and orchestrates: graph delete → vector delete → object-store cleanup (source + parsed) → outbox publish of `DocumentDeletedEvent`.
- [ ] `IngestionService.reindex_source_document(kb_id: str, document_id: str)` is the convenience wrapper used by re-upload (delete + re-ingest).
- [ ] `DELETE /knowledgebases/{kb_id}/documents/{document_id}` (added in `api.09`) calls the service method and returns 204 on full success, 207 Multi-Status on partial failure with `{step, status, error}` entries.
- [ ] Status projection (`ingestion.19`) reflects `deleted` transition.
- [ ] Existing re-upload path in `knowledgebases.py:430-439` is refactored to call `reindex_source_document` rather than performing cascade inline.
- [ ] Architecture.md §14.3 milestone bullet is updated to `done` and links to the closing PR.
- [ ] Unit tests cover: happy path, partial failure (vector store unavailable), document-not-found, KB-busy-409.

### Verification
- `pytest backend/tests/ingestion/test_service_delete.py backend/tests/api/test_document_delete_endpoint.py -v` green.
- A manual smoke run uploads a document, calls DELETE, queries the graph and vector store, confirms zero rows for that source.

### Code touch points
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/service_models.py` (modify — `DocumentDeleteReport`)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/events/types.py` (modify — `DocumentDeletedEvent`)
- `backend/tests/ingestion/test_service_delete.py` (new)
- `backend/tests/api/test_document_delete_endpoint.py` (new)
- `docs/architecture.md` (modify)

---

## Story ingestion.17: Add ingestion-stage observability — structured logs, Prometheus metrics, OpenTelemetry spans

**ID:** ingestion.17
**Status:** planned
**Prerequisites:** [_observability.03, _observability.05, _observability.07]
**Unblocks:** []
**Estimated size:** L

**As an** SRE operating the ingestion pipeline,
**I need** every stage (storage write, parse, chunk, extract, validate, publish) to emit structured logs, Prometheus counters/histograms, and OpenTelemetry spans,
**so that** I can trace a single document through the pipeline, spot per-stage latency regressions, and alert on parse/extract failure rates.

### Current State
- `backend/ingestion/extractor.py:38` instantiates a module logger but emits only warning-level lines on extraction failure (e.g. `extractor.py:285-286`).
- `backend/ingestion/service.py`, `backend/ingestion/chunker.py`, and `backend/ingestion/validator.py` emit no structured stage logs.
- No Prometheus counters/histograms exist for ingestion (`documents_registered_total`, `parse_duration_seconds`, `extraction_duration_seconds`, `dedup_suppression_total`).
- No OpenTelemetry spans wrap stage transitions.

### Acceptance Criteria
- [ ] A `ingestion.observability` module exposes typed counter/histogram/span helpers that wrap the shared `_observability` registry contracts.
- [ ] Each stage emits a structured log line (`stage=`, `source_document_id=`, `knowledge_base_id=`, `duration_ms=`, `outcome=`).
- [ ] Counters: `ingestion_documents_registered_total`, `ingestion_documents_parsed_total`, `ingestion_documents_failed_total{stage,error_class}`, `ingestion_chunks_emitted_total`, `ingestion_candidates_emitted_total{type,extractor}`, `ingestion_dedup_suppressed_total{type,reason}`.
- [ ] Histograms: `ingestion_stage_duration_seconds{stage}` (parse, chunk, extract, validate, publish).
- [ ] OpenTelemetry spans wrap each stage with attributes `source.document_id`, `knowledge_base_id`, `parser.name`, `extractor.method`.
- [ ] A Grafana dashboard JSON definition lands under `infra/grafana/ingestion.json`.
- [ ] Integration test confirms a single document run produces the expected counter increments and span hierarchy.

### Verification
- `pytest backend/tests/ingestion/test_observability.py -v` green.
- `curl localhost:8000/metrics` after a single ingestion shows the expected counter/histogram series.
- Manual: open Jaeger/Tempo and confirm a trace spans storage→parse→chunk→extract→validate→publish.

### Code touch points
- `backend/ingestion/observability.py` (new)
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/chunker.py` (modify)
- `backend/ingestion/extractor.py` (modify)
- `backend/ingestion/validator.py` (modify)
- `infra/grafana/ingestion.json` (new)
- `backend/tests/ingestion/test_observability.py` (new)

---

## Story ingestion.18: Add document-level status projection (SourceDocumentStatusStore)

**ID:** ingestion.18
**Status:** planned
**Prerequisites:** [database.04, events.04]
**Unblocks:** []
**Estimated size:** L

**As a** Ingestion Studio user,
**I need** a durable per-document status projection with monotonic transitions and a per-KB document list endpoint,
**so that** I can see which documents are pending vs parsed vs failed without polling Redis Streams.

### Current State
- `SourceDocument.status: IngestionStatus` exists at `backend/ingestion/models.py:40-68` with states `PENDING`, `PARSING`, `PARSED`, `CHUNKED`, `EXTRACTED`, `VALIDATED`, `FAILED`.
- There is no durable store for these statuses; they live only on in-memory `SourceDocument` instances during a single service call.
- No per-KB document listing endpoint with current stage and error detail exists.

### Acceptance Criteria
- [ ] `SourceDocumentStatusStore` protocol in `backend/ingestion/protocols.py` plus a Postgres adapter under `backend/ingestion/adapters/status_store_postgres.py`.
- [ ] Schema: `(kb_id, source_document_id, current_status, last_error, transition_log: list[StatusTransition], updated_at)`; `transition_log` enforces monotonic ordering by `(status_rank, updated_at)`.
- [ ] An event consumer subscribes to `DocumentsUploadedEvent` / `DocumentsParsedEvent` / `DocumentsFailedEvent` / `DocumentDeletedEvent` (from `ingestion.16`) and updates the projection.
- [ ] `GET /knowledgebases/{kb_id}/documents` returns `{document_id, filename, current_status, last_transition_at, last_error}` for each document; supports filtering by status.
- [ ] Out-of-order events (e.g. a stale `parsing` event arriving after `failed`) are ignored, not regressed.
- [ ] Frontend Ingestion Studio (`chili_app/src/pages/KnowledgeBaseManagerPage.tsx`) consumes the new endpoint (cross-edge to `frontend.md`, not part of this story's AC).

### Verification
- `pytest backend/tests/ingestion/test_status_store.py backend/tests/integration/test_status_projection_replay.py -v` green.
- Manual: ingest a document, observe transitions PENDING → PARSING → PARSED → CHUNKED → EXTRACTED → VALIDATED in the projection.

### Code touch points
- `backend/ingestion/protocols.py` (modify)
- `backend/ingestion/adapters/status_store_postgres.py` (new)
- `backend/database/migrations/` (new Alembic revision)
- `backend/ingestion/consumers/status_projection.py` (new)
- `backend/api/routers/knowledgebases.py` (modify — add list endpoint)
- `backend/tests/ingestion/test_status_store.py` (new)
- `backend/tests/integration/test_status_projection_replay.py` (new)

---

## Story ingestion.19: Define extraction quality fixtures and golden tests with precision/recall gates

**ID:** ingestion.19
**Status:** planned
**Prerequisites:** [ingestion.11, analytics.07, _observability.08]
**Unblocks:** []
**Estimated size:** L

**As a** extraction-quality steward,
**I need** a domain-coverage fixture corpus with gold-standard extractions and a CI-enforced precision/recall floor,
**so that** prompt edits, model upgrades, and extractor refactors cannot silently regress extraction quality below an agreed threshold.

### Current State
- `backend/tests/ingestion/fixtures/policies/` holds two markdown policy fixtures used only by the Ollama integration test (`backend/tests/ingestion/test_documents_e2e_with_ollama.py:39`).
- No domain-coverage corpus (narrative PDF, narrative DOCX, malformed files, multilingual samples) exists.
- No precision/recall metric is computed against any gold-standard extraction set.
- `analytics/metrics/` does not currently expose extraction-quality computation (cross-edge to `analytics.07`).

### Acceptance Criteria
- [ ] A fixture corpus under `backend/tests/ingestion/fixtures/golden/<domain>/` covers at minimum: 5 narrative PDFs, 5 narrative DOCX, 3 malformed files, 3 multilingual samples (per the multi-language decision from `ingestion.22`).
- [ ] Each fixture ships with a `.gold.json` companion declaring expected entities (type + natural key + minimal properties) and expected relationships.
- [ ] A `compute_extraction_quality(predicted, gold) -> QualityReport` function in `backend/analytics/metrics/extraction_quality.py` returns per-type precision/recall/F1 and an overall macro-F1 (cross-edge to `analytics.07`).
- [ ] A `pytest` marker `@pytest.mark.extraction_quality` runs the corpus through the live extractor and asserts macro-F1 ≥ 0.7 (initial floor; raised once baseline is measured).
- [ ] Quality metrics are exported to Prometheus when the suite runs in CI (cross-edge to `_observability.08` for fixture-drift dashboards).
- [ ] A `make ingestion-quality` target invokes the suite locally.

### Verification
- `pytest -m extraction_quality backend/tests/ingestion/test_extraction_quality.py -v` green and macro-F1 meets the floor.
- `make ingestion-quality` succeeds.

### Code touch points
- `backend/tests/ingestion/fixtures/golden/medicare_fraud/` (new fixtures)
- `backend/tests/ingestion/test_extraction_quality.py` (new)
- `backend/analytics/metrics/extraction_quality.py` (new — implemented in `analytics.07`, consumed here)
- `Makefile` (modify — `ingestion-quality` target)
- `backend/pyproject.toml` (modify — register `extraction_quality` marker)

---

## Story ingestion.20: Add tenant-scoped ingestion namespacing

**ID:** ingestion.20
**Status:** planned
**Prerequisites:** [_multitenancy.03, _multitenancy.05, storage.06]
**Unblocks:** []
**Estimated size:** M

**As a** multi-tenant operator,
**I need** every ingestion artifact (source storage key, parsed storage key, outbox row, status projection) to be prefixed by `tenant_id`,
**so that** KBs with the same id in different tenants cannot collide and a tenant cannot read another tenant's artifacts via guessing the KB id.

### Current State
- `IngestionService` constructs storage keys of the form `knowledgebases/{kb_id}/documents/{source_document_id}/source` at `backend/ingestion/service.py:281`, `backend/ingestion/service.py:288`, `backend/ingestion/service.py:297`, `backend/ingestion/service.py:313`.
- No `tenant_id` prefix exists anywhere; KB ids are assumed globally unique.
- Open question 5 from the Wave 1 epic draft (whether `tenant_id` becomes part of the `source_document_id` natural key) is resolved during this story.

### Acceptance Criteria
- [ ] All storage key builders accept `tenant_id` as the first segment: `tenants/{tenant_id}/knowledgebases/{kb_id}/documents/{source_document_id}/source`.
- [ ] `IngestionService` method signatures accept `tenant_id` (sourced from the canonical `_multitenancy.03` propagation contract); the API router passes the authenticated tenant.
- [ ] `source_document_id` natural key includes tenant context (decision: stays as a sibling field, NOT in the natural key, so content-hash dedup remains per-tenant cleanly — documented in the spec note added by this story).
- [ ] Outbox rows, status projection rows, and event payloads all carry `tenant_id`.
- [ ] Migration script renames existing keys from `knowledgebases/...` to `tenants/<default-tenant>/knowledgebases/...` for the existing single-tenant deployment.
- [ ] Unit tests cover: cross-tenant isolation (tenant A cannot read tenant B's keys), per-tenant dedup (same content_hash in two tenants stored independently), the migration script is idempotent.

### Verification
- `pytest backend/tests/ingestion/test_tenant_scoping.py -v` green.
- `python -m backend.ingestion.tools.migrate_tenant_keys --dry-run` reports the expected rename count.

### Code touch points
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/protocols.py` (modify)
- `backend/events/types.py` (modify — add `tenant_id` to ingestion events)
- `backend/ingestion/tools/migrate_tenant_keys.py` (new)
- `backend/tests/ingestion/test_tenant_scoping.py` (new)

---

## Story ingestion.21: Add multi-language support — chunking, extractor prompts, evidence handling

**ID:** ingestion.21
**Status:** planned
**Prerequisites:** [ingestion.09, config.05]
**Unblocks:** []
**Estimated size:** L

**As an** operator ingesting non-English content,
**I need** `Chunk.language` to be populated by a detector, sentence splitting to respect non-ASCII terminators (e.g. `。` `？` `！`), the extractor prompt to be language-aware, and evidence/quote handling to preserve original-language text,
**so that** Spanish/Chinese/Arabic policy documents extract entities correctly instead of being silently degraded by ASCII-only assumptions.

### Current State
- `Chunk.language` field exists at `backend/ingestion/models.py:130` but is never set.
- `SentenceSplitter._sentence_pattern` (`backend/ingestion/chunker.py:190`) uses `r"[^.!?]+[.!?]*\s*"` — ASCII terminators only.
- `LlmDocumentExtractor._build_prompt` (`backend/ingestion/extractor.py:333-339`) is English-only ("You extract structured entities…", "Return JSON only.").
- No language-detection step exists in the parse-or-chunk pipeline.
- Open question 3 from the Wave 1 epic draft (immediate target = English + Spanish vs broader i18n) is resolved during this story: decision captured in the implementation plan.

### Acceptance Criteria
- [ ] `LanguageDetector` (e.g. wrapping `langdetect` or `lingua`) populates `ParsedDocument.parser_metadata["language"]` and per-chunk `Chunk.language` (ISO 639-1).
- [ ] `SentenceSplitter` supports Unicode sentence terminators (`。`, `？`, `！`, `．`, `…`) and CJK whitespace handling.
- [ ] `LlmDocumentExtractor` loads a localized prompt variant per `ingestion.09` versioning (e.g. `extractor/v1/system.en.txt`, `extractor/v1/system.es.txt`) keyed on `Chunk.language`; falls back to English if no variant exists with a warning.
- [ ] `IngestionConfig.supported_languages: list[str]` declares the per-deployment supported set; unknown languages are flagged in `ValidationReport` as warnings.
- [ ] Evidence `quote` fields preserve original-language text (no transliteration).
- [ ] Unit tests cover: English (regression), Spanish, Chinese (CJK splitter), unsupported language (warning), per-chunk language differences within one document.

### Verification
- `pytest backend/tests/ingestion/test_multilingual.py -v` green.
- Coverage ≥ 85% on the language-detection module.

### Code touch points
- `backend/ingestion/language.py` (new — detector)
- `backend/ingestion/chunker.py` (modify — sentence terminators)
- `backend/ingestion/extractor.py` (modify — localized prompt lookup)
- `backend/ingestion/prompts/extractor/v1/system.es.txt` (new — initial Spanish variant per the decision)
- `backend/config/schema.py` (modify — `supported_languages`)
- `backend/pyproject.toml` (modify — add language-detection dependency under an `[i18n]` extra)
- `backend/tests/ingestion/test_multilingual.py` (new)

---

## Story ingestion.22: Add streaming upload and per-document progress reporting

**ID:** ingestion.22
**Status:** planned
**Prerequisites:** [ingestion.06, api.10, frontend.11, storage.05]
**Unblocks:** []
**Estimated size:** XL

**As an** Ingestion Studio user uploading multi-hundred-megabyte documents,
**I need** chunked / resumable uploads and a per-document progress channel (SSE or WebSocket),
**so that** large uploads do not require buffering the whole file in API memory and the UI shows live byte-level progress instead of a spinner.

### Current State
- `register_knowledge_base_documents` reads the full upload into memory via `await upload.read()` at `backend/api/routers/knowledgebases.py:413`.
- The synchronous ingestion service blocks on `object_store.put_bytes` at `backend/ingestion/service.py:93-103`.
- No chunked upload route, no resumable-upload protocol, no SSE/WS progress channel keyed on `source_document_id`.
- Open question 4 from the Wave 1 epic draft (`tus.io`, multipart S3, or custom range-based POST) is resolved during this story: decision captured in the implementation plan.

### Acceptance Criteria
- [ ] Story is split into M/L sub-stories before merge (XL split required by §5); split into (a) chunked-upload API + service, (b) progress channel + frontend wiring.
- [ ] A chunked-upload route accepts a sequence of byte ranges keyed by `(kb_id, upload_session_id)`; sessions persist until completion or TTL expiry.
- [ ] The chosen protocol (per the resolved open question) is documented in `docs/architecture.md` §5.2 / §14.3.
- [ ] `IngestionService` consumes the assembled stream rather than a full-byte buffer (relies on `ingestion.06` async I/O).
- [ ] Progress events are published to a per-`source_document_id` SSE channel under `/knowledgebases/{kb_id}/documents/{document_id}/progress`; events include `bytes_received`, `total_bytes`, `stage`, `parsed_chunks`, `extracted_candidates`.
- [ ] The Ingestion Studio (cross-edge to `frontend.11`) renders a live progress bar per document.
- [ ] Resumable uploads survive a client disconnect: re-issuing the next range continues the session.
- [ ] Backend integration test covers full upload, resume after disconnect, TTL expiry of a stale session.

### Verification
- `pytest backend/tests/api/test_chunked_upload.py backend/tests/integration/test_resumable_upload.py -v` green.
- Manual: drop a 200 MB file in the Ingestion Studio and observe the progress bar update in near-real-time.

### Code touch points
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/ingestion/service.py` (modify)
- `backend/ingestion/upload_sessions.py` (new)
- `backend/api/sse.py` (modify or new — progress channel)
- `backend/tests/api/test_chunked_upload.py` (new)
- `backend/tests/integration/test_resumable_upload.py` (new)
- `docs/architecture.md` (modify)

---

## Story ingestion.23: Add chunk-and-resume and memory-bounded handling for large documents

**ID:** ingestion.23
**Status:** planned
**Prerequisites:** [ingestion.06, ingestion.18, agent.07]
**Unblocks:** []
**Estimated size:** L

**As a** worker handling documents that exceed available memory,
**I need** chunking to stream output to the extractor instead of materializing every chunk in a list, plus a per-document chunk cap and a resume-from-chunk-N path after a worker crash,
**so that** a 500 MB document does not OOM the worker and a mid-extraction crash does not force re-processing from chunk zero.

### Current State
- `DocumentChunker.chunk_document` (`backend/ingestion/chunker.py:379-416`) materializes every chunk in a list before returning, then the extractor iterates the list.
- No per-document chunk count cap exists in `ChunkingConfig`.
- No resume-from-chunk-N path: a worker crash mid-extraction restarts from chunk zero on retry.

### Acceptance Criteria
- [ ] `DocumentChunker.iter_chunks(parsed_document, source_document_id) -> Iterator[Chunk]` streams chunks lazily; `chunk_document` becomes a thin `list(iter_chunks(...))` wrapper for callers that need materialization.
- [ ] `LlmDocumentExtractor.extract_document` and `PatternDocumentExtractor.extract_document` consume the iterator; per-chunk state (warnings, candidates) is flushed to a `ExtractionState` checkpoint after every N chunks (default 50, configurable via `IngestionConfig.extractor.checkpoint_interval`).
- [ ] `ChunkingConfig.max_chunks_per_document: int | None` (default 5000) caps runaway documents; over-cap documents are marked `FAILED` with a typed error rather than processed indefinitely.
- [ ] Resume contract: the agent workflow (cross-edge to `agent.07`) records the last successful checkpoint chunk index; on retry the extractor restarts from `last_completed_chunk_index + 1` using the same chunking determinism.
- [ ] Unit tests cover: iterator semantics, checkpoint flush, max-chunks cap, resume from mid-document checkpoint.

### Verification
- `pytest backend/tests/ingestion/test_chunker_streaming.py backend/tests/ingestion/test_extractor_resume.py -v` green.
- A reviewer ingests a synthetic 100k-chunk document and observes peak worker RSS stays under a documented bound.

### Code touch points
- `backend/ingestion/chunker.py` (modify)
- `backend/ingestion/extractor.py` (modify)
- `backend/ingestion/models.py` (modify — `ExtractionState`)
- `backend/config/schema.py` (modify — `max_chunks_per_document`, `checkpoint_interval`)
- `backend/agent/coordinator.py` (modify — resume integration)
- `backend/tests/ingestion/test_chunker_streaming.py` (new)
- `backend/tests/ingestion/test_extractor_resume.py` (new)

---

## Story ingestion.24: Add typed parser warnings channel on ParsedDocument

**ID:** ingestion.24
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** Ingestion Studio user,
**I need** parsers to surface typed non-fatal warnings (missing pages, dropped rows, charset fallback) via a dedicated `ParsedDocument.warnings` field instead of free-form `parser_metadata`,
**so that** the UI can group, count, and link warnings to specific parser categories rather than parse a `dict[str, object]`.

### Current State
- `ParsedDocument.parser_metadata` is a free-form `dict[str, object]` at `backend/ingestion/models.py:92`.
- Parsers (`pdf.py`, `docx.py`, `csv.py`, `xlsx.py`) have no typed `warnings: list[ParserWarning]` field; any soft issue (e.g. an empty PDF page) is either stuffed into `parser_metadata` or silently dropped.
- This story precedes `ingestion.04` because that story consumes the new channel.

### Acceptance Criteria
- [ ] `ParserWarning` model (`backend/ingestion/models.py`) carries `code: str`, `message: str`, `severity: Literal["info", "warning", "error"]`, optional `row_index: int | None`, optional `page_number: int | None`, optional `column_name: str | None`.
- [ ] `ParsedDocument.warnings: list[ParserWarning]` is added (default `[]`); `parser_metadata` is retained for free-form context but warnings move out of it.
- [ ] All in-tree parsers (`pdf`, `docx`, `csv`, `xlsx`, `html`, `json`, `txt`) emit at least one warning in their existing soft-failure paths (e.g. PDF empty page, HTML missing charset).
- [ ] The downstream event `DocumentsParsedEvent` (`backend/events/types.py`) carries a `warning_count: int` field for routing without inspecting the payload.
- [ ] Unit tests cover the new field on every parser plus serialization round-trip.

### Verification
- `pytest backend/tests/ingestion/parsers/ -v` green including the new warning assertions.
- `pyright --strict` clean.

### Code touch points
- `backend/ingestion/models.py` (modify)
- `backend/ingestion/parsers/pdf.py` (modify)
- `backend/ingestion/parsers/docx.py` (modify)
- `backend/ingestion/parsers/csv.py` (modify)
- `backend/ingestion/parsers/xlsx.py` (modify)
- `backend/ingestion/parsers/html.py` (modify)
- `backend/ingestion/parsers/json.py` (modify)
- `backend/ingestion/parsers/txt.py` (modify)
- `backend/events/types.py` (modify)
- `backend/tests/ingestion/parsers/` (modify)

---

## Story ingestion.25: Document and CI-enforce a production ingestion certification suite

**ID:** ingestion.25
**Status:** planned
**Prerequisites:** [ingestion.17, ingestion.19, _cicd.06, _observability.08]
**Unblocks:** []
**Estimated size:** L

**As a** release manager,
**I need** a single `make ingestion-certify` target that gates pyright/ruff/coverage/parser-fixture-corpus/provenance-round-trip/cleanup-reindex/extraction-quality in one command, and a CI job that runs it pre-release,
**so that** an ingestion regression cannot ship without breaking the build.

### Current State
- `backend/tests/ingestion/` covers unit tests plus a single Ollama-gated integration test (`test_documents_e2e_with_ollama.py`).
- There is no aggregated certification target; individual gates (pyright, ruff, coverage, fixture corpus) are run ad hoc.
- No per-domain narrative-document fixture set exists outside the two markdown fixtures used by the Ollama test.
- Architecture.md §6 ingestion requirements imply a per-domain certification posture; no enforcement mechanism backs it.

### Acceptance Criteria
- [ ] `make ingestion-certify` runs in order: `pyright --strict backend/ingestion`, `ruff check backend/ingestion`, `pytest backend/tests/ingestion --cov=backend/ingestion --cov-fail-under=85`, `pytest -m extraction_quality`, `pytest backend/tests/integration/test_ingestion_lifecycle_certify.py`, and emits a green/red summary line.
- [ ] `backend/tests/integration/test_ingestion_lifecycle_certify.py` exercises: register → parse → chunk → extract → validate → publish → graph/vector write → reindex → delete → re-register cycle and asserts zero residual state.
- [ ] A scheduled GitHub Actions pre-release job (cross-edge to `_cicd.06`) runs `make ingestion-certify` against a dev-compose stack and posts the artifact to `infra/grafana/ingestion.json` dashboards (cross-edge to `_observability.08`).
- [ ] A per-domain narrative-document fixture set lives under `backend/tests/ingestion/fixtures/golden/<domain>/narrative/` for at least the medicare_fraud domain (extends `ingestion.19`).
- [ ] The certification suite documentation lives under `backend/ingestion/README.md` with the failure-triage playbook.

### Verification
- `make ingestion-certify` exits 0 on a clean tree.
- The scheduled CI job runs green for two consecutive cycles before the story flips to `done`.

### Code touch points
- `Makefile` (modify — `ingestion-certify` target)
- `.github/workflows/ingestion-certify.yaml` (new)
- `backend/tests/integration/test_ingestion_lifecycle_certify.py` (new)
- `backend/tests/ingestion/fixtures/golden/medicare_fraud/narrative/` (new fixtures)
- `backend/ingestion/README.md` (modify — playbook section)
