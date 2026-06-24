# ingestion backlog

> **Scope:** Document parsing (PDF/DOCX/HTML/JSON/TXT), chunking, LLM extraction, fallback chain, idempotency, observability.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story ingestion.01: Reconcile architecture.md HTML-parser milestone with shipped registration

**ID:** ingestion.01
**Status:** done
**Prerequisites:** []
**Unblocks:** [ingestion.02]
**Estimated size:** S
**Done:** 2026-05-28 · docs-keeper cleanup · local working tree

**As a** platform maintainer,
**I need** `docs/architecture.md` to stop describing HTML-parser registration as a "Next milestone" when the parser is already wired,
**so that** new contributors do not chase a phantom gap and the parser inventory remains a trustworthy onboarding reference.

### Current State
- `HtmlParser` is implemented at `backend/ingestion/parsers/html.py:99-125` and registered in `backend/ingestion/parsers/registry.py:47-57` via `create_default_registry()`.
- `docs/architecture.md` §14.3 now lists HTML as registered and points at `ingestion.02` for the remaining fidelity work.
- The real residual HTML gap (table/heading fidelity) is captured separately as `ingestion.02`; this story was purely a doc reconcile.

### Acceptance Criteria
- [x] `docs/architecture.md` §14.3 no longer claims HTML parser registration is pending; the bullet is either deleted or rewritten to point at `ingestion.02` as the live follow-on.
- [x] `backend/ingestion/README.md` parser inventory section lists HTML alongside PDF/DOCX/CSV/XLSX/JSON/TXT with the correct registration status.
- [x] No other doc (root `README.md`, `backend/README.md`, `CLAUDE.md`, `.github/copilot-instructions.md`) repeats the stale "HTML parser pending" claim.

### Verification
- `rg -n "no .*parser is registered|register an HTML parser|DocumentFormat\\.HTML exists" docs/ backend/ CLAUDE.md .github/ -g '!docs/wiki/**' -g '!docs/archive/**' -g '!docs/backlog/ingestion.md'` returns no matches.
- Reviewer reads the updated §14.3 paragraph and confirms it matches `parsers/registry.py:47-57`.

### Code touch points
- `docs/architecture.md` (modify)
- `backend/ingestion/README.md` (modify)
- `backend/README.md` (modify, if it cites the stale milestone)
- `.github/copilot-instructions.md` (modify, if it cites the stale milestone)

---

## Story ingestion.02: Strengthen HTML parser fidelity beyond visible text

**ID:** ingestion.02
**Status:** done
**Prerequisites:** [ingestion.01]
**Unblocks:** [ingestion.06]
**Estimated size:** M
**Done:** 2026-06-23 · ingestion Wave 0 (ready-set) · local working tree

**As a** policy/news ingestion operator,
**I need** the HTML parser to preserve headings, links, and table structure (not just visible paragraph text),
**so that** downstream chunking and extraction can use document structure as signal instead of seeing a flattened text blob.

### Current State
- `_VisibleTextParser` at `backend/ingestion/parsers/html.py:14-97` collects only `handle_data` text into block-separated paragraphs.
- `handle_starttag` (`html.py:56-64`) explicitly ignores all attributes (`del attrs`) so anchor `href` targets are dropped.
- Tables are flattened to their text content with no row/column structure; `<h1>`–`<h6>` are demoted to plain paragraph text with no level marker.
- `HtmlParser.parse` (`html.py:106-125`) returns only `text_content` and a single `visible_text_length` metadata field.

### Acceptance Criteria
- [x] Headings are preserved with a leading marker (e.g. `# `, `## `) so downstream chunking can detect section boundaries.
- [x] Anchor text retains link targets in a normalized form (e.g. `[text](url)` markdown-style) for entity-extraction context.
- [x] Tables are emitted as markdown-style pipe tables so they survive chunking intact (nested tables flattened into the parent cell).
- [x] `ParsedDocument.parser_metadata` carries counts (`heading_count`, `link_count`, `table_count`) for observability.
- [x] New unit tests cover heading fidelity, link extraction, table preservation, nested-table edge cases, and the existing visible-text behavior remains green.
- [x] `backend/ingestion/README.md` documents the new fidelity guarantees.

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
**Status:** done
**Prerequisites:** []
**Unblocks:** [ingestion.06]
**Estimated size:** L
**Done:** 2026-06-23 · ingestion Wave 0 (ready-set) · local working tree

**As a** Medicare-fraud analyst ingesting scanned policy or claim PDFs,
**I need** the PDF parser to fall back to an OCR adapter when text extraction yields nothing,
**so that** image-only PDFs become parseable instead of failing outright with `ParserError("PDF does not contain extractable text.")`.

### Current State
- `PdfParser.parse` at `backend/ingestion/parsers/pdf.py:23-46` calls `pypdf` and raises `ParserError` (line 34-35) whenever the concatenated page text is empty.
- No OCR adapter boundary exists; `pyproject.toml` declares no OCR optional extra.
- Architecture.md §5/§6 does not currently commit to OCR; this story includes the architectural decision check (Open question 1 from the Wave 1 epic draft).

