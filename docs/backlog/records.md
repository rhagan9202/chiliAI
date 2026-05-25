# records backlog

> **Scope:** Structured/tabular ingestion (CSV/JSONL/api-push → raw_records → Flow 1 fan-out), feed registry, validation, idempotency, observability, streaming.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story records.01: Declare and enforce per-feed allowed file formats

**ID:** records.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** domain operator,
**I need** each `RecordFeedConfig` to declare which file formats (CSV / JSONL) it accepts and the upload router to reject mismatches with 415,
**so that** a misnamed or wrong-format upload is rejected at the boundary instead of dying with a confusing parser error mid-batch.

### Current State
- `RecordFeedConfig` (`backend/config/schema.py:331-349`) has no `formats` / `accepted_formats` field — feeds are format-agnostic in config.
- The router branches on filename extension only (`backend/api/routers/records.py:30-39 _select_file_source`) — a JSONL upload to a feed designed for CSV-only export semantics passes router validation, then `JsonlFileSource.read_rows` (`backend/records/adapters/sources/file_source.py:54-77`) parses it without any feed-level guard.
- `medicare_fraud_cms_desynpuf.yaml` (`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml:92-409`) declares every feed as `source: file_upload` with no format hint.
- No 415 mapping exists for "feed does not accept this format" — only for "unsupported extension entirely."

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
**Status:** planned
**Prerequisites:** [database.01]
**Unblocks:** []
**Estimated size:** M

**As a** worker operator,
**I need** the records service to detect a byte-identical (or row-set-identical) re-upload of the same feed and short-circuit before publishing `RecordsIngestedEvent`,
**so that** an operator who clicks "upload" twice does not re-fire Flow 1 fan-out, re-run graph upserts, and emit a duplicate workflow record.

### Current State
- `RecordsService.register_records` always mints a fresh `correlation_id` (`backend/records/service.py:36`).
- Row-level idempotency works (`backend/records/adapters/postgres.py:20-26` — `ON CONFLICT (knowledge_base_id, record_type, record_id) DO NOTHING`) so re-uploaded rows insert zero rows.
- But `accepted_count` is included in `RecordsIngestedEvent` (`backend/records/service.py:71-79`) and the event is published unconditionally, so Flow 1 fan-out (`backend/agent/coordinator.py:1597-1690 handle_records_ingested`) re-runs against the existing rows. The handler is idempotent but does pay for the full map_batch + graph upsert + embed every time.
- `RawRecord` already carries `content_hash` (`backend/records/models.py:30-41`) but there is no submission-level digest aggregating an entire batch.

### Acceptance Criteria
- [ ] New `record_submissions` table (or extension of `raw_records` indexing) capturing `(knowledge_base_id, feed_name, submission_hash)` with unique constraint, created via a new Alembic migration under `backend/database/migrations/versions/`.
- [ ] `RecordsService.register_records` computes a deterministic submission hash over the sorted list of per-row `content_hash` values BEFORE persisting; on a duplicate hit it returns a `RecordIngestReceipt` with `accepted_count=0`, `duplicate=True` and DOES NOT publish `RecordsIngestedEvent`.
- [ ] `RecordIngestReceipt` (`backend/records/service_models.py`) gets a new `duplicate: bool = False` field.
- [ ] HTTP response on a duplicate is `200 OK` (not 202) so the SPA can disambiguate "accepted for processing" vs "already ingested" without parsing the body.
- [ ] Unit test in `backend/tests/records/test_service.py`: re-submitting the same `RecordSubmission` twice yields one event and one `RecordsIngestedEvent` on the bus.
- [ ] `backend/records/README.md` "Idempotency" section documents the submission-level dedup and links architecture §6.3.

### Verification
- `pytest backend/tests/records -q` green with new dedup tests.
- Coverage ≥ 85% on `backend/records/service.py` and the new migration.
- Manual: upload `beneficiary_2008_sample.csv` twice; check Redis stream `records.ingested` has exactly one entry and `duplicate=true` on the second receipt.

