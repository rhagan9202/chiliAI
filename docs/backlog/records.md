# records backlog

> **Scope:** Structured/tabular ingestion (CSV/JSONL/api-push → raw_records → Flow 1 fan-out), feed registry, validation, idempotency, observability, streaming, pull-based origin sources (object store / HTTP / stream).
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story records.01: Declare and enforce per-feed allowed file formats

**ID:** records.01
**Status:** in-progress
**Prerequisites:** []
**Unblocks:** [_plugins.01]
**Estimated size:** M

**As a** domain operator,
**I need** each `RecordFeedConfig` to declare which file formats (CSV / JSONL) it accepts and the upload router to reject mismatches with 415,
**so that** a misnamed or wrong-format upload is rejected at the boundary instead of dying with a confusing parser error mid-batch.

### Current State
- `RecordFeedConfig.accepted_formats` exists with default `["csv", "jsonl"]`, and `_resolve_feed_formats` / `upload_record_file` reject mismatched uploads with HTTP 415 before reading the body.
- Tests cover custom `accepted_formats` on config models and a router-level 415 when a CSV-only feed receives `.jsonl`.
- Residual gap: `medicare_fraud_cms_desynpuf.yaml` still relies on the default `["csv", "jsonl"]` for its file-upload feeds; it does not explicitly declare `accepted_formats: [csv]` for CMS CSV feeds.