### Acceptance Criteria
- [x] `OcrAdapterProtocol` lives in `backend/ingestion/parsers/protocols.py` with a page-level `recognize_page(content: bytes, page_number: int) -> str` signature, dependency-light.
- [x] A concrete `TesseractOcrAdapter` lives under `backend/ingestion/parsers/adapters/` behind an optional `[ocr]` extra in `pyproject.toml` (lazy `importlib` imports); an in-tree `_StubOcrAdapter` ships in the parser unit tests.
- [x] `PdfParser` accepts an optional `ocr_adapter` parameter; when a page's text extraction is empty AND an adapter is configured, it OCRs that page and emits the OCR text with `parser_metadata["ocr_used"] = True`.
- [x] When no adapter is configured the parser continues to raise `ParserError` (unchanged behavior) so opt-in is explicit.
- [x] `docs/architecture.md` §6.5 states OCR is a supported optional adapter, opt-in per deployment.
- [x] Unit tests cover: text-PDF (no OCR), image-PDF with adapter (OCR used), image-PDF without adapter (ParserError), mixed-page PDF (OCR fills empty pages only), and OCR-finds-nothing keeps the empty-page warning. (Unit tests live in `test_local_parsers.py`; the `[ocr]`-gated integration test is `test_pdf_ocr_integration.py`.)

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
**Unblocks:** [ingestion.06]
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
**Unblocks:** [api.01, config.13]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As a** worker operating the documents flow,
**I need** the storage-write + event-publish path to be atomic via an outbox so that a publish failure after a successful storage write does not strand the document,
**so that** the worker can replay missed events and the Ingestion Studio's per-document status never disagrees with the durable record.

### Current State
- `IngestionService.register_documents` writes source bytes then publishes `DocumentsUploadedEvent`. When configured with an `IngestionRecoveryStore`, a publish failure creates an `IngestionRecoveryMarker`; `replay_recovery_markers()` republishes from stored object metadata and removes the marker only after publish succeeds.
- `ingest_task` still publishes parsed and failure events directly with no equivalent durable marker/outbox path.
- No outbox table exists today; events go straight from in-process publisher to Redis Streams.

### Acceptance Criteria
- [x] A durable recovery marker exists for `documents.uploaded` storage-then-publish failures, and tests prove replay keeps the marker when publish fails again and removes it only after successful publish.
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

## Story ingestion.06: Introduce async ingestion service facade

**ID:** ingestion.06
**Status:** planned
**Prerequisites:** [ingestion.02, ingestion.03, ingestion.04]
**Unblocks:** [ingestion.26]
**Estimated size:** L

### Narrative
As an ingestion operator,
I want ingestion orchestration to expose async service methods,
so that uploads and remote fetches can run without blocking worker capacity.

### Current State
Ingestion workflows exist, but blocking IO still appears in parts of the service path.

### Acceptance Criteria
- [ ] Async facade covers document registration, file ingestion, remote fetch kickoff, and status reads.
- [ ] Concurrency limits protect worker and storage resources.
- [ ] Blocking adapters are wrapped behind explicit boundaries pending native async replacements.
- [ ] Cancellation and timeout behavior is documented for long-running ingestion calls.

### Verification
- [ ] Async unit tests cover concurrent ingestion calls and timeout behavior.
- [ ] Existing synchronous callers continue to work through compatibility wrappers where required.

### Code touch points
- `backend/ingestion/**`
- `backend/app/api/**`
- `backend/tests/**`

---
## Story ingestion.07: Harden remote document fetching against SSRF and oversized payloads

**ID:** ingestion.07
**Status:** planned
**Prerequisites:** [ingestion.27, _security.06]
**Unblocks:** []
**Estimated size:** M

**As a** security-conscious operator,
**I need** the remote-fetch path to enforce a host allowlist, block private-IP/loopback/link-local targets, re-check the target after redirects, and refuse to authenticate against unknown hosts,
**so that** a tenant-supplied URL cannot pivot inside the cluster network or exfiltrate credentials.

### Current State
- `HttpxRemoteDocumentFetcher.__init__` (`backend/ingestion/parsers/remote.py:23-32`) accepts a timeout and `max_bytes` only.
- `fetch` enforces HTTPS on the original URI, streams via `client.stream()`, re-checks that the final redirected URL is still HTTPS, rejects malformed/negative `content-length`, and enforces `max_bytes` while iterating chunks.
- Remaining gaps: no host allowlist, no IP-range deny-list, no DNS rebinding guard, and no authenticated-fetch story.

