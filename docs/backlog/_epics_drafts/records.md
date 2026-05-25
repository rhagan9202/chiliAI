## File: docs/backlog/records.md

**Scope:** `backend/records/` — structured/tabular ingestion (CSV/JSONL/api-push → `raw_records` → Flow 1 fan-out).
**Scope source:** Re-derived from current code at HEAD against `docs/architecture.md` §5.2 (records row), §6.3 (Flow 1), §6.5 (May 2026 enhancements).
**Format:** imperative epic title + one-line gap with `file:line` evidence. Done work skipped.

---

## Status snapshot (skip, do not turn into epics)

The following are already implemented and verified in code at HEAD — do not generate stories for them:

- File and api-push parsers: `CsvFileSource`, `JsonlFileSource`, `ApiPushSource` (`backend/records/adapters/sources/`).
- Feed-schema coercion + validation reusing `validate_entity`: `backend/records/validation.py:111`.
- `raw_records` Postgres table + GIN(payload) + correlation index: `backend/database/migrations/versions/0001_persistence_baseline.py:30-48`.
- Idempotent persist via natural-PK `ON CONFLICT DO NOTHING`: `backend/records/adapters/postgres.py:20-26`.
- KB-scoped delete on both adapters: `backend/records/adapters/in_memory.py:45`, `backend/records/adapters/postgres.py:87`.
- Embed + index records-derived entities into the vector store: `backend/agent/coordinator.py:1639-1676`.
- Records router with RBAC (`analyst`), 409-on-busy KB, 413 size cap from `ValidationConfig.max_file_size_mb`: `backend/api/routers/records.py:42-107`.
- `id_template` composite-key support for segmented claim feeds: `backend/config/schema.py:341`, `backend/records/service.py:40-48`.
- `allow_extra_fields` passthrough for wide files (DE-SynPUF carrier_claims 142 cols): `backend/config/schema.py:346`, `backend/records/validation.py:140-148`.

---

## Epics

### records.E1 — Add JSONL upload coverage to the feed config inventory
Gap: medicare_fraud_cms_desynpuf.yaml declares every feed as `source: file_upload` with no format hint and the router only branches on filename extension (`backend/api/routers/records.py:30-39`); no per-feed declaration of `formats: [csv, jsonl]` exists, so a wrong-format upload silently passes router validation and dies in `read_rows`. Add per-feed allowed-format declaration and 415 enforcement.

### records.E2 — Enforce row-level idempotency across re-ingest of identical files
Gap: `RecordsService.register_records` always mints a fresh `correlation_id` (`backend/records/service.py:36`) and `_INSERT_SQL` conflict-resolves only on the natural PK (`backend/records/adapters/postgres.py:25`); a re-uploaded identical file produces a new batch with `accepted_count=0` per existing rows but emits a duplicate `RecordsIngestedEvent` and re-runs Flow 1 fan-out. Wire `content_hash` into a submission-level dedup check (e.g. file-hash index on `(knowledge_base_id, feed_name, file_content_hash)`) and short-circuit before publishing.

### records.E3 — Land Plan-C persistence for the `pde` feed
Gap: domain config declares 9 feeds (`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml:97-384`: 3 beneficiary + 2 carrier + inpatient + outpatient + pde + nppes_providers) but the task brief lists only 8; verify whether `pde` (Part D events) is intentionally excluded or simply missing. Either remove from config or add the entity/relationship mappings and fixture.

### records.E4 — Stream large file uploads instead of in-memory read
Gap: `upload_record_file` calls `await file.read()` (`backend/api/routers/records.py:75`) loading the entire payload into memory before parsing, gated only by a configurable MB ceiling; CMS files commonly run 1–10 GB. Add a chunked/streaming reader for `CsvFileSource` and `JsonlFileSource` (iterate `UploadFile.file` line-by-line) and lift or remove the 413 cap.

### records.E5 — Add resumable batch ingest with checkpointing
Gap: nothing in `backend/records/` supports resumption — a 5M-row CSV that fails mid-way after persisting 2M rows is restarted from row 0 (relying on PK idempotency for correctness but redoing all parse + validate work). Introduce a batch checkpoint per `correlation_id` (or per file-hash) recording `last_row_index` so retries skip already-persisted rows.

### records.E6 — Emit per-feed observability metrics
Gap: `records/` contains zero `logger`, metric, or counter calls (verified by `grep -rn "logger" backend/records/` returning no hits in the module). `RecordsService.register_records` and the router log nothing on success, no per-feed counter for rows ingested/rejected, no last-success timestamp surface. Add structured logging + Prometheus counters (`records_rows_ingested_total{feed}`, `records_validation_errors_total{feed}`, `records_last_ingest_at{feed,kb}`).

