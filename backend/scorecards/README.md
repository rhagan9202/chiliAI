# scorecards

Config-driven **scorecard runs**. A domain pack declares scorecard templates
(`DomainConfig.scorecards.templates`, typed by `config.schema.ScorecardTemplateConfig`);
this module evaluates a template deterministically against a knowledge base's
ingested feed records, grades every metric and section
(`pass` / `warn` / `fail` / `incomplete`), renders JSON and Markdown exports,
and persists the result as a durable, KB-scoped `ScorecardRun`.

## Layout

| File | Responsibility |
|------|----------------|
| `evaluation.py` | Pure evaluator: `evaluate_template(template, ScorecardEvalState)` over `SourceRecord`s. Selects metric inputs, evaluates formulas, applies weighted means, freshness/staleness checks, health classification, and citations. No I/O. |
| `models.py` | `ScorecardRun`, `ScorecardEvaluationResult`, `ScorecardSectionResult`, `ScorecardMetricResult`, `ScorecardCitation`, and the `ScorecardHealth` / `ScorecardRunStatus` / `ScorecardExportFormat` / `ScorecardCompleteness` literals. |
| `service_models.py` | API-boundary requests/responses (`ScorecardGenerateRequest`, `ScorecardRunListRequest`, `ScorecardRunListResponse`, `ScorecardTemplateListResponse`, `ScorecardExportResponse`, ...). |
| `service.py` | `ScorecardService` (template lookup, record selection, evaluation, export rendering, persistence), `create_scorecard_service`, and the `ScorecardSourceRecordLoader` read-boundary protocol. |
| `protocols.py` / `adapters/protocols.py` | `ScorecardRunRepository` — `upsert / get / list / delete_by_kb`. |
| `adapters/in_memory.py` | `InMemoryScorecardRunRepository` for tests/dev. |
| `adapters/postgres.py` | `PostgresScorecardRunRepository` over `database.ConnectionProvider`; `upsert` uses `ON CONFLICT` on the natural key. |
| `exceptions.py` | `ScorecardEvaluationError` base plus `ScorecardFormulaError`, `ScorecardPersistenceError`, `ScorecardRunNotFoundError`, `ScorecardTemplateNotFoundError`, `ScorecardExportNotFoundError`. |

## Contracts and invariants

- **No cross-module imports for source data.** `ScorecardService` reads records
  only through `ScorecardSourceRecordLoader.load_source_records(kb_id)`. The
  gateway implements it (`RecordFeedSourceLoader` in `api/dependencies.py`),
  bridging the `records` raw-record store and mapping each row's
  `record_type` back to the feed name metric inputs reference. With no loader
  configured, `generate` evaluates an empty record set.
- **Record selection** (`ScorecardService._select_records`): `scope_type ==
  "installation"` keeps only records whose `installation_id` equals
  `scope_id`; broader scopes evaluate the whole KB record set. Records with an
  `observed_at` must fall inside `[period_start, period_end]`; undated records
  are kept and left to the evaluator's freshness check.
- **Idempotent run ids.** `source_snapshot_hash` is a SHA-256 over the request
  (KB, template, scope, period), sorted per-record content digests, and a
  digest of the template definition. The run id is
  `scorecard-run-<first 24 hex chars>`. Identical request + data + template
  returns the existing run; changed data or a retuned threshold yields a new run.
- Exports (`json`, `markdown`) are rendered at generation time and stored on
  the run in `export_payloads`; `export_run` only reads them back.
- `ScorecardRunStatus` declares `generated`, `failed`, `superseded`, but the
  service currently only writes `generated`.

## How it is reached

Routed by `api/routers/scorecards.py` (prefix `/scorecards`):

| Route | Role |
|-------|------|
| `GET /scorecards/templates` | viewer |
| `POST /scorecards/runs` | analyst — generate (or return the existing idempotent) run |
| `GET /scorecards/runs` | viewer — list, filter by template/status |
| `GET /scorecards/runs/{run_id}` | viewer |
| `GET /scorecards/runs/{run_id}/export` | viewer — stored JSON or Markdown export |

`api/routers/housing.py` reuses the same `RecordFeedSourceLoader` for its
housing read models.
The worker does not evaluate scorecards; it only builds a repository
(`build_scorecard_run_repository` in `agent/coordinator.py`) so KB teardown
(`knowledgebases/cleanup.py`) can call `delete_by_kb`.

## Persistence

Table `scorecard_runs`, created by
`database/migrations/versions/0008_scorecards.py`: `PRIMARY KEY
(knowledge_base_id, run_id)`, a `UNIQUE` natural key over
`(knowledge_base_id, template_id, scope_type, scope_id, period_start,
period_end, source_snapshot_hash)`, jsonb `sections` / `export_payloads`, and
index `ix_scorecard_runs_kb_template`. `get_scorecard_run_repository`
(`api/dependencies.py`) returns the in-memory adapter when no connection
provider is configured, otherwise the Postgres adapter.

## Tests

`tests/scorecards/` — `test_evaluation.py` (pure evaluator),
`test_service.py`, `test_in_memory_store.py`, and `test_postgres_store.py`
(`@pytest.mark.integration`).

See also: [config](../config/README.md) (template schema),
[records](../records/README.md) (source feeds),
[architecture](../../docs/architecture.md).
