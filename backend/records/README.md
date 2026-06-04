# records — Structured / Tabular Ingestion

The structured-ingestion counterpart to `ingestion/` (documents). `records/`
accepts tabular feeds (CSV / JSONL file uploads, JSON api-push), validates
rows against a config-declared feed schema, lands canonical rows in the
`raw_records` Postgres table, and publishes a `RecordsIngestedEvent`. The
worker's Flow 1 handler then fans each batch out to the knowledge graph and
the `observations` table.

## Layout

- `models.py` — `RawRecord`, `RecordBatch`, `RejectedRow`, `content_hash_for`
  (per-row idempotency digest) and `submission_hash_for` (whole-submission
  digest over feed name + sorted per-row content hashes).
- `service_models.py` — `RecordSubmission`, `RecordIngestReceipt` (API
  boundary). The receipt carries `accepted_count`, `duplicate` /
  `duplicate_count` (submission-level dedup), and `rejected_count` / `rejected`
  (per-row format rejections).
- `validation.py` — `coerce_row` and two validators: `validate_rows_partition`
  splits a batch into coerced-valid rows and `RejectedRow`s **without raising**
  (used by the service so good rows still ingest); `validate_rows` retains the
  all-or-nothing raise for callers that need a hard failure. Both reuse
  `shared.types.validate_entity` via a synthetic `EntityDefinition`.
- `mappers/feed_mapper.py` — config-driven `map_batch` (rows → entities +
  relationships) and `map_observations` (rows → scored observations).
- `service.py` — `RecordsService.register_records()`: validate → persist →
  publish `RecordsIngestedEvent`.
- `protocols.py` — `RecordsServiceProtocol` (service boundary).
- `adapters/protocols.py` — `RawRecordStore` (now also `was_submitted` /
  `record_submission` for submission-level dedup), `RecordSourceProtocol`.
- `adapters/in_memory.py` — `InMemoryRawRecordStore` (local/test backend).
- `adapters/postgres.py` — `PostgresRawRecordStore` (`raw_records` plus the
  `record_submissions` dedup table, migration `0004_record_submissions`).
- `adapters/sources/file_source.py` — `CsvFileSource`, `JsonlFileSource`.
- `adapters/sources/api_push_source.py` — `ApiPushSource`.

`records/` communicates downstream only by publishing events — it never
imports `graph` or `analytics` internals.

## Feed configuration

Feeds are declared in `DomainConfig.records.feeds` — adding a domain's tabular
feeds requires config changes only, no code. Each `RecordFeedConfig` declares
a `record_schema`, `entities` (row → entity mappings), `relationships`, and
`observations`. See `config/defaults/medicare_fraud.yaml` for a worked example.

## Flow 1

```
records source (CSV/JSONL/api-push)
  → RecordsService.register_records()   # validate vs feed schema
  → RawRecordStore.persist()            # raw_records (canonical)
  → publish RecordsIngestedEvent
  → worker handle_records_ingested:
       1. map rows → entities/relationships → GraphService.upsert_records_graph()
       2. derive observations → observations table (PostgresObservationStore)
```

Every write is an idempotent upsert, so the worker's retry/DLQ wrapper can
re-run the handler safely.

## Idempotency, partial acceptance, and format gating (BL-015)

- **Submission-level dedup** — `register_records` computes a
  `submission_hash_for(feed_name, [content_hash...])` (order-independent). If
  the same hash was already registered for the KB (`RawRecordStore.was_submitted`),
  the call is a no-op: nothing is persisted or published and the receipt is
  returned with `duplicate=True`, `accepted_count=0`, `duplicate_count=<rows>`.
  The file/push endpoints return **HTTP 200** for a duplicate (vs. 202 for a
  fresh accept). Otherwise the hash is recorded via `record_submission` before
  persisting.
- **Per-row format rejection** — individual rows that fail coercion/schema
  validation no longer abort the whole batch. Valid rows ingest; rejected rows
  are reported in the receipt as `rejected_count` / `rejected` (`RejectedRow`
  with `index` + `reason`).
- **Format gate** — each `RecordFeedConfig` declares
  `accepted_formats` (default `["csv", "jsonl"]`). The file-upload endpoint
  rejects an upload whose format is not in the resolved feed's
  `accepted_formats` with **HTTP 415**.

## API endpoints

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/records/{knowledge_base_id}/files` | analyst | Ingest a CSV or JSONL file upload into the named feed (415 if the feed does not accept the format; 200 on duplicate submission, else 202) |
| `POST` | `/records/{knowledge_base_id}/push` | analyst | Ingest a JSON array of record rows into the named feed (200 on duplicate submission, else 202) |

## NPPES and DE-SynPUF Feeds (medicare_fraud domain)

`config/defaults/medicare_fraud.yaml` (and the dev variant) declares two built-in feed definitions that exercise the records pipeline end-to-end:

- **`nppes_providers`** — NPPES National Provider Identifier file. Each row maps to a `provider` entity with NPI, taxonomy, name, address, and state. Used by the Tennessee demo subset.
- **`de_synpuf_inpatient`** / **`de_synpuf_outpatient`** — CMS DE-SynPUF synthetic Medicare claims. Inpatient rows map to `claim → provider` and `claim → beneficiary` relationships; outpatient rows are analogous. Used by the Tennessee demo subset.

These feeds are config-only additions — no application code was changed. To add a new feed for a different domain, declare it in the domain YAML under `records.feeds` following the same pattern.

The Tennessee subset materializer at `tools/sample_data/build_tennessee_subset.py` filters the full NPPES CSV and DE-SynPUF JSONL down to Tennessee providers and their associated claims. Run `python -m tools.sample_data.build_tennessee_subset --help` to see options.

## KB-Scoped Delete

`RawRecordStore` exposes `delete_by_kb(kb_id)` which bulk-removes all `raw_records` rows belonging to the given knowledge base. This is the raw-records leg of the KB-delete cascade triggered by `DELETE /knowledgebases/{id}`. Both `InMemoryRawRecordStore` and `PostgresRawRecordStore` implement this method.

## Commands

```bash
pip install -e ".[dev,postgres]"
pytest tests/records -m "not integration"   # fast unit tests
pytest tests/records -m integration           # needs a migrated TimescaleDB
```
