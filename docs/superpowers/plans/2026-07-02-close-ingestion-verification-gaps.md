# Close Ingestion Verification Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 5 gaps found by full-story verification of the `fix/ingestion-relationship-fidelity` branch: HTML unuploadable via API, LLM extractor unreachable (coordinator never passes `llm_client`), validator rejecting string decimals, warnings invisible in the UI, and uninterpolated `%s` worker logs.

**Architecture:** Backend fixes are surgical (config default, coordinator wiring helper, a new `ingestion/normalization.py` pass before `validate_entity`, one structlog processor). The UI gap is the only cross-cutting piece: persist warning data onto `DocumentRecord` (object-store/in-memory repository — Pydantic JSON, no DB migration), expose it on `DocumentSummary`, regenerate contracts, render `warning`-tone `Chip`s in the Ingestion Studio document inventory. Live refresh already works via existing SSE-driven React Query invalidation — no realtime changes needed.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 / structlog / pytest; React 19 + TS strict + Vite 8 / Vitest / Playwright.

## Global Constraints

- `pyright` (bare, strict config) clean including tests; no `Any`.
- pytest coverage ≥ 85% per package.
- `backend/.venv/bin/ruff check --no-cache .` clean (sandbox cache quirk).
- After ANY frontend-consumed Pydantic change: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` then `cd chili_app && npm run codegen:api`.
- Frontend imports DTOs only from `src/api/contracts.ts`; never hand-write wire types.
- E2E must run against the real stack (`make dev`), no `page.route` mocks of the subject under test; `page.route` patterns must be `/api/`-anchored.
- No new hardcoded domain types; everything config-driven.

## Design decisions (rationale recorded once, referenced by tasks)

1. **Gap 2 extractor selection:** `llm.provider == "local"` is the documented echo stub (`llm/adapters/in_memory.py`), useless for extraction. Real providers get `LlmDocumentExtractor` (fixing `coordinator.py:869` which never passes `llm_client`, contradicting the BL-014 comment in `medicare_fraud_cms_desynpuf.yaml:55-57`); `local` keeps the deterministic `PatternDocumentExtractor` baseline. We do NOT fake NER inside the stub.
2. **Gap 3 decimal target type is `float`, not `Decimal`:** `_matches_property_type` (shared/types.py:333) defines the platform's decimal representation as int|float; range checks use `float(value)`; artifacts round-trip through JSON; graph adapters store floats. Typed-`Decimal` migration is out of scope — noted on backlog story ingestion.14. `list[T]` per-element normalization is impossible (PropertyDefinition has no element type) — noted as deviation.
3. **Gap 4 scope:** per-document surfacing only (warning count + bounded reason sample). No `WorkflowRunResponse` change — a run-level rollup adds a second read-model seam for the same data (YAGNI). `DocumentsExtractionWarningEvent` finally gets a consumer that persists to `DocumentRecord`.
4. **Gap 4 combined channel:** `DocumentRecord.warning_count`/`warning_reasons` accumulate parse warnings (from `DocumentsParsedEvent.warning_count`) and extraction/validation warnings (from the warning event). Reasons capped at 10 (matches `_MAX_EXTRACTION_WARNING_SAMPLE`).
5. **Gap 2b event enrichment:** `handle_entities_extracted` already loads the `ExtractionResult`; its `warnings` (e.g. "LLM returned non-JSON for chunk …", "No entity candidates extracted…") join `sample_reasons` and the publish trigger, so empty extractions are explained, not silent.

---

### Task 1: Commit the lockfile repair (build was broken)

**Files:**
- Modify: `chili_app/package-lock.json` (already regenerated in working tree)

- [ ] **Step 1: Verify `npm ci` passes** — `cd chili_app && npm ci --dry-run --no-audit --no-fund` → exit 0.
- [ ] **Step 2: Commit**
```bash
git add chili_app/package-lock.json
git commit -m "fix(app): regenerate package-lock.json out of sync with @mermaid-js/mermaid-cli deps

npm ci failed with 'Missing: puppeteer@24.43.1 from lock file', breaking the
frontend Docker image build and make dev."
```

### Task 2: Gap 5 — interpolate %-style args in structlog output

**Files:**
- Modify: `backend/shared/logging.py` (shared_processors list)
- Test: `backend/tests/shared/test_logging.py`

**Interfaces:** none new; behavior change only.

- [ ] **Step 1: Write failing test** — capture a rendered line for `logger.info("processed %s items", 3)` and assert `"processed 3 items"` appears and `positional_args` does not.
- [ ] **Step 2: Run it** — `pytest tests/shared/test_logging.py -v` → new test FAILS.
- [ ] **Step 3: Implement** — add `structlog.stdlib.PositionalArgumentsFormatter()` to `shared_processors` (after `add_logger_name`, before `_correlation_id_processor`).
- [ ] **Step 4: Test passes; whole shared suite green.**
- [ ] **Step 5: Commit** — `fix(shared): interpolate %-style positional args in structlog output`.

### Task 3: Gap 1 — accept text/html uploads

**Files:**
- Modify: `backend/config/schema.py:295-304` (ValidationConfig.allowed_content_types default gains `"text/html"`)
- Test: `backend/tests/config/test_schema.py` (or nearest config test module), `backend/tests/api/test_input_validation.py`
- Regenerate: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`