### Acceptance Criteria
- [ ] `RemoteFetchPolicy` config object specifies `allowed_hosts: list[str]` (exact + suffix match), `denied_ip_ranges: list[IPv4Network | IPv6Network]` (defaults block RFC 1918, loopback, link-local, multicast, `0.0.0.0/0` if allowlist mode is enforced).
- [ ] Pre-flight DNS resolution checks every resolved IP against the deny-list; redirects re-run the full host + IP check.
- [ ] Credentials (basic auth, bearer tokens) are only attached when the host matches a configured `authenticated_hosts` allowlist; redirects strip credentials by default.
- [x] `content-length` is not trusted as the only limit; body-size enforcement happens mid-stream in the current synchronous fetcher.
- [ ] Async backpressure-aware remote streaming lands with the ingestion.06/ingestion.27 work.
- [ ] Audit log entry on every blocked request (cross-edge to `_security.06` audit log; `_security.07` is PII redaction, not the audit log).
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
**Unblocks:** [ingestion.10, ingestion.21, ingestion.22]
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
**Unblocks:** [ingestion.11]
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
**Unblocks:** [analytics.01, ingestion.12, ingestion.19]
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
- API enforces `allowed_content_types` and reads uploads in 64 KiB chunks, raising 413 immediately after `max_file_size_mb` is exceeded.
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
**Prerequisites:** [vectorstore.09]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md

**As a** KB operator who needs to remove a single document without dropping the whole KB,
**I need** a standalone `DELETE /knowledgebases/{kb_id}/documents/{document_id}` route that owns the cascade across graph + vector + object store + status projection,
**so that** the architecture.md §14.3 milestone "wire `delete_by_source_document` to the document-delete endpoint" is closed.

### Current State
- The API has a standalone `DELETE /knowledgebases/{kb_id}/documents/{document_id}` route (`backend/api/routers/knowledgebases.py:352-400`), but it only deletes object-store keys under the document prefix and then the metadata row; it does not call `graph_service.delete_by_source_document` or `vector_service.delete_by_source_document`.
- The re-upload path records a replacement candidate by content hash and calls `graph_service.delete_by_source_document` / `vector_service.delete_by_source_document` only after registration returns an enqueued receipt (`knowledgebases.py:140-141`).
- The graph/vector `delete_by_source_document` capability **is already implemented** in code — `graph/service.py:313`, `graph/adapters/{in_memory.py:275,neo4j_adapter.py:570}`, `vectorstore/service.py:216`, `vectorstore/adapters/{in_memory.py:111,qdrant_adapter.py:261}`. What is missing is the *wiring* of that capability into the standalone delete route, plus the ingestion-owned orchestration contract.
- Ingestion itself owns no `delete_source_document` / `reindex_source_document` contract.
- Architecture.md §14.3 carries this as an open milestone for the dedicated route.
- **PM prereq re-point (2026-06-23):** original prereqs `[api.09, graph.07, vectorstore.05]` were mislabeled — api.09 = "Consolidate request/response contracts", graph.07 = "Improve entity search relevance", vectorstore.05 = "namespace lifecycle", none of which gate this cascade. The single real prerequisite is **vectorstore.09** ("Wire `delete_by_source_document` into the document-delete API and harden edge cases"), which owns the vector leg of the cascade. The graph leg's capability already ships (no graph story needed) and there is no separate api story for the delete route — the route already exists and this story owns wiring the cascade through it.

### Acceptance Criteria
- [ ] `IngestionService.delete_source_document(kb_id: str, document_id: str) -> DocumentDeleteReport` exists and orchestrates: graph delete → vector delete → object-store cleanup (source + parsed) → outbox publish of `DocumentDeletedEvent`.
- [ ] `IngestionService.reindex_source_document(kb_id: str, document_id: str)` is the convenience wrapper used by re-upload (delete + re-ingest).
- [ ] `DELETE /knowledgebases/{kb_id}/documents/{document_id}` (route already exists at `knowledgebases.py:352`; coordinate the vector leg with `vectorstore.09`) calls the service method and returns 204 on full success, 207 Multi-Status on partial failure with `{step, status, error}` entries.
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
**Unblocks:** [ingestion.25]
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
**Unblocks:** [ingestion.22, ingestion.23]
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
**Prerequisites:** [ingestion.11, analytics.33, _observability.08]
**Unblocks:** [ingestion.25]
**Estimated size:** L

**As a** extraction-quality steward,
**I need** a domain-coverage fixture corpus with gold-standard extractions and a CI-enforced precision/recall floor,
**so that** prompt edits, model upgrades, and extractor refactors cannot silently regress extraction quality below an agreed threshold.

### Current State
- `backend/tests/ingestion/fixtures/policies/` holds two markdown policy fixtures used only by the Ollama integration test (`backend/tests/ingestion/test_documents_e2e_with_ollama.py:39`).
- No domain-coverage corpus (narrative PDF, narrative DOCX, malformed files, multilingual samples) exists.
- No precision/recall metric is computed against any gold-standard extraction set.
- `analytics/metrics/` does not currently expose extraction-quality computation (cross-edge to **`analytics.33`** — new story added by the 2026-06-23 PM run; the prior reference to `analytics.07` was wrong, as `analytics.07` is a timeseries-DI story).