### records.E7 — Add per-feed data-quality checks beyond schema coercion
Gap: `validate_rows` (`backend/records/validation.py:111`) only enforces required-field presence, type coercion, and `validate_entity` range/pattern checks; there is no null-rate threshold, outlier detection, or anomaly check on per-batch distributions. Add a configurable `quality_checks` block per feed (e.g. `max_null_rate`, `expected_row_count_range`) with batch-level rejection and DLQ-emit on breach.

### records.E8 — Add per-feed schema versioning and migration semantics
Gap: `RecordFeedConfig` has no `schema_version` field (`backend/config/schema.py:331-349`); the only `schema_version` is the top-level `DomainConfig.schema_version` (`backend/config/schema.py:370`). A field rename or type change in `record_schema` silently retroactively validates old rows because nothing persists which feed-version each `raw_record` was validated against. Add `RecordFeedConfig.schema_version`, stamp it onto each `RawRecord` payload, and document a feed-versioning migration playbook.

### records.E9 — Add tenant scoping to feed registration and KB delete cascade
Gap: `RawRecord` (`backend/records/models.py:30`) and `RawRecordStore` queries are keyed on `knowledge_base_id` only — there is no `tenant_id` column on `raw_records` and no tenant filter on `load_batch` / `delete_by_kb` (`backend/records/adapters/postgres.py:28-39, 87-97`). Once `_multitenancy.md` lands, add tenant scoping to the table + all adapter queries and the API dependency chain.

### records.E10 — Add rate limiting and submission-size policy to the records API
Gap: `POST /records/{kb}/files` and `POST /records/{kb}/push` (`backend/api/routers/records.py:42, 110`) enforce only RBAC role and an MB cap; no per-tenant / per-IP rate limit, no row-count ceiling on api-push, and no quota interaction with `_security.md`. Add token-bucket rate limiting and a `max_rows_per_submission` row cap configurable per feed.

### records.E11 — Add fixtures and golden tests for the missing CMS feeds
Gap: `backend/tests/records/fixtures/cms/` ships fixtures only for `beneficiary_2008`, `carrier_claims`, `inpatient_claims`, `outpatient_claims`, and `pde` — there are no fixtures for `beneficiary_2009`, `beneficiary_2010`, or `nppes_providers`. Add sample CSVs and a `test_cms_ingestion` golden test per feed asserting deterministic entity/relationship counts.

### records.E12 — Document and surface the no-`GraphUpdatedEvent` Flow-1 quirk
Gap: `handle_records_ingested` calls `upsert_records_graph` which intentionally does not publish `GraphUpdatedEvent` (`docs/architecture.md:693`, `backend/agent/coordinator.py:1635-1637`) — meaning Flow 2 (graph metrics) and Flow 3 (risk recompute) do NOT trigger from records ingest, only from document ingest. This is a design choice but undocumented in `backend/records/README.md` and frequently surprises operators; either publish a records-targeted `GraphUpdatedEvent` (gated by config) or add a `## Known Quirks` section calling this out plus a story to formalize the decision.

### records.E13 — Add admin endpoint to list and inspect declared feeds
Gap: there is no `GET /records/feeds` endpoint — analysts and the frontend learn the legal `feed` form values only by reading the YAML. Surface `RecordsConfig.feeds` (name, record_type, source, required schema fields, observation metrics) through a read-only API and expose it in the workbench upload UI.

---

## Provisional cross-cutting edges

- `records.E6` ↔ `_observability.md` — per-feed metrics belong under the platform observability story (records adds the per-feed labels).
- `records.E9` ↔ `_multitenancy.md` — depends on the platform-wide tenant model.
- `records.E10` ↔ `_security.md` + `api.md` — rate limiting middleware is API-cross-cutting.
- `records.E4` ↔ `api.md` — streaming `UploadFile` handling is an API-platform concern.
- `records.E12` ↔ `agent.md` — Flow-1 vs Flow-2/3 wiring lives in the coordinator.

---

## Open questions

1. **PDE feed status (E3):** is `pde` deliberately scoped out of the Plan-C demo set (so should drop from yaml), or genuinely planned (so needs fixture + Plan-C verification)? Brief says "8 feeds"; config has 9.
2. **Re-ingest semantics (E2):** is the intended behavior to (a) silently skip identical re-uploads, (b) accept and dedup via PK with no event re-fire, or (c) treat each upload as a fresh batch and let downstream consumers tolerate replay? Architecture §6.3 says "idempotent upsert keyed on (kb, record_type, record_id)" — which matches (b) but the event is still re-fired.
3. **Streaming threshold (E4):** keep the current 413 cap as a safety net or remove entirely once streaming lands? Affects `ValidationConfig.max_file_size_mb` and the API contract.
4. **Schema versioning policy (E8):** are feed schema changes expected to be additive-only (then versioning is documentation), or breaking changes allowed (then a real migration model is needed)?