- [ ] **Step 1: Failing tests** — (a) `ValidationConfig().allowed_content_types` contains `"text/html"`; (b) API upload test posting `files=...;type=text/html` no longer 415s (mirror existing accepted-type test).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Add `"text/html"` to the default list** (after `"text/csv"`).
- [ ] **Step 4: Tests pass.**
- [ ] **Step 5: Regen contracts** (export_openapi + codegen); commit all together — `feat(config): allow text/html uploads (HTML parser was unreachable via API)`.

### Task 4: Gap 3 — property normalization before validate_entity (backlog ingestion.14)

**Files:**
- Create: `backend/ingestion/normalization.py`
- Modify: `backend/ingestion/validator.py` (normalize inside `validate_extraction` before `validate_entity`)
- Test: `backend/tests/ingestion/test_normalization.py` (new), `backend/tests/ingestion/test_validator.py`

**Interfaces:**
- Produces: `normalize_properties(properties: dict[str, object], definition: EntityDefinition) -> tuple[dict[str, object], list[str]]` — returns (normalized copy, error strings prefixed `normalization_failed:`). Per-type: DECIMAL str→float (period or comma separator), INTEGER str→int, BOOLEAN yes/no/true/false/1/0→bool, DATE common formats (`%m/%d/%Y`, `%Y/%m/%d`, `%d.%m.%Y`)→ISO string, ENUM case-insensitive→canonical config value, STRING strip whitespace. Values already of the target type pass through; unparseable values produce an error and the entity is dropped via `entity_errors`.

- [ ] **Step 1: Failing unit tests** — success+failure per normalizer, incl. bool `True` not treated as int, ISO date passthrough.
- [ ] **Step 2: Run → FAIL (module missing).**
- [ ] **Step 3: Implement `normalization.py`** (pure functions, fully typed).
- [ ] **Step 4: Unit tests pass.**
- [ ] **Step 5: Failing validator integration test** — candidate `claim` with `amount="412.00"` (string) now validates; `amount="not-a-number"` lands in `entity_errors` with `normalization_failed`.
- [ ] **Step 6: Wire into `ExtractionResultValidator.validate_extraction`** after `_partition_entity_properties`, before `validate_entity`.
- [ ] **Step 7: Full ingestion suite green; coverage ≥85% on normalization.py.**
- [ ] **Step 8: Commit** — `feat(ingestion): normalize property values before schema validation (ingestion.14)`.

### Task 5: Gap 2a — coordinator actually uses the LLM extractor for real providers

**Files:**
- Modify: `backend/agent/coordinator.py:869` (+ new helper `build_document_extractor(config, llm_client)` near `build_llm_client`)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: `build_document_extractor(config: DomainConfig, llm_client: LlmClientProtocol) -> DocumentExtractorProtocol` — returns `LlmDocumentExtractor` when `config.llm.provider != "local"`, else `PatternDocumentExtractor`.

- [ ] **Step 1: Failing tests** — provider `"local"` → `PatternDocumentExtractor`; provider `"ollama"` (with a stub client) → `LlmDocumentExtractor`.
- [ ] **Step 2–4: TDD cycle**; replace the `create_document_extractor(...)` call at :869 with the helper.
- [ ] **Step 5: Commit** — `fix(agent): route document extraction through LlmDocumentExtractor for real LLM providers`.

### Task 6: Gap 2b — extraction-stage warnings reach the warning event

**Files:**
- Modify: `backend/agent/coordinator.py` (`_collect_extraction_warning_reasons` gains extraction warnings; publish trigger includes them)
- Test: `backend/tests/agent/test_coordinator.py`

- [ ] **Step 1: Failing test** — an `ExtractionResult` with `warnings=["LLM returned non-JSON for chunk c1: …"]` and clean validation still publishes `DocumentsExtractionWarningEvent` with that reason in `sample_reasons`.
- [ ] **Step 2–4: TDD cycle** — pass `extraction_result.warnings` into `_collect_extraction_warning_reasons(report, extraction_warnings)`; trigger on `or extraction_warnings`.
- [ ] **Step 5: Commit** — `feat(agent): include extraction-stage warnings in documents.extraction_warning events`.

### Task 7: Gap 4a — persist warnings on DocumentRecord