### Code touch points
- `backend/database/migrations/versions/0003_record_submissions.py` (new — submission-hash index/table)
- `backend/records/service.py` (modify — compute submission hash, dedup short-circuit)
- `backend/records/service_models.py` (modify — `duplicate` field on receipt)
- `backend/records/adapters/protocols.py` (modify — `mark_submission` / `has_submission` methods)
- `backend/records/adapters/in_memory.py` (modify — set-backed dedup)
- `backend/records/adapters/postgres.py` (modify — submission insert + lookup)
- `backend/api/routers/records.py` (modify — 200 vs 202 status flip on `duplicate`)
- `backend/records/README.md` (modify — idempotency section)
- `backend/tests/records/test_service.py` (modify — dedup test)
- `backend/tests/records/test_postgres_adapter.py` (modify — adapter dedup test)

---

## Story records.03: Resolve `pde` feed status (drop or land Plan-C fan-out)

**ID:** records.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** domain owner,
**I need** the `pde` (Part D events) feed in `medicare_fraud_cms_desynpuf.yaml` to either be removed or fully wired (entity mappings + relationships + fixture-backed golden test),
**so that** the declared 9th feed is not a half-wired surface that ingests `raw_records` but never produces graph entities or observations.

### Current State
- `medicare_fraud_cms_desynpuf.yaml:349-383` declares `name: pde`, `record_type: pde_record`, `id_field: PDE_ID`, with a `record_schema`. The Tennessee subset materializer (`tools/sample_data/build_tennessee_subset.py`) references PDE rows.
- The fixture `backend/tests/records/fixtures/cms/pde_sample.csv` exists but no `entities`, `relationships`, or `observations` mappings are declared for the feed in the YAML — only the schema.
- No `pde_record` entity definition exists in the top-level `entities:` block (`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml:7-90`) — `map_batch` would yield zero entities.
- Architecture §5.2 / §6.3 expects feed → entities → graph; a declared-but-unmapped feed is a footgun.

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
**Prerequisites:** [api.10]
**Unblocks:** []
**Estimated size:** L

**As an** analyst,
**I need** CSV and JSONL uploads to stream row-by-row through the parser instead of being fully `await file.read()`-ed into memory,
**so that** CMS-scale files (1–10 GB) can be ingested without OOMing the API container and without raising the 413 cap to a memory-dangerous value.

### Current State
- `upload_record_file` calls `content = await file.read()` (`backend/api/routers/records.py:75`) loading the entire payload before parsing.
- `CsvFileSource.read_rows(raw: bytes)` (`backend/records/adapters/sources/file_source.py:23-48`) and `JsonlFileSource.read_rows(raw: bytes)` (`:54-77`) both take `bytes` and return a fully-materialized `list[dict[str, object]]`.
- The 413 ceiling is governed by `ValidationConfig.max_file_size_mb` (default 100 MB; `backend/api/routers/records.py:77-82`) — raising it linearly raises API memory pressure.
- `RecordsService.register_records` takes a `list[dict[str, object]]` (`backend/records/service.py:30-35`) so the whole batch is in memory anyway — streaming only the parser stage is a no-op without a service refactor.

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
**Unblocks:** []
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
**Unblocks:** []
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
- `handle_records_ingested` (`backend/agent/coordinator.py:1597-1690`) calls `graph_service.upsert_records_graph` and intentionally does NOT publish `GraphUpdatedEvent` — the inline comment at `backend/agent/coordinator.py:1677-1678` says "we intentionally do not publish VectorsIndexedEvent here" but does not explain GraphUpdatedEvent omission.
- Architecture §6.3 (`docs/architecture.md:~693`) describes Flow 1 as ending at graph upsert + observations write — Flows 2/3 are documents-only triggered.
- `backend/records/README.md:38-51` describes Flow 1 but does not call out the no-`GraphUpdatedEvent` quirk.
- No story or doc records this as an intentional design choice vs an oversight; this surprises operators reading the events module.

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