### Acceptance Criteria
- [ ] A fixture corpus under `backend/tests/ingestion/fixtures/golden/<domain>/` covers at minimum: 5 narrative PDFs, 5 narrative DOCX, 3 malformed files, 3 multilingual samples (per the multi-language decision from `ingestion.22`).
- [ ] Each fixture ships with a `.gold.json` companion declaring expected entities (type + natural key + minimal properties) and expected relationships.
- [ ] A `compute_extraction_quality(predicted, gold) -> QualityReport` function in `backend/analytics/metrics/extraction_quality.py` returns per-type precision/recall/F1 and an overall macro-F1 (cross-edge to `analytics.33`).
- [ ] A `pytest` marker `@pytest.mark.extraction_quality` runs the corpus through the live extractor and asserts macro-F1 ≥ 0.7 (initial floor; raised once baseline is measured).
- [ ] Quality metrics are exported to Prometheus when the suite runs in CI (cross-edge to `_observability.08` for fixture-drift dashboards).
- [ ] A `make ingestion-quality` target invokes the suite locally.

### Verification
- `pytest -m extraction_quality backend/tests/ingestion/test_extraction_quality.py -v` green and macro-F1 meets the floor.
- `make ingestion-quality` succeeds.

### Code touch points
- `backend/tests/ingestion/fixtures/golden/medicare_fraud/` (new fixtures)
- `backend/tests/ingestion/test_extraction_quality.py` (new)
- `backend/analytics/metrics/extraction_quality.py` (new — implemented in `analytics.33`, consumed here)
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

## Story ingestion.22: Add chunked upload session API

**ID:** ingestion.22
**Status:** planned
**Prerequisites:** [frontend.15, ingestion.27, ingestion.09, ingestion.18]
**Unblocks:** [ingestion.28]
**Estimated size:** L

### Narrative
As a user uploading large files,
I want chunked upload sessions,
so that long uploads can survive network interruptions and backend request limits.

### Current State
Ingestion accepts uploads, but resumable upload session state and chunk assembly are not implemented.

### Acceptance Criteria
- [ ] API creates upload sessions with file metadata, expected size, content hash, and knowledge base scope.
- [ ] API accepts chunks idempotently and records received byte ranges.
- [ ] Completed sessions assemble and hand off files to the existing ingestion workflow.
- [ ] Expired or abandoned sessions are detectable for cleanup.

### Verification
- [ ] API tests cover session creation, repeated chunk submission, completion, and missing chunks.
- [ ] Large-file smoke test uploads through the chunked path.

### Code touch points
- `backend/app/api/**`
- `backend/ingestion/**`
- `backend/tests/**`

---
## Story ingestion.23: Add chunk-and-resume and memory-bounded handling for large documents

**ID:** ingestion.23
**Status:** planned
**Prerequisites:** [ingestion.27, ingestion.18, agent.07]
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
**Status:** done
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** 2026-06-23 · ingestion Wave 0 (ready-set) · local working tree

**As a** Ingestion Studio user,
**I need** parsers to surface typed non-fatal warnings (missing pages, dropped rows, charset fallback) via a dedicated `ParsedDocument.warnings` field instead of free-form `parser_metadata`,
**so that** the UI can group, count, and link warnings to specific parser categories rather than parse a `dict[str, object]`.

### Current State
- `ParsedDocument.parser_metadata` is a free-form `dict[str, object]` at `backend/ingestion/models.py:92`.
- Parsers (`pdf.py`, `docx.py`, `csv.py`, `xlsx.py`) have no typed `warnings: list[ParserWarning]` field; any soft issue (e.g. an empty PDF page) is either stuffed into `parser_metadata` or silently dropped.
- This story precedes `ingestion.04` because that story consumes the new channel.

### Acceptance Criteria
- [x] `ParserWarning` model (`backend/ingestion/models.py`) carries `code: str`, `message: str`, `severity: Literal["info", "warning", "error"]`, optional `row_index: int | None`, optional `page_number: int | None`, optional `column_name: str | None`.
- [x] `ParsedDocument.warnings: list[ParserWarning]` is added (default `[]`); `parser_metadata` is retained for free-form context but warnings move out of it.
- [x] All in-tree parsers (`pdf`, `docx`, `csv`, `xlsx`, `html`, `json`, `txt`) emit at least one warning in their existing soft-failure paths (e.g. PDF empty page, HTML missing charset).
- [x] The downstream event `DocumentsParsedEvent` (`backend/events/types.py`) carries a `warning_count: int` field (on `ParsedDocumentReference`) for routing without inspecting the payload.
- [x] Unit tests cover the new field on every parser plus serialization round-trip.

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
**Unblocks:** [ingestion.04]
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

## Story ingestion.26: Replace blocking storage adapters with async equivalents

**ID:** ingestion.26
**Status:** planned
**Prerequisites:** [ingestion.06]
**Unblocks:** [ingestion.27]
**Estimated size:** L

### Narrative
As an ingestion operator,
I want storage and parser IO to use async-compatible adapters,
so that ingestion concurrency is limited by configured capacity rather than blocking calls.