**Files:**
- Modify: `backend/knowledgebases/models.py` (DocumentRecord + `warning_count: int = 0`, `warning_reasons: list[str] = []`)
- Modify: `backend/knowledgebases/protocols.py` (+ `record_document_warnings(knowledge_base_id, document_id, *, additional_count: int, reasons: list[str]) -> DocumentRecord | None` — accumulates count, appends reasons capped at 10)
- Modify: `backend/knowledgebases/adapters/in_memory.py`, `backend/knowledgebases/adapters/object_store.py`
- Modify: `backend/agent/coordinator.py` — `handle_documents_parsed` records `reference.warning_count`; new `handle_documents_extraction_warning(event, *, kb_repository)` consumer registered in the dispatch chain (coordinator.py:2900-2938) records dropped/empty reasons. Worker deps already include `kb_repository`.
- Test: `backend/tests/knowledgebases/` (repository contract tests for both adapters), `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: `DocumentRecord.warning_count/warning_reasons` consumed by Task 8. Verify at execution that `DocumentRecord.id == source_document_id` from events (one probe against the running stack; adjust lookup to `get_document` by that id).

- [ ] **Step 1: Failing repository tests** (both adapters: accumulate, cap at 10, unknown doc → None).
- [ ] **Step 2–4: TDD cycle for repository.**
- [ ] **Step 5: Failing coordinator tests** — parsed event with `warning_count=2` persists 2; extraction-warning event persists dropped-entity reasons.
- [ ] **Step 6–7: Implement handlers; suites green.**
- [ ] **Step 8: Commit** — `feat(knowledgebases): persist per-document parser/extraction warnings`.

### Task 8: Gap 4b — expose warnings on DocumentSummary

**Files:**
- Modify: `backend/api/routers/knowledgebases.py:82-91` (DocumentSummary + `warning_count: int = 0`, `warning_reasons: list[str] = []`; populate in `list_knowledge_base_documents` and any single-doc projection)
- Test: `backend/tests/api/` document-list test asserts fields present
- Regenerate: openapi + codegen (CI drift gate)

- [ ] **Steps: TDD cycle, regen contracts, commit** — `feat(api): expose document warning count and reasons`.

### Task 9: Gap 4c — render warnings in Ingestion Studio

**Files:**
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (DocumentInventory rows :636-706 — add `<Chip tone="warning">{n} warning{s}</Chip>` beside the status chip at :681-683 when `warning_count > 0`, with `title={warning_reasons.join('\n')}`; selected-document detail panel lists reasons)
- Test: Vitest component test for the chip logic; existing tests stay green
- Uses: generated `KnowledgeBaseDocumentResponse` (contracts.ts:110) — fields arrive via codegen from Task 8

- [ ] **Steps: failing Vitest → implement → pass → lint/build clean → commit** — `feat(app): surface per-document ingestion warnings in Ingestion Studio`.

### Task 10: Gap 4d — Playwright e2e against the live stack

**Files:**
- Create/modify: `chili_app/e2e/` spec — full stack (`make dev`): create KB, upload ragged CSV via UI, await ready, assert warning chip visible with reason text.

- [ ] **Steps: write spec, run against running stack, green, commit** — `test(e2e): ingestion warning surfacing end-to-end`.

### Task 11: Docs + backlog reconciliation

**Files:**
- Modify: `backend/ingestion/README.md` (normalization pass, extractor selection), `backend/README.md`, `docs/architecture.md` (extractor selection rule, warning surfacing path), `docs/backlog/ingestion.md` (ingestion.14 → done with float-not-Decimal + no-list[T] notes), `docs/backlog/frontend.md`/`api.md` if they track warning surfacing, `chili_app/README.md` if commands changed.

- [ ] **Steps: update docs, commit** — `docs: record normalization, extractor selection, and warning surfacing changes`.

### Task 12: Full validation

- [ ] Backend gates: `pytest --cov` (≥85% per package), `pyright` (bare), `ruff check --no-cache .`.
- [ ] Frontend gates: `npm run lint`, `npm run build`, `npm run test:run`; contracts drift check (regen produces no diff).
- [ ] Rebuild stack (`make down && make dev`), re-run the verification scenario:
  - HTML upload → 202, parsed with heading/link/table fidelity, entities path runs.
  - Ragged CSV → claim entities WITH `amount` survive into the graph (KB entity_count > 0); warning chip shows parse + validation reasons in UI.
  - Worker logs interpolated (no literal `%s`).
  - `documents.extraction_warning` events carry extraction-stage reasons.
- [ ] Update this plan's checkboxes; report.

## Self-review
- Spec coverage: gap 1→Task 3; gap 2→Tasks 5,6 (+ decision 1); gap 3→Task 4; gap 4→Tasks 7-10; gap 5→Task 2; broken build→Task 1; CLAUDE.md doc rules→Task 11; validation→Task 12. ✓
- No placeholders: interface signatures and file:line anchors given; one execution-time verification (DocumentRecord.id keying) explicitly flagged with the probe to run. ✓
- Type consistency: `record_document_warnings` signature used in Tasks 7/8; `warning_count`/`warning_reasons` names consistent across record, summary, frontend. ✓