### Acceptance Criteria
- [ ] `RecordFeedConfig.accepted_formats: list[Literal["csv", "jsonl"]]` field added with default `["csv", "jsonl"]` (back-compat) in `backend/config/schema.py`.
- [ ] `_validate_cross_references` in `backend/config/schema.py` rejects an empty `accepted_formats` list with a clear error.
- [ ] `upload_record_file` in `backend/api/routers/records.py` looks up the feed BEFORE parsing and returns `HTTP 415` with `detail` naming the feed + allowed formats when extension is not in `accepted_formats`.
- [ ] `medicare_fraud_cms_desynpuf.yaml` updated to declare `accepted_formats: [csv]` for every existing feed (matches today's behavior).
- [ ] Test in `backend/tests/api/test_records_router.py` asserts 415 with feed-named detail when CSV-only feed receives a `.jsonl` upload, and 202 when the same feed receives a `.csv` upload.
- [ ] `backend/records/README.md` "Feed configuration" section documents the new field.

### Verification
- `pytest backend/tests/api/test_records_router.py backend/tests/config/test_schema.py -q` green.
- Coverage ≥ 85% on `backend/api/routers/records.py` and the `config.schema` changes.
- Manual: `curl -F feed=beneficiary_2008 -F file=@x.jsonl /records/kb1/files` returns 415; `-F file=@x.csv` returns 202.

### Code touch points
- `backend/config/schema.py` (modify — add `accepted_formats` to `RecordFeedConfig`, cross-ref validation)
- `backend/api/routers/records.py` (modify — feed lookup + 415 enforcement before parse)
- `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (modify — declare formats on each feed)
- `backend/records/README.md` (modify — feed configuration docs)
- `backend/tests/api/test_records_router.py` (modify — 415-on-format-mismatch tests)
- `backend/tests/config/test_schema.py` (modify — accepted_formats validation tests)

---

## Story records.02: Short-circuit identical-file re-uploads with submission-level dedup

**ID:** records.02
**Status:** done
**Prerequisites:** [database.01]
**Unblocks:** [config.13, records.05]
**Estimated size:** M
**Done:** implemented with `submission_hash_for`, `record_submissions` migration `0004_record_submissions`, `RawRecordStore.was_submitted` / `record_submission`, duplicate receipts, no event publish on duplicate, and HTTP 200 for duplicate file/push submissions.

**As a** worker operator,
**I need** the records service to detect a byte-identical (or row-set-identical) re-upload of the same feed and short-circuit before publishing `RecordsIngestedEvent`,
**so that** an operator who clicks "upload" twice does not re-fire Flow 1 fan-out, re-run graph upserts, and emit a duplicate workflow record.

### Current State
- `RecordsService.register_records` computes an order-independent submission hash from the feed name plus per-row content hashes before persisting.
- On duplicate, the service returns a duplicate receipt and skips both `RawRecordStore.persist` and `RecordsIngestedEvent` publish.
- File and push endpoints set HTTP 200 when `receipt.duplicate` is true; fresh submissions still return 202.

### Acceptance Criteria
- [x] New `record_submissions` table captures `(knowledge_base_id, submission_hash)` with a composite primary key via `0004_record_submissions`.
- [x] `RecordsService.register_records` computes a deterministic submission hash over the sorted list of per-row `content_hash` values BEFORE persisting; on a duplicate hit it returns a `RecordIngestReceipt` with `accepted_count=0`, `duplicate=True` and DOES NOT publish `RecordsIngestedEvent`.
- [x] `RecordIngestReceipt` includes `duplicate`, `duplicate_count`, `rejected_count`, and `rejected`.
- [x] HTTP response on a duplicate is `200 OK` (not 202).
- [x] Unit tests cover duplicate submissions on service/store paths and router status handling.
- [x] `backend/records/README.md` documents submission-level dedup in "Idempotency, partial acceptance, and format gating (BL-015)".

### Verification
- `pytest backend/tests/records -q` green with new dedup tests.
- Coverage ≥ 85% on `backend/records/service.py` and the new migration.
- Manual: upload `beneficiary_2008_sample.csv` twice; check Redis stream `records.ingested` has exactly one entry and `duplicate=true` on the second receipt.

### Code touch points
- `backend/database/migrations/versions/0004_record_submissions.py`
- `backend/records/models.py`
- `backend/records/service.py`
- `backend/records/service_models.py`
- `backend/records/adapters/protocols.py`
- `backend/records/adapters/in_memory.py`
- `backend/records/adapters/postgres.py`
- `backend/api/routers/records.py`
- `backend/records/README.md`
- `backend/tests/records/test_service.py`
- `backend/tests/records/test_in_memory_store.py`
- `backend/tests/records/test_postgres_store.py`
- `backend/tests/api/test_records_router.py`

---

## Story records.03: Resolve `pde` feed status (drop or land Plan-C fan-out)

**ID:** records.03
**Status:** in-progress
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** domain owner,
**I need** the `pde` (Part D events) feed in `medicare_fraud_cms_desynpuf.yaml` to either be removed or fully wired (entity mappings + relationships + fixture-backed golden test),
**so that** the declared 9th feed is not a half-wired surface that ingests `raw_records` but never produces graph entities or observations.

### Current State
- `medicare_fraud_cms_desynpuf.yaml:349-380` declares `name: pde`, `record_type: pde_record`, `id_field: PDE_ID`, with a `record_schema`. The Tennessee subset materializer (`tools/sample_data/build_tennessee_subset.py`) references PDE rows.
- **Update (2026-06-01):** the `pde` feed has since been **wired toward the Plan-C path** — it now declares `entities` and a `billed_for` `relationships` block (`medicare_fraud_cms_desynpuf.yaml:375`), so `map_batch` produces graph entities and edges rather than zero. A golden test asserts deterministic entity/relationship counts after the fan-out (`backend/tests/records/test_cms_ingestion.py:268` `test_pde_feed_creates_drug_claims_and_billed_for_edges`), alongside validation and column-count coverage.
- Residual gap (why this is in-progress, not done): the feed declares no `observations` mapping. The wire-vs-drop decision is now recorded in `backend/records/README.md` ("CMS Feed Inventory"), but `docs/architecture.md` §6.3 still has no callout and no final `Done:` line closes the story.

### Acceptance Criteria
- [ ] Decision recorded in `backend/records/README.md` ("CMS feed inventory" section) and `docs/architecture.md` §6.3 callout: `pde` is either (a) dropped, or (b) wired end-to-end.
- [ ] If dropped: remove `pde` block from `medicare_fraud_cms_desynpuf.yaml`, delete `backend/tests/records/fixtures/cms/pde_sample.csv`, and remove PDE handling from `tools/sample_data/build_tennessee_subset.py`.
- [ ] If wired: add a `pde_event` (or similar) entity to top-level `entities:`, declare `entities`/`relationships`/`observations` in the `pde` feed block, add a `prescribed_by` or analogous relationship type if needed, and add a `prescription` link (claim ↔ provider) if appropriate.
- [ ] Golden test in `backend/tests/records/test_cms_ingestion.py` (or new file) asserts deterministic entity + relationship + observation counts after Flow 1 for a `pde_sample.csv` ingest.
- [ ] `docs/backlog/records.md` story closed with the chosen path cited in the `Done:` line.

### Verification
- `pytest backend/tests/records -q -k pde` green.
- Coverage ≥ 85% on changed mapper paths.
- Manual: `python -m tools.sample_data.build_tennessee_subset --help` runs without referencing dropped PDE (drop case) or produces a non-empty PDE export (wire case).

### Code touch points
- `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (modify — drop block, or add entities/relationships/observations)
- `backend/tests/records/fixtures/cms/pde_sample.csv` (delete or keep)
- `tools/sample_data/build_tennessee_subset.py` (modify — drop PDE handling, or keep)
- `backend/records/README.md` (modify — CMS feed inventory)
- `docs/architecture.md` (modify — §6.3 callout)
- `backend/tests/records/test_cms_ingestion.py` (modify — pde golden test if wired)

---

## Story records.04: Stream large file uploads instead of full in-memory read

**ID:** records.04
**Status:** planned
**Prerequisites:** []
**Unblocks:** [records.05, records.14]
**Estimated size:** L

**As an** analyst,
**I need** CSV and JSONL uploads to stream row-by-row through the parser instead of being fully `await file.read()`-ed into memory,
**so that** CMS-scale files (1–10 GB) can be ingested without OOMing the API container and without raising the 413 cap to a memory-dangerous value.

### Current State
- `upload_record_file` now reads in 64 KiB chunks through `_read_upload_file_with_limit`, but still materializes the full payload as `bytes` before parsing.
- `CsvFileSource.read_rows(raw: bytes)` (`backend/records/adapters/sources/file_source.py:23-48`) and `JsonlFileSource.read_rows(raw: bytes)` (`:54-77`) both take `bytes` and return a fully-materialized `list[dict[str, object]]`.
- The 413 ceiling is governed by `ValidationConfig.max_file_size_mb`; raising it still linearly raises API memory pressure because chunks are joined before parsing.
- `RecordsService.register_records` takes a `list[dict[str, object]]` (`backend/records/service.py:30-35`) so the whole batch is in memory anyway — streaming only the parser stage is a no-op without a service refactor.
- **PM prereq cleanup (2026-06-23):** original prereq `api.10` ("Adopt a uniform paginated-collection contract") was mislabeled — this streaming-upload story has no dependency on the list-pagination contract, and no api streaming-upload story exists. Edge dropped; this is a self-contained records/service refactor.

### Acceptance Criteria
- [ ] `RecordSourceProtocol` (`backend/records/adapters/protocols.py`) gets a new method `iter_rows(stream: IO[bytes]) -> Iterator[dict[str, object]]` (keep `read_rows` for back-compat callers; mark deprecated).
- [ ] `CsvFileSource.iter_rows` and `JsonlFileSource.iter_rows` implement chunked / line-by-line streaming reading from `UploadFile.file` (BinaryIO).
- [ ] `RecordsService.register_records` (`backend/records/service.py`) accepts an iterator/generator of rows and persists in chunks of `CHILI_RECORDS_PERSIST_CHUNK` (default 5000) rows; submission hash (records.02) updated to a streaming SHA-256 over per-row content hashes.
- [ ] `upload_record_file` (`backend/api/routers/records.py`) wraps `file.file` (the underlying `SpooledTemporaryFile`) and passes the iterator to the service — no `await file.read()`.
- [ ] `ValidationConfig.max_file_size_mb` semantics changed: now bounds the streaming-uploaded byte count via a `Content-Length` check (still 413 on exceed) instead of in-memory size; default raised to 5120 (5 GB) in code defaults.
- [ ] Integration test in `backend/tests/api/test_records_router.py` uploads a synthetically generated 500 MB CSV and asserts peak memory growth < 200 MB (via `tracemalloc` or `resource.getrusage`).
- [ ] `backend/records/README.md` documents the streaming model and the new chunk-size env knob.

### Verification
- `pytest backend/tests/records backend/tests/api -q` green.
- Coverage ≥ 85% on `records/service.py` and the source adapters.
- Manual: upload a 1 GB synthetic CSV against `docker compose -f docker-compose.dev.yaml` API; container memory stays below 1 GB peak; ingest completes.

### Code touch points
- `backend/records/adapters/protocols.py` (modify — add `iter_rows`)
- `backend/records/adapters/sources/file_source.py` (modify — streaming `iter_rows` impls)
- `backend/records/adapters/sources/api_push_source.py` (modify — keep buffered, document why)
- `backend/records/service.py` (modify — accept iterator, chunked persist, streaming submission-hash)
- `backend/api/routers/records.py` (modify — stream `file.file`, drop `await file.read()`)
- `backend/config/schema.py` (modify — `ValidationConfig.max_file_size_mb` default 5120)
- `backend/records/README.md` (modify — streaming model docs)
- `backend/tests/records/test_file_source.py` (modify — iter_rows tests)
- `backend/tests/api/test_records_router.py` (modify — large-file streaming test)

---

## Story records.05: Add resumable batch ingest with checkpointing

**ID:** records.05
**Status:** planned
**Prerequisites:** [records.02, records.04, database.01]
**Unblocks:** []
**Estimated size:** L

**As a** worker operator,
**I need** a checkpoint per (kb, feed, submission-hash, row-cursor) so that a retried upload skips already-persisted rows,
**so that** a 5M-row CSV that crashes at row 3M restarts from row 3M instead of reparsing and re-validating all 3M from the top.

### Current State
- Nothing in `backend/records/` records a per-submission progress cursor — `RecordsService.register_records` (`backend/records/service.py:30-86`) is a single transactional persist call; on crash the entire batch is replayed from row 0.
- PK idempotency in `_INSERT_SQL` (`backend/records/adapters/postgres.py:20-26`) makes replay safe but pays the full parse + coerce + validate cost.
- There is no `record_batch_checkpoints` table in the persistence baseline (`backend/database/migrations/versions/0001_persistence_baseline.py`).
- Streaming (records.04) makes resumption meaningful — without streaming the whole batch is in memory anyway.

### Acceptance Criteria
- [ ] New `record_batch_checkpoints` table created via Alembic migration: columns `(knowledge_base_id, feed_name, submission_hash, last_row_index, last_updated_at)` with PK `(knowledge_base_id, feed_name, submission_hash)`.
- [ ] `RawRecordStore` protocol (`backend/records/adapters/protocols.py`) gains `load_checkpoint(...)` and `save_checkpoint(...)` methods, implemented in both `InMemoryRawRecordStore` and `PostgresRawRecordStore`.
- [ ] `RecordsService.register_records` loads the checkpoint at start, skips rows whose index ≤ `last_row_index`, and saves the checkpoint every `CHILI_RECORDS_CHECKPOINT_EVERY` rows (default 10_000).
- [ ] On successful completion, the checkpoint row is deleted (or marked complete) so a follow-up identical submission triggers the records.02 dedup path, not a no-op resume.
- [ ] Unit test in `backend/tests/records/test_service.py`: simulate a persist failure at row 1500, retry the same submission, assert the second run skips rows 0-1499 and persists rows 1500+.
- [ ] `backend/records/README.md` documents checkpoint semantics and recovery behavior.

### Verification
- `pytest backend/tests/records -q -k checkpoint` green.
- Coverage ≥ 85% on `records/service.py` and the checkpoint persistence path.
- Manual: kill the worker mid-batch on a 1M-row upload; restart; verify Postgres `record_batch_checkpoints` row exists with a non-zero `last_row_index` and the retried batch resumes from there.

### Code touch points
- `backend/database/migrations/versions/0004_record_batch_checkpoints.py` (new)
- `backend/records/adapters/protocols.py` (modify — add checkpoint methods)
- `backend/records/adapters/in_memory.py` (modify — checkpoint impl)
- `backend/records/adapters/postgres.py` (modify — checkpoint SQL + impl)
- `backend/records/service.py` (modify — load/skip/save checkpoint loop)
- `backend/records/README.md` (modify — checkpoint semantics docs)
- `backend/tests/records/test_service.py` (modify — checkpoint resume test)
- `backend/tests/records/test_postgres_adapter.py` (modify — checkpoint round-trip test)

---

## Story records.06: Emit per-feed observability metrics and structured logs

**ID:** records.06
**Status:** planned
**Prerequisites:** [_observability.01, _observability.02]
**Unblocks:** [api.09, records.07]
**Estimated size:** M

**As a** worker operator,
**I need** per-feed Prometheus counters and structured log lines for every records submission,
**so that** I can answer "how many rows did `carrier_claims_a` ingest in the last hour?", "which feed is rejecting validations?", and "when was the last successful `nppes_providers` upload?" without grepping raw worker logs.

### Current State
- `backend/records/` contains zero `logger`, metric, or counter calls — `grep -rn "logger\|Counter\|Histogram" backend/records/` returns no hits in the module.
- `RecordsService.register_records` (`backend/records/service.py:30-86`) and `upload_record_file` (`backend/api/routers/records.py:48-107`) log nothing on success.
- `backend/monitoring/metrics.py:28` is the only existing per-stage histogram precedent (architecture §11.2).
- `_observability.01` (structured logging baseline) and `_observability.02` (Prometheus metrics surface) are the platform prereqs.

### Acceptance Criteria
- [ ] New module `backend/records/metrics.py` defines: `records_rows_ingested_total{feed,record_type}` (Counter), `records_rows_rejected_total{feed,reason}` (Counter), `records_submission_duration_seconds{feed}` (Histogram), `records_last_ingest_at_seconds{feed,knowledge_base_id}` (Gauge of Unix epoch).
- [ ] `RecordsService.register_records` emits a structured log line at INFO on submit start (with `feed`, `kb`, `source_type`, `source_ref`, `correlation_id`) and on submit end (with `accepted_count`, `duration_ms`, `duplicate`).
- [ ] Validation errors raised from `validate_rows` increment `records_rows_rejected_total` with `reason="schema_violation"` per-row.
- [ ] `upload_record_file` emits a structured log line on 415 / 413 / 404 paths with the same correlation-id key for traceability.
- [ ] Test in `backend/tests/records/test_metrics.py` asserts counters move on a successful submit and on a rejected submit.
- [ ] `backend/records/README.md` "Observability" section enumerates the metrics and lists Grafana panel suggestions.

### Verification
- `pytest backend/tests/records -q -k metrics` green.
- Coverage ≥ 85% on `backend/records/metrics.py` and `service.py`.
- Manual: `curl http://localhost:8000/metrics | grep records_` shows the new metric names after a test submission.

### Code touch points
- `backend/records/metrics.py` (new)
- `backend/records/service.py` (modify — instrument register_records)
- `backend/api/routers/records.py` (modify — instrument error paths)
- `backend/records/README.md` (modify — observability section)
- `backend/tests/records/test_metrics.py` (new)

---

## Story records.07: Add per-feed data-quality checks beyond schema coercion

**ID:** records.07
**Status:** planned
**Prerequisites:** [records.06, agent.10]
**Unblocks:** [analytics.06]
**Estimated size:** L

**As a** domain operator,
**I need** configurable batch-level data-quality checks (null-rate thresholds, expected row-count ranges, value-distribution sanity bounds) that reject a batch and route it to the DLQ on breach,
**so that** an obviously-broken CMS extract (e.g. 100% NULL `BENE_BIRTH_DT`) does not silently flood the graph with bad entities.

### Current State
- `validate_rows` (`backend/records/validation.py:111-159`) only enforces required-field presence, type coercion, and `validate_entity` range/pattern checks per-row — there is no batch-level aggregate check.
- No null-rate, outlier, value-distribution, or expected-row-count check exists anywhere in `backend/records/`.
- `RecordFeedConfig` (`backend/config/schema.py:331-349`) has no `quality_checks` block.
- The DLQ wrapper exists in `backend/agent/coordinator.py` (agent.10 prereq); records currently fails open without a DLQ leg of its own.

### Acceptance Criteria
- [ ] New `FeedQualityChecks` Pydantic model in `backend/config/schema.py` with fields: `max_null_rate: dict[str, float]` (per-field), `min_row_count: int | None`, `max_row_count: int | None`, `expected_value_set: dict[str, list[str]]` (per-field allowed-values), `min_unique_count: dict[str, int]` (per-field).
- [ ] `RecordFeedConfig.quality_checks: FeedQualityChecks | None = None` added.
- [ ] New `backend/records/quality.py` with `check_batch(feed, rows) -> list[str]` returning empty list on pass, list of violation strings on fail.
- [ ] `RecordsService.register_records` (`backend/records/service.py`) invokes `check_batch` after `validate_rows`; on failure raises `RecordQualityError` (new in `backend/records/exceptions.py`) which the router maps to `HTTP 422` with the violation list in `detail`.
- [ ] `records_rows_rejected_total` (from records.06) incremented with `reason="quality_check"`.
- [ ] Unit tests in `backend/tests/records/test_quality.py` cover each check kind (null-rate, row-count, value-set, unique-count) green + red.
- [ ] At least one medicare_fraud feed (e.g. `beneficiary_2008`) updated in `medicare_fraud_cms_desynpuf.yaml` with sample `quality_checks` block as a worked example.

### Verification
- `pytest backend/tests/records -q -k quality` green.
- Coverage ≥ 85% on `backend/records/quality.py`.
- Manual: upload a `beneficiary_2008` CSV with 100% NULL `BENE_BIRTH_DT` → API returns 422 with `"max_null_rate violated for BENE_BIRTH_DT: 1.0 > 0.1"` in detail.

### Code touch points
- `backend/config/schema.py` (modify — `FeedQualityChecks` + `quality_checks` field)
- `backend/records/quality.py` (new)
- `backend/records/exceptions.py` (modify — `RecordQualityError`)
- `backend/records/service.py` (modify — invoke `check_batch`)
- `backend/api/routers/records.py` (modify — map `RecordQualityError` to 422)
- `backend/records/metrics.py` (modify — quality_check rejection counter wiring)
- `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (modify — example quality_checks)
- `backend/tests/records/test_quality.py` (new)
- `backend/records/README.md` (modify — quality-check semantics + DLQ behavior)

---

## Story records.08: Add per-feed schema versioning with stamped payload provenance

**ID:** records.08
**Status:** planned
**Prerequisites:** [config.01]
**Unblocks:** []
**Estimated size:** M

**As a** domain operator evolving a feed schema,
**I need** each `RawRecord` to record which `feed_schema_version` it was validated against and the loader to refuse incompatible reads,
**so that** a field rename or type change in `record_schema` does not silently retroactively re-interpret already-stored rows.

### Current State
- `RecordFeedConfig` (`backend/config/schema.py:331-349`) has no `schema_version` field; the only `schema_version` is the top-level `DomainConfig.schema_version` (`backend/config/schema.py:370`) which is platform-wide, not per-feed.
- `RawRecord` (`backend/records/models.py:30-41`) does not stamp the schema version onto the payload.
- The `raw_records` table (`backend/database/migrations/versions/0001_persistence_baseline.py:30-43`) has no `feed_schema_version` column.
- No migration playbook documents how to evolve a feed schema safely; today a rename is a silent breaking change for downstream `map_batch`.

### Acceptance Criteria
- [ ] `RecordFeedConfig.schema_version: str = "1.0"` added in `backend/config/schema.py`.
- [ ] Alembic migration adds `feed_schema_version text NOT NULL DEFAULT '1.0'` column to `raw_records` (backfilled `'1.0'` for existing rows).
- [ ] `RawRecord.feed_schema_version: str` field added; `RecordsService.register_records` (`backend/records/service.py`) populates it from the resolved feed.
- [ ] `_INSERT_SQL` and `_SELECT_SQL` in `backend/records/adapters/postgres.py` updated to include the new column.
- [ ] `map_batch` (`backend/records/mappers/feed_mapper.py`) warns (logger.warning) if a loaded record's `feed_schema_version` differs from the currently-configured feed's `schema_version`, and skips the row with `records_rows_rejected_total{reason="schema_version_mismatch"}` increment.
- [ ] New doc `backend/records/SCHEMA_MIGRATIONS.md` (or section in `backend/records/README.md`) documents the additive-only versioning policy and the procedure to bump `schema_version`.
- [ ] Test in `backend/tests/records/test_service.py` asserts the version is stamped; test in `backend/tests/agent/test_handle_records_ingested.py` asserts version-mismatch rows are skipped with a counter increment.

### Verification
- `pytest backend/tests/records backend/tests/agent -q -k schema_version` green.
- Coverage ≥ 85% on records changes.
- Manual: bump `schema_version: 1.1` on one feed in `medicare_fraud_cms_desynpuf.yaml`; verify new rows insert with `1.1` while old `1.0` rows are skipped at Flow-1 time and the counter increments.

### Code touch points
- `backend/config/schema.py` (modify — `schema_version` on `RecordFeedConfig`)
- `backend/database/migrations/versions/0005_record_schema_version.py` (new)
- `backend/records/models.py` (modify — `feed_schema_version` field)
- `backend/records/service.py` (modify — stamp version)
- `backend/records/adapters/postgres.py` (modify — column in SQL + row mapping)
- `backend/records/adapters/in_memory.py` (modify — preserve version)
- `backend/records/mappers/feed_mapper.py` (modify — version-mismatch handling)
- `backend/records/README.md` (modify — versioning policy + procedure)
- `backend/tests/records/test_service.py` (modify — version-stamp test)
- `backend/tests/agent/test_handle_records_ingested.py` (modify — mismatch test)

---

## Story records.09: Add tenant scoping to records persistence and cascade-delete

**ID:** records.09
**Status:** planned
**Prerequisites:** [_multitenancy.03, _multitenancy.05, _multitenancy.10]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator,
**I need** every records read, write, and delete to be scoped by `tenant_id` end-to-end (request → service → adapter → SQL),
**so that** cross-tenant data leakage through the records API or via a KB-id collision is impossible by construction.

### Current State
- `RawRecord` (`backend/records/models.py:30-41`) has no `tenant_id` field — all records are keyed on `knowledge_base_id` alone.
- `_INSERT_SQL` / `_SELECT_SQL` / `_DELETE_BY_KB_SQL` (`backend/records/adapters/postgres.py:20-39, 87`) filter only on `knowledge_base_id`.
- `load_batch` and `delete_by_kb` (`backend/records/adapters/postgres.py:75-97`) accept no tenant parameter.
- `upload_record_file` / `push_records` (`backend/api/routers/records.py:42-144`) do not extract a tenant claim from the request.
- The persistence baseline (`backend/database/migrations/versions/0001_persistence_baseline.py:30-48`) has no `tenant_id` column on `raw_records` — `_multitenancy.05` adds it platform-wide.

### Acceptance Criteria
- [ ] `RawRecord.tenant_id: str` field added in `backend/records/models.py`.
- [ ] All three `_*_SQL` constants in `backend/records/adapters/postgres.py` filter on `(tenant_id, knowledge_base_id, ...)`; `load_batch` and `delete_by_kb` take a `tenant_id` kwarg; protocol methods updated.
- [ ] `InMemoryRawRecordStore` keys updated from `(kb, type, id)` to `(tenant, kb, type, id)`.
- [ ] `RecordsService.register_records` accepts the resolved tenant (via service-state or new method param) and stamps `tenant_id` on every persisted `RawRecord`.
- [ ] Records router endpoints (`backend/api/routers/records.py`) use the tenant-resolution dependency from `_multitenancy.03` and pass `tenant_id` through.
- [ ] `handle_records_ingested` (`backend/agent/coordinator.py:1597`) propagates tenant from the event envelope into all downstream calls (graph, observation writer, vector store).
- [ ] New test `backend/tests/records/test_tenant_isolation.py` asserts that records ingested under tenant A are not loadable / deletable as tenant B, even with a colliding `knowledge_base_id`.

### Verification
- `pytest backend/tests/records -q -k tenant` green.
- `pytest backend/tests/api/test_records_router.py -q` green with tenant-claim fixtures.
- Coverage ≥ 85% on `records/service.py`, `records/adapters/postgres.py`, `records/adapters/in_memory.py`.

### Code touch points
- `backend/records/models.py` (modify — `tenant_id`)
- `backend/records/adapters/protocols.py` (modify — tenant on every method)
- `backend/records/adapters/postgres.py` (modify — SQL + signatures)
- `backend/records/adapters/in_memory.py` (modify — keying + signatures)
- `backend/records/service.py` (modify — stamp tenant)
- `backend/api/routers/records.py` (modify — tenant dep + propagation)
- `backend/agent/coordinator.py` (modify — `handle_records_ingested` tenant propagation)
- `backend/records/README.md` (modify — tenant scoping section)
- `backend/tests/records/test_tenant_isolation.py` (new)
- `backend/tests/api/test_records_router.py` (modify — tenant claim assertions)

---

## Story records.10: Add rate limiting and submission-size policy to records API

**ID:** records.10
**Status:** planned
**Prerequisites:** [_security.10, api.10]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator,
**I need** per-tenant / per-IP token-bucket rate limiting and a configurable `max_rows_per_submission` cap on both records endpoints,
**so that** a misbehaving analyst client or a compromised credential cannot DoS the ingest path or starve other tenants of worker throughput.

### Current State
- `POST /records/{kb}/files` and `POST /records/{kb}/push` (`backend/api/routers/records.py:42, 110`) enforce only RBAC role (`analyst`) and the MB cap from `ValidationConfig.max_file_size_mb` (`backend/api/routers/records.py:77-82`).
- No rate-limit middleware exists anywhere in the API (`_security.10` adds the platform middleware as the prereq).
- No row-count ceiling exists on api-push — a single request can submit an arbitrarily long JSON array.
- `RecordFeedConfig` (`backend/config/schema.py:331-349`) has no `max_rows_per_submission` field.

### Acceptance Criteria
- [ ] `RecordFeedConfig.max_rows_per_submission: int | None = None` added in `backend/config/schema.py`.
- [ ] `RecordsService.register_records` raises a new `RecordSubmissionTooLargeError` (in `backend/records/exceptions.py`) when row count exceeds the per-feed cap; router maps to `HTTP 413` with detail naming the cap and the actual count.
- [ ] Records router decorated with the rate-limit dependency from `_security.10` using a records-specific limit (e.g. `records-upload: 60/minute per tenant`); limit configurable via `RecordsConfig.rate_limit_per_minute_per_tenant`.
- [ ] `429 Too Many Requests` returned with `Retry-After` header on bucket exhaustion.
- [ ] `records_rows_rejected_total{reason="rate_limited"}` and `..{reason="submission_too_large"}` increments wired (records.06 metrics).
- [ ] Test in `backend/tests/api/test_records_router.py` asserts 413 on oversized row count and 429 on rapid-fire submits.
- [ ] `backend/records/README.md` documents both knobs.

### Verification
- `pytest backend/tests/api/test_records_router.py backend/tests/records -q -k "rate or too_large"` green.
- Coverage ≥ 85% on changed paths.
- Manual: 61 sequential `/records/kb1/push` calls with the limit at 60/min → the 61st returns 429 with `Retry-After`.

### Code touch points
- `backend/config/schema.py` (modify — `max_rows_per_submission`, `rate_limit_per_minute_per_tenant`)
- `backend/records/exceptions.py` (modify — `RecordSubmissionTooLargeError`)
- `backend/records/service.py` (modify — row-count enforcement)
- `backend/api/routers/records.py` (modify — rate-limit dep + 413/429 mappings)
- `backend/records/metrics.py` (modify — new rejection-reason labels)
- `backend/records/README.md` (modify — rate limit + submission size docs)
- `backend/tests/api/test_records_router.py` (modify — rate-limit + oversize tests)

---

## Story records.11: Add fixtures and golden tests for missing CMS feeds

**ID:** records.11
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** records-pipeline maintainer,
**I need** sample CSV fixtures and golden ingest tests for `beneficiary_2009`, `beneficiary_2010`, and `nppes_providers`,
**so that** every declared CMS feed in `medicare_fraud_cms_desynpuf.yaml` has reproducible end-to-end coverage and a schema or mapper regression breaks a test rather than a customer demo.

### Current State
- `backend/tests/records/fixtures/cms/` ships only `beneficiary_2008_sample.csv`, `carrier_claims_sample.csv`, `inpatient_claims_sample.csv`, `outpatient_claims_sample.csv`, `pde_sample.csv`.
- No fixture for `beneficiary_2009`, `beneficiary_2010`, or `nppes_providers`.
- Domain config declares all three (`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml:119-141, 141-167, 384-409`).
- `tools/sample_data/build_tennessee_subset.py` is the precedent for shipping subset data — NPPES is materialized there.

### Acceptance Criteria
- [ ] New fixtures `backend/tests/records/fixtures/cms/beneficiary_2009_sample.csv`, `beneficiary_2010_sample.csv`, `nppes_providers_sample.csv` each containing ≥ 10 deterministic rows with realistic CMS-shaped values.
- [ ] New test cases (in `backend/tests/records/test_cms_ingestion.py` or per-feed sibling files) per fixture asserting: (a) `validate_rows` accepts every row, (b) `RecordsService.register_records` persists the expected row count, (c) `handle_records_ingested` (Flow 1) produces the expected `(entities_count, relationships_count, observations_count)` tuple.
- [ ] Fixtures are deterministic (no random seeds) — re-running tests yields identical counts.
- [ ] `backend/records/README.md` "CMS feed inventory" section updated to confirm every declared feed has fixture coverage.
- [ ] Coverage of `backend/records/mappers/feed_mapper.py` rises (delta visible in coverage report).

### Verification
- `pytest backend/tests/records -q -k "beneficiary_2009 or beneficiary_2010 or nppes"` green.
- Coverage ≥ 85% on `backend/records/mappers/feed_mapper.py`.
- Manual: `ls backend/tests/records/fixtures/cms/` shows all 8 fixture CSVs.

### Code touch points
- `backend/tests/records/fixtures/cms/beneficiary_2009_sample.csv` (new)
- `backend/tests/records/fixtures/cms/beneficiary_2010_sample.csv` (new)
- `backend/tests/records/fixtures/cms/nppes_providers_sample.csv` (new)
- `backend/tests/records/test_cms_ingestion.py` (modify — new golden cases)
- `backend/records/README.md` (modify — fixture inventory)

---

## Story records.12: Formalize and document the records → no-GraphUpdatedEvent design

**ID:** records.12
**Status:** planned
**Prerequisites:** [agent.10]
**Unblocks:** []
**Estimated size:** S

**As a** worker operator,
**I need** the deliberate decision that `handle_records_ingested` does NOT publish `GraphUpdatedEvent` to be either documented prominently (with rationale) or replaced by an opt-in `RecordsGraphUpdatedEvent` (gated by config),
**so that** operators are not surprised when records-only KBs never trigger Flow 2 (graph metrics) or Flow 3 (risk recompute).

### Current State
- `handle_records_ingested` (`backend/agent/coordinator.py`, search `def handle_records_ingested` — line anchors drift; previously cited :1597-1690, now ~:2960+) calls `graph_service.upsert_records_graph` and intentionally does NOT publish `GraphUpdatedEvent`.
- Architecture §6.3 describes Flow 1 as ending at graph upsert + observations write — Flows 2/3 are documents-only triggered.
- `backend/records/README.md` describes Flow 1 but does not call out the no-`GraphUpdatedEvent` quirk.
- **Re-scoped by analytics.34 (done 2026-07-24):** Flow B (GNN/risk/explainability/alerts) now fires natively off records ingest via a direct in-process call gated by `RecordsConfig.analytics_trigger` — WITHOUT publishing `GraphUpdatedEvent` (publishing would force Flow A's storage-key artifacts + redundant re-embedding; that decision is recorded in analytics.34's AC 1). What remains for THIS story is the Flow 2/3 question only (graph metrics recompute, risk recompute off a published event) and the operator-facing documentation of the no-publish design. If the `emit_graph_updated_event` toggle is still wanted, its event must carry storage-key artifacts or Flow A must learn to skip artifact-less documents.

### Acceptance Criteria
- [ ] `backend/records/README.md` gets a new `## Flow 1: known quirks` section explicitly documenting that records-driven graph upserts do NOT publish `GraphUpdatedEvent`, with rationale (records are typically high-volume; per-batch metric/risk recompute would thrash) and a pointer to the opt-in toggle.
- [ ] `RecordsConfig.emit_graph_updated_event: bool = False` added in `backend/config/schema.py` to make the behavior configurable.
- [ ] When `emit_graph_updated_event=True`, `handle_records_ingested` publishes a `GraphUpdatedEvent` (or new `RecordsGraphUpdatedEvent` derived from it) with `source_kind="records"`; Flow 2/3 handlers honor it.
- [ ] `docs/architecture.md` §6.3 updated with a one-paragraph callout for the toggle.
- [ ] Integration test in `backend/tests/agent/test_handle_records_ingested.py` asserts no `GraphUpdatedEvent` is published by default and exactly one is published when the toggle is on.
- [ ] Inline comment at the omission site in `backend/agent/coordinator.py` updated to reference the toggle.

### Verification
- `pytest backend/tests/agent -q -k records_graph_updated` green.
- Coverage ≥ 85% on `backend/agent/coordinator.py:handle_records_ingested`.
- Manual: enable `records.emit_graph_updated_event: true` in `medicare_fraud_dev.yaml`, ingest a feed, observe `graph.updated` stream receives an entry.

### Code touch points
- `backend/config/schema.py` (modify — `emit_graph_updated_event` on `RecordsConfig`)
- `backend/agent/coordinator.py` (modify — conditional publish + comment refresh)
- `backend/records/README.md` (modify — Flow 1 quirks section)
- `docs/architecture.md` (modify — §6.3 toggle callout)
- `backend/tests/agent/test_handle_records_ingested.py` (modify — toggle test)

---

## Story records.13: Add admin endpoint to list and inspect declared feeds

**ID:** records.13
**Status:** planned
**Prerequisites:** [api.10]
**Unblocks:** []
**Estimated size:** M

**As an** analyst building an upload form,
**I need** a read-only `GET /records/feeds` endpoint returning the configured feed inventory (name, record_type, source, accepted_formats, required schema fields, observation metrics),
**so that** the workbench can render a feed picker and field-help inline instead of forcing analysts to read the YAML.

### Current State
- There is no `GET /records/feeds` (or any GET) endpoint in `backend/api/routers/records.py` — the router only exposes the two POST endpoints (`backend/api/routers/records.py:42, 110`).
- The frontend (`chili_app/src/pages/`) has no records-feed picker that consumes feed metadata from the API.
- The only way to discover legal `feed` form values is to read `medicare_fraud_cms_desynpuf.yaml` directly.
- `RecordsConfig.feeds` (`backend/config/schema.py:352-355`) carries all the metadata needed.

### Acceptance Criteria
- [ ] New `GET /records/feeds` endpoint added in `backend/api/routers/records.py`, RBAC `analyst`, returning a `RecordFeedListResponse` shaped per the api.10 pagination contract.
- [ ] New Pydantic response models `RecordFeedSummary` (per-feed: name, record_type, source, accepted_formats, id_field, id_template, required_field_names, observation_metric_names) and `RecordFeedListResponse` in `backend/api/contracts.py` (or `backend/api/routers/records.py` if api.10's contracts split hasn't landed).
- [ ] Endpoint returns 200 with all configured feeds; cacheable via standard ETag (per api.10 pagination behavior if applicable).
- [ ] Test in `backend/tests/api/test_records_router.py` asserts shape, presence of every declared feed in the medicare config, and the right 401/403 behavior.
- [ ] `backend/records/README.md` API endpoints table updated to include the new GET route.
- [ ] Optional follow-up (out of scope): frontend feed picker is a separate `frontend.*` story; only the API surface lands here.

### Verification
- `pytest backend/tests/api/test_records_router.py -q -k list_feeds` green.
- Coverage ≥ 85% on records router additions.
- Manual: `curl -H "Authorization: Bearer <analyst-token>" http://localhost:8000/records/feeds | jq '.items | length'` returns 9 (or current count) for the medicare config.

### Code touch points
- `backend/api/routers/records.py` (modify — new GET endpoint + response models)
- `backend/api/contracts.py` (modify — `RecordFeedSummary`, `RecordFeedListResponse` once api.10 contract split lands)
- `backend/records/README.md` (modify — API endpoints table)
- `backend/tests/api/test_records_router.py` (modify — list-feeds test)

---

## Story records.14: Object-store pull origin (S3 / MinIO / blob / local FS) by reference

**ID:** records.14
**Status:** planned
**Prerequisites:** [storage.01, records.04]
**Unblocks:** [records.15, records.16, records.17]
**Estimated size:** L

**As a** data engineer staging multi-GB feed files,
**I need** feeds to accept an object reference (store key or `s3://` URI) that the worker pulls and streams through the records pipeline,
**so that** bulk data never traverses an HTTP upload body and size limits stop applying to it.

### Current State
- `IngestionSourceConfig.type` is `Literal["file_upload", "api_push"]` (`backend/config/schema.py:64`) — no pull origin exists.
- The ObjectStore protocol has no streaming read; storage.01 adds `get_stream` (`docs/backlog/storage.md`).
- `read_upload_file_with_limit` (`backend/api/routers/records.py:45`) is the only inbound byte path for records files.
- Design: `docs/superpowers/specs/2026-07-26-records-origin-sources-design.md` §3.

### Acceptance Criteria
- [ ] `RecordOriginSource` protocol in `backend/records/adapters/protocols.py`: `iter_rows(ref: str) -> Iterator[dict[str, object]]` streaming rows; in-memory adapter for tests (REQ-INT-003).
- [ ] `ObjectStoreOriginSource` adapter streams via `ObjectStore.get_stream` (storage.01) and reuses the records.04 streaming CSV/JSONL parsers; accepts bare keys and `s3://bucket/key` URIs.
- [ ] `IngestionSourceConfig.type` gains `"object_store"`; feed config validates that object-store feeds name an accepted format.
- [ ] `POST /records/{kb}/feeds/{feed}/pulls` (RBAC `analyst`) registers a pull `{ref: str}` and returns a 202 receipt with `correlation_id`; the worker executes the pull via a new `records.pull.requested` event handled in `agent/coordinator.py`, ending in the existing validate → dedup → persist → `records.ingested` path.
- [ ] Pull failures publish the existing ingest-failure surface (no new alert path); receipts are queryable through the existing run timeline.
- [ ] Integration test against MinIO (`@pytest.mark.integration`) pulls a staged CSV object end-to-end.
- [ ] `backend/records/README.md` documents the origin model.

### Verification
- `pytest backend/tests/records/ backend/tests/api/test_records_router.py -q` green; coverage ≥ 85% on new modules.
- `pytest -m integration -k object_store_origin` green with the dev stack up.
- Manual: register a pull for a staged `sample_data` object; `records.ingested` appears with the object's row count.

### Code touch points
- `backend/records/adapters/protocols.py` (modify — `RecordOriginSource`)
- `backend/records/adapters/sources/object_store_source.py` (create)
- `backend/config/schema.py` (modify — source type literal)
- `backend/api/routers/records.py` (modify — pull registration endpoint)
- `backend/agent/coordinator.py` (modify — pull execution handler)
- `backend/events/types.py` (modify — `RecordsPullRequestedEvent`)
- `backend/tests/records/test_object_store_source.py` (create)

---

## Story records.15: HTTP API pull origin

**ID:** records.15
**Status:** planned
**Prerequisites:** [records.14]
**Unblocks:** []
**Estimated size:** M

**As a** data engineer whose upstream publishes export URLs,
**I need** a feed origin that fetches a remote HTTP(S) export and streams it through the records pipeline,
**so that** scheduled exports ingest without an intermediate manual download/upload.

### Current State
- No outbound-fetch origin exists; records.14 establishes the pull surface and `RecordOriginSource` protocol this story implements against.
- Auth-by-env-var precedent: `GraphDbConfig.auth_env_var` (`backend/config/schema.py:110`).

### Acceptance Criteria
- [ ] `HttpPullOriginSource` adapter implements `RecordOriginSource` with chunked `httpx` streaming; `IngestionSourceConfig.type` gains `"http_pull"` with `endpoint` required and optional `auth_env_var` (bearer header).
- [ ] Response size guard: abort with a recorded failure past a configurable `max_pull_bytes` (default 10 GiB); malformed/absent Content-Length handled (precedent: `tests/ingestion/test_service.py` remote content-length cases).
- [ ] Paginated-GET support via an optional `next_link_field` config key (JSON responses only); CSV/JSONL exports fetch single-shot streams.
- [ ] Unit tests with a stub transport cover success, auth header, oversize abort, and pagination.

### Verification
- `pytest backend/tests/records/test_http_pull_source.py -q` green; coverage ≥ 85%.
- Manual: point a feed at a local `python -m http.server` export and confirm `records.ingested`.

### Code touch points
- `backend/records/adapters/sources/http_pull_source.py` (create)
- `backend/config/schema.py` (modify — source type literal + fields)
- `backend/tests/records/test_http_pull_source.py` (create)

---

## Story records.16: Stream origin (Redis Streams first)

**ID:** records.16
**Status:** planned
**Prerequisites:** [records.14]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator with continuously produced records,
**I need** a feed origin that consumes rows from an event stream with its own consumer group,
**so that** near-real-time sources feed the same validate/dedup/persist pipeline as files.

### Current State
- Redis Streams is the existing event transport (`backend/events/adapters/`); no records-facing stream consumption exists.
- Kafka has no adapter — per the architecture rules it must not enter `DomainConfig` literals until one exists (roadmap).

### Acceptance Criteria
- [ ] `StreamOriginSource` consumes a configured Redis stream key with consumer group `records:<feed>`, batching rows (configurable batch size / max wait) into pipeline submissions.
- [ ] `IngestionSourceConfig.type` gains `"stream"` with `stream_key` required; validation rejects it when the event backend is in-memory.
- [ ] At-least-once semantics documented; per-row dedup relies on the existing records content-hash idempotency (records.02).
- [ ] Worker lifecycle: consumption starts/stops with the coordinator; unacked entries are reclaimed on restart (respecting the CHILI_EVENT_RECLAIM_MIN_IDLE_MS trap noted in sprint 2026-28 ops lessons).
- [ ] Integration test (`@pytest.mark.integration`) produces rows to a test stream and asserts persisted records.

### Verification
- `pytest backend/tests/records/test_stream_source.py -q` green; `pytest -m integration -k stream_origin` green with the stack up.
- Manual: `redis-cli XADD` a row envelope; observe `records.ingested`.

### Code touch points
- `backend/records/adapters/sources/stream_source.py` (create)
- `backend/config/schema.py` (modify — source type literal + fields)
- `backend/agent/coordinator.py` (modify — consumer lifecycle)
- `backend/tests/records/test_stream_source.py` (create)

---

## Story records.17: Presigned-URL direct upload path for large interactive files

**ID:** records.17
**Status:** planned
**Prerequisites:** [storage.01, records.14]
**Unblocks:** []
**Estimated size:** M

**As an** analyst uploading a very large file from the browser,
**I need** the app to upload directly to object storage via a presigned URL and then register the object by reference,
**so that** interactive uploads scale past API-buffered limits without traversing the gateway.

### Current State
- Browser uploads go through `apiUploadWithProgress` (`chili_app/src/lib/apiClient.ts`) as multipart bodies to the API.
- storage.01 charters `generate_presigned_url`; records.14 charters register-by-reference — this story is the frontend/API glue.

### Acceptance Criteria
- [ ] `POST /records/{kb}/feeds/{feed}/uploads:presign` (RBAC `analyst`) returns `{url, key, expires_in}` for S3/MinIO backends; 409 with a clear detail on backends without presign support (local FS/in-memory).
- [ ] Frontend upload flow: files past a configurable threshold (default 256 MB) use presign → PUT direct → register pull by `key` via the records.14 endpoint; smaller files keep the existing multipart path with its progress bar.
- [ ] Progress + Retry UX parity with the existing `apiUploadWithProgress` behavior.
- [ ] Playwright e2e against the full stack (MinIO) exercises the presigned path with a >threshold synthetic CSV.

### Verification
- `npm run test:run` green; `make test-e2e` includes the presigned-path spec, green.
- Manual: upload a 300 MB synthetic CSV in the browser; observe direct-to-MinIO traffic and a registered pull.

### Code touch points
- `backend/api/routers/records.py` (modify — presign endpoint)
- `chili_app/src/lib/apiClient.ts` (modify — threshold branch)
- `chili_app/src/api/records.ts` (modify — presign + register calls)
- `chili_app/e2e/` (create — presigned upload spec)