### Acceptance Criteria
- [ ] Object storage adapter interface supports async reads and writes.
- [ ] Local filesystem, configured object storage, and parser boundaries expose async-compatible methods or explicit thread offloading.
- [ ] Adapter selection and fallback behavior are documented.

### Verification
- [ ] Async adapter tests cover local and object-storage fixtures.
- [ ] Concurrency test proves multiple uploads do not block the event loop under normal limits.

### Code touch points
- `backend/ingestion/**`
- `backend/app/storage/**`
- `backend/tests/**`

---

## Story ingestion.27: Stream remote fetches through async ingestion pipeline

**ID:** ingestion.27
**Status:** planned
**Prerequisites:** [ingestion.26]
**Unblocks:** [ingestion.07, ingestion.22, ingestion.23]
**Estimated size:** M

### Narrative
As an ingestion operator,
I want remote fetches to stream into the async ingestion pipeline,
so that large remote files do not require full buffering in memory.

### Acceptance Criteria
- [x] Current synchronous remote fetch implementation streams content with timeout and size-limit enforcement.
- [ ] Async remote fetch path streams through the async ingestion pipeline.
- [ ] Pipeline applies backpressure when storage or parsing is slower than download.
- [ ] Fetch errors are surfaced through existing ingestion status records.

### Verification
- [ ] Tests cover streaming success, timeout, oversized response, and upstream failure.
- [ ] Memory-sensitive smoke test proves large fetches do not buffer the full file in process memory.

### Code touch points
- `backend/ingestion/**`
- `backend/tests/**`

---

## Story ingestion.28: Publish upload progress events

**ID:** ingestion.28
**Status:** planned
**Prerequisites:** [ingestion.22, events.10]
**Unblocks:** [ingestion.29]
**Estimated size:** M

### Narrative
As a user uploading large files,
I want upload progress to be visible while chunks are received and processed,
so that I can tell whether an upload is still making progress.

### Acceptance Criteria
- [ ] Backend publishes progress events for bytes received, assembly, ingestion handoff, and failure states.
- [ ] Progress API or subscription endpoint exposes latest session state.
- [ ] Progress events include upload session ID and knowledge base scope.

### Verification
- [ ] Tests cover progress transitions for successful and failed uploads.
- [ ] Event tests prove progress events are emitted in order for a normal upload.

### Code touch points
- `backend/ingestion/**`
- `backend/app/events/**`
- `backend/app/api/**`

---

## Story ingestion.29: Add frontend resumable upload progress flow

**ID:** ingestion.29
**Status:** planned
**Prerequisites:** [ingestion.28, frontend.15]
**Unblocks:** []
**Estimated size:** L

### Narrative
As a user uploading large files,
I want the frontend to show resumable upload progress and recovery controls,
so that interrupted uploads can be completed without starting over.

### Acceptance Criteria
- [ ] Frontend uploads files through chunked sessions and shows progress states.
- [ ] Interrupted uploads can resume from the server-reported received ranges.
- [ ] Failure states distinguish retryable network errors from rejected files.

### Verification
- [ ] Browser E2E test covers interruption, resume, completion, and failed upload states.
- [ ] Component tests cover progress rendering and retry controls.

### Code touch points
- `frontend/src/**`
- `frontend/tests/**`
- `tests/e2e/**`

---

## Story ingestion.30: Use the LLM's relationship output instead of fabricating intra-chunk Cartesian edges

**ID:** ingestion.30
**Status:** done
**Type:** bug
**Prerequisites:** []
**Unblocks:** [ingestion.31]
**Estimated size:** M
**Done:** 2026-06-23 · ingestion relationship-fidelity slice · local working tree

**As an** extraction-quality operator,
**I need** `LlmDocumentExtractor` to parse and use the `relationships` array the model returns (keyed by `source_index`/`target_index`) rather than discarding it and emitting every source-type × target-type pair within a chunk,
**so that** the graph reflects relationships the model actually identified instead of a combinatorial false-positive explosion.

### Current State
- `_build_prompt` (`backend/ingestion/extractor.py:333-345`) instructs the model to return `{"relationships": [{"type": "...", "source_index": 0, "target_index": 1}]}`.
- `_extract_chunk` parses the `entities` array but **never reads the `relationships` array** — the model's relationship output is silently dropped.
- `_extract_relationships` (`backend/ingestion/extractor.py:404-435`) ignores model output entirely: for each chunk it loops every `rel_def` and emits a `CandidateRelationship` for **every** `(source, target)` pair where `source.type == rel_def.source` and `target.type == rel_def.target` (`extractor.py:415-421`). This is an `O(|sources| × |targets| × |rel_defs|)` Cartesian product per chunk.
- Result: in a chunk with N sources and M targets, all N×M edges are created regardless of whether the text supports them; relationship confidence is just `min(source.confidence, target.confidence)` (`extractor.py:429`) with no model grounding.

### Acceptance Criteria
- [x] `_extract_chunk` parses the model's `relationships` array, mapping `source_index`/`target_index` back to the entity candidates produced for that chunk; out-of-range or dangling indices are dropped with a warning, not silently.
- [x] `_extract_relationships` is replaced by (or rewired to consume) the model-provided edges; the Cartesian fallback is removed. Only relationships the model emitted (and whose endpoints survived entity validation) are produced.
- [x] Each emitted `CandidateRelationship` carries `evidence` (the model's supporting span/quote where available) instead of `evidence=[]`.
- [x] Relationship `type` is validated against `RelationshipDefinition.name` and endpoint types against `source`/`target`; mismatches are dropped with a warning.
- [x] Unit tests cover: model returns valid relationships (created), model returns out-of-range index (dropped + warning), model returns a relationship whose endpoint was validation-dropped (dropped), model returns no relationships (none created — no Cartesian fallback), endpoint-type mismatch (dropped).

### Verification
- `pytest backend/tests/ingestion/test_llm_extractor.py -v` green including the new relationship-sourcing cases.
- Coverage ≥ 85% on `backend/ingestion/extractor.py`.
- A reviewer ingests a fixture chunk with 3 providers + 2 claims and confirms only the model-asserted edges appear, not all 6 pairs.

### Code touch points
- `backend/ingestion/extractor.py` (modify — `_extract_chunk`, `_extract_relationships`)
- `backend/tests/ingestion/test_llm_extractor.py` (modify)

---

## Story ingestion.31: Stop dropping relationships for cross-chunk-deduplicated entities

**ID:** ingestion.31
**Status:** done
**Type:** bug
**Prerequisites:** [ingestion.30]
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-06-23 · ingestion relationship-fidelity slice · local working tree

**As an** extraction-quality operator,
**I need** the relationship pass to resolve endpoints against the document's surviving (deduplicated) entity set rather than the per-chunk candidate list,
**so that** edges referencing an entity that was deduplicated away in an earlier chunk are not silently lost.

### Current State
- `LlmDocumentExtractor.extract_document` (`backend/ingestion/extractor.py:240-253`) deduplicates entities across the whole document via `seen_natural_keys` / `_is_duplicate` (`extractor.py:243-251, 386-402`), keeping only the first candidate per `(type, natural_key)` and discarding later duplicates from `all_candidates`.
- The relationship pass then filters candidates by `c.chunk_id == chunk.id` (`extractor.py:413`). A later chunk that mentions a now-deduplicated entity has **no surviving candidate of that type in that chunk**, so any relationship anchored on it is never created.
- Net effect: the more frequently an entity appears (the more important it usually is), the more of its relationships are dropped.

### Acceptance Criteria
- [x] Relationship endpoints resolve to the surviving deduplicated candidate for the entity's `(type, natural_key)`, regardless of which chunk the relationship was found in.
- [x] A duplicate mention's relationships are re-pointed to the surviving candidate id rather than dropped.
- [x] When an endpoint has no `natural_key` (cannot be deduplicated), existing per-chunk behavior is preserved (no regression).
- [x] Surviving candidates accumulate `metadata["merged_chunk_ids"]` (or equivalent) so provenance reflects all contributing chunks.
- [x] Unit tests cover: entity deduped in chunk 1, relationship found in chunk 3 → edge created against the chunk-1 survivor; no-natural-key endpoint → unchanged; self-loop avoided.

### Verification
- `pytest backend/tests/ingestion/test_llm_extractor.py -v` green including the cross-chunk endpoint-resolution cases.
- Coverage ≥ 85% on `backend/ingestion/extractor.py`.

### Code touch points
- `backend/ingestion/extractor.py` (modify — dedup/relationship interplay)
- `backend/tests/ingestion/test_llm_extractor.py` (modify)

---

## Story ingestion.32: Convert all parser/read failures into DocumentsFailedEvent instead of escaping the safe wrappers

**ID:** ingestion.32
**Status:** done
**Type:** bug
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-06-16 · IFO-1 (ingestion failure-path observability slice) · local working tree

**As a** worker operating the documents flow,
**I need** every parse-stage failure — including non-`ParserError` exceptions and object-store read failures — to be caught and published as a `DocumentsFailedEvent`,
**so that** a single malformed document surfaces as a clean per-document failure rather than escaping uncaught, leaving the document stuck and (per ingestion batch handling) poisoning its batch.

### Current State
- `safe_parse_content` (`backend/ingestion/orchestrators/parser.py:69-92`) catches **only** `ParserError` (`parser.py:86`); `safe_parse_source` (`parser.py:106-109`) catches `ParserError` and `RemoteFetchError`.
- Several real failures raise other types that escape these wrappers:
  - Lazy-iteration errors raised **outside** the parser constructor's try-block: PDF `page.extract_text()`, XLSX `iter_rows`, CSV row iteration (only the dialect sniff is guarded in `csv.py`).
  - Empty/textless output: `ParsedDocument._ensure_content` (`backend/ingestion/models.py:94-100`) raises a Pydantic `ValidationError`, not a `ParserError`, e.g. for an empty TXT file decoding to `""`.
  - `ingest_task` reads source bytes unguarded at `backend/ingestion/service.py:290` (`self._object_store.get_bytes(task.storage_key)`); a deleted/missing source object raises `KeyError`.
- In each case the exception propagates out of `ingest_task`, **no `DocumentsFailedEvent` is published**, and the document is stranded (and, per the downstream batch handlers, fails the whole batch on retry/DLQ).

### Acceptance Criteria
- [x] The parse path catches any unexpected exception (not just `ParserError`) and converts it to a `DocumentParseFailure` with `error_type`/`error_message`, so `ingest_task` always emits a `DocumentsFailedEvent` for a failed document.
- [x] `ParsedDocument` validation failure (empty content) is mapped to a typed parse failure rather than an escaping `ValidationError`.
- [x] The object-store read in `ingest_task` is guarded; a missing source key produces a `DocumentParseFailure`, not an uncaught `KeyError`.
- [x] Parsers that iterate lazily (PDF/CSV/XLSX) either widen their try-blocks to cover iteration or are covered by the wrapper-level catch; the chosen approach is documented.
- [x] Unexpected (non-`ParserError`) failures are logged at error level with the source document id and exception class so they remain debuggable.
- [x] Unit tests cover: parser raising a non-`ParserError` mid-iteration, empty-TXT validation failure, missing source object (`KeyError`), and confirm a `DocumentsFailedEvent` is published in each case with the rest of the batch unaffected.

### Verification
- `pytest backend/tests/ingestion/test_orchestrator_parser.py backend/tests/ingestion/test_service.py -v` green including the new escape-path cases.
- Coverage ≥ 85% on `backend/ingestion/orchestrators/parser.py` and `backend/ingestion/service.py`.

### Code touch points
- `backend/ingestion/orchestrators/parser.py` (modify — broaden exception handling)
- `backend/ingestion/service.py` (modify — guard `ingest_task` read; map validation failure)
- `backend/ingestion/parsers/{pdf,csv,xlsx}.py` (modify — cover lazy iteration, if chosen)
- `backend/tests/ingestion/test_orchestrator_parser.py` (new or modify)
- `backend/tests/ingestion/test_service.py` (modify)

---

## Story ingestion.33: Use the full content digest for document identity to eliminate dedup collisions

**ID:** ingestion.33
**Status:** done
**Type:** bug
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** 2026-06-23 · ingestion relationship-fidelity slice · local working tree

**As a** KB operator,
**I need** `source_document_id` to be derived from the full SHA-256 digest rather than a 24-hex-char (96-bit) prefix,
**so that** a hash-prefix collision cannot silently route a new upload into the dedup path and return another document's bytes.

### Current State
- `_source_document_id` (`backend/ingestion/service.py:415-421`) returns `f"doc-sha256-{sha256(submission.content).hexdigest()[:24]}"` for content uploads and `f"doc-uri-{...[:24]}"` for remote URIs — only the first 24 hex chars (96 bits) form the identity.
- The full 64-char digest is already computed and retained as `checksum` (`service.py:73-78`) and in storage metadata, so identity discards information the system already has.
- A prefix collision hits the `already_registered` dedup path and returns the existing object's bytes — silent data loss/corruption with no error surfaced.

### Acceptance Criteria
- [x] `_source_document_id` uses the full hex digest (or a documented, sufficiently-wide encoding) for both the `doc-sha256-` and `doc-uri-` forms.
- [x] A migration/compat note documents the id-format change and its effect on existing stored keys (cross-edge to `ingestion.20` storage-key construction); existing documents remain resolvable or a one-time migration is specified.
- [x] Dedup correctness is preserved: re-uploading identical bytes still produces the same id and `enqueued=False`.
- [x] Unit tests cover: identical content → same id; two contents sharing a 24-char prefix but differing later → distinct ids (regression test for the collision).

### Verification
- `pytest backend/tests/ingestion/test_service.py -v` green including the prefix-collision regression test.
- `pyright --strict` clean on `backend/ingestion/service.py`.

### Code touch points
- `backend/ingestion/service.py` (modify — `_source_document_id`)
- `backend/tests/ingestion/test_service.py` (modify)
- `docs/architecture.md` (modify, if it documents the id format)

---

## Story ingestion.34: Stamp the correct source_kind for record-derived entities

**ID:** ingestion.34
**Status:** done
**Type:** bug
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** 2026-06-23 · ingestion provenance + empty-extraction slice · local working tree

**As a** provenance/audit consumer,
**I need** entities and relationships derived from structured records (via `StructuredRecordChunker`) to be stamped `source_kind="record"` rather than `source_kind="document"`,
**so that** cascade-delete and audit queries can correctly distinguish record-derived data from document-derived data.

### Current State
- `_entity_from_candidate` and `_relationship_from_candidate` in `backend/ingestion/validator.py` hardcode `SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT` (`validator.py:31, 50`) for **every** candidate.
- `SOURCE_KIND_RECORD` exists (`backend/shared/provenance.py:26`) but the document validator never uses it.
- Records ingested through the document pipeline via `StructuredRecordChunker` (`backend/ingestion/chunker.py`) therefore carry an incorrect `source_kind="document"` provenance stamp.

### Acceptance Criteria
- [x] The validator stamps `source_kind` based on the candidate's actual origin (document text vs structured record), using `SOURCE_KIND_RECORD` for record-derived candidates and `SOURCE_KIND_DOCUMENT` for text-derived candidates.
- [x] The origin signal is threaded from the chunk/candidate (e.g. a chunk-source-kind field or candidate metadata) to the validator rather than inferred heuristically. (Explicit `ChunkMetadata.source_kind` set by the chunker, read per-candidate by `chunk_id` in `validate_extraction`.)
- [x] Provenance round-trip is verified: a record-derived entity reports `source_kind="record"` end-to-end.
- [x] Unit tests cover both paths (text-derived → `document`, record-derived → `record`) and the relationship variants.

### Verification
- `pytest backend/tests/ingestion/test_validator.py -v` green including the source-kind cases.
- Coverage ≥ 85% on `backend/ingestion/validator.py`.

### Code touch points
- `backend/ingestion/validator.py` (modify)
- `backend/ingestion/models.py` (modify, if a source-kind signal must be added to the candidate/chunk)
- `backend/ingestion/chunker.py` (modify, if origin must be propagated)
- `backend/tests/ingestion/test_validator.py` (modify)

---

## Story ingestion.35: Surface empty extractions and validation drops instead of marking the document silently ready

**ID:** ingestion.35
**Status:** planned
**Type:** bug
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** Ingestion Studio user,
**I need** a document that yields zero valid entities, or whose entities were dropped during validation, to surface a distinct status/warning rather than completing as "ready" with no signal,
**so that** a misconfigured extractor (or a single hallucinated extra property) does not silently produce empty knowledge bases that look successful.

### Current State
- `validate_extraction` (`backend/ingestion/validator.py:76-112`) records dropped candidates in `entity_errors` / `relationship_errors` (`validator.py:79-80, 87, 100, 110-111`) — but the coordinator emits only `valid_entity_count` and never propagates these error maps to a user-visible surface.
- `validate_entity` (`backend/shared/types.py`) rejects an entity for an unexpected/extra property; the LLM prompt asks the model to omit unknown fields but does not forbid extra ones, so one hallucinated property silently drops an otherwise-good entity.
- A document with zero valid entities still emits `KnowledgeBaseReadyEvent` with `vector_count=0` (`backend/agent/coordinator.py:1258-1267`) and is marked ready — there is no "empty extraction" terminal state or warning.

### Acceptance Criteria
- [x] A document that produces zero valid entities reaches a distinct, durable terminal signal (the per-document `DocumentsExtractionWarningEvent`, plus `empty_extraction=True` + `source_document_id` on `KnowledgeBaseReadyReference`), not a silent ready.
- [ ] `entity_errors` / `relationship_errors` counts (and a bounded sample) are surfaced via the document status projection / API so the UI can show "N entities dropped during validation: <reasons>" (cross-edge to `ingestion.18`). _Partially delivered: counts + a bounded `sample_reasons` ride the durable `DocumentsExtractionWarningEvent`, and the full `ValidationReport` is persisted to the object store; the `GET .../documents` projection/API surface remains `ingestion.18`._
- [x] The "unexpected property drops the whole entity" sharp edge is mitigated: either extra properties are stripped/relegated to metadata before `validate_entity`, or the drop is reported as a typed, user-visible warning rather than a silent loss. (Coordinate with `ingestion.14` normalization.) (Implemented as strip-to-`metadata.extra_properties` + a `ValidationReport.warnings` notice; prompt hardened to discourage extra properties.)
- [ ] Metrics: `ingestion_documents_empty_extraction_total`, `validation_entities_dropped_total{reason}` (cross-edge to `ingestion.17`). _Deferred: structured worker logs + the durable event ship now; Prometheus counters land with the `ingestion.17` observability registry._
- [x] Unit tests cover: zero-valid-entity document (distinct signal emitted), entity dropped for extra property (warning surfaced), report counts propagate to the status surface.

### Verification
- `pytest backend/tests/ingestion/test_validator.py backend/tests/agent/test_coordinator_ready.py -v` green including the empty/dropped cases.
- Manual: ingest a document that extracts nothing and confirm the UI/status shows an empty-extraction warning rather than a clean "ready".

### Code touch points
- `backend/ingestion/validator.py` (modify — surface drop reasons)
- `backend/agent/coordinator.py` (modify — empty-extraction signal + propagate error counts)
- `backend/events/types.py` (modify, if a new status/warning field is added to the ready/validated events)
- `backend/tests/ingestion/test_validator.py` (modify)
- `backend/tests/agent/test_coordinator_ready.py` (new or modify)

---
