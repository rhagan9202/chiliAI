# connectors

**Pull connectors** (SAFE-CMS-017): KB-scoped connector definitions that read
rows from an external source and land them through the same
`records` ingestion path as a manual upload. A sync run is driven page by page
by the worker through `connector.page.queued` events; rows that cannot be
ingested are kept as quarantine records for operators.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `ConnectorDefinitionCreate` / `ConnectorDefinition` (source type, config, `ConnectorSchedule`, `ConnectorMappingRef` naming the target feed, `credentials_ref`), `ConnectorSyncRun` (+ `Create` / `Update`, `ConnectorSyncCounters`: pulled / accepted / quarantined / failed), `ConnectorQuarantineRecord`, page models, the type literals, and `redact_credentials_ref`. |
| `repository.py` | `ConnectorRepositoryProtocol` — definitions, runs (`create_run`, `claim_sync_run`, `update_run`, `list_runs`, `list_stale_runs`), quarantine (`add_quarantine_record`, `list_quarantine`). |
| `adapters/in_memory.py` / `adapters/postgres.py` | `InMemoryConnectorRepository`, `PostgresConnectorRepository`. |
| `service.py` | `ConnectorService` — `register_connector`, `list_connectors`, `start_sync` (publishes the first page event), `complete_sync`, `fail_sync`, `quarantine_record`, `list_runs`, `list_quarantine`; `IMPLEMENTED_SOURCE_TYPES`, `IMPLEMENTED_SCHEDULE_MODES`. |
| `executor.py` | `handle_connector_page_queued` — registered with `execution.registry.register_handler("connector.page.queued", ...)`. |
| `reconciler.py` | `ConnectorSyncReconciler.reconcile_stale_runs` — fails `queued` / `running` runs that stopped progressing (`stale_connector_sync_reconciled`). |
| `status_adapter.py` | `execute_connector_sync_status_capability` and `CONNECTOR_SYNC_STATUS_CAPABILITY_ID` (`connector.sync.status`) for the capability registry. |
| `sources/protocols.py` | `ConnectorSourceAdapter.read_page(config, cursor, limit)` → `SourcePage` (rows + opaque `next_cursor`). |
| `sources/filesystem.py` | `FilesystemSourceAdapter` — pages CSV rows from a directory tree confined to `allowed_root`. |
| `exceptions.py` | `ConnectorError`, `ConnectorValidationError`, `ConnectorSourceError`. |

## Contracts and invariants

- **Only what runs is accepted.** `register_connector` rejects source types
  outside `IMPLEMENTED_SOURCE_TYPES` (`filesystem`) and schedule modes outside
  `IMPLEMENTED_SCHEDULE_MODES` (`manual`), even though the model literals also
  declare `object_store`, `http`, `interval`, `cron`. Re-registering an
  identical definition is idempotent; a different one under the same id is
  rejected. `start_sync` re-checks the source type and honours an optional
  `idempotency_key`.
- **Rows go through `RecordsService`.** The executor calls
  `records_service.register_records`, so validation, submission-hash dedup and
  the `records.ingested` publish are the manual-upload code path. One
  ingest correlation id is assigned per run and reused for every page.
- **Page handling** (`handle_connector_page_queued`): skips terminal runs and
  events whose cursor differs from the run's stored `source_cursor`
  (redelivery / out-of-order); claims a `queued` run on the first page;
  partitions out rows with no derivable record id (quarantined instead of
  failing the batch); moves counters and quarantine only when the receipt is
  not a duplicate; advances the cursor only after rows are registered; then
  either publishes the next `ConnectorPageQueuedEvent` or marks the run
  `completed`.
- **Fail, don't retry, the impossible.** A deleted connector, a source type
  with no adapter, an unconfigured feed, or a `ConnectorSourceError` fails the
  run with a reason. Other exceptions propagate to the worker's retry /
  dead-letter handling.
- `credentials_ref` is exposed only in redacted form
  (`ConnectorDefinition.credentials_display`).

## How it is reached

- **API:** `api/routers/connectors.py`, prefix
  `/knowledgebases/{knowledge_base_id}/connectors`: `GET ""` (viewer),
  `POST ""` (analyst, register), `POST /{connector_id}/sync-runs` (analyst,
  start), `GET /{connector_id}/sync-runs` (viewer),
  `GET /{connector_id}/quarantine` (viewer).
- **Worker:** `execution/__init__.py` imports `connectors.executor` so the
  handler registers; `agent/coordinator.py` supplies
  `build_connector_source_adapters()` and runs `ConnectorSyncReconciler` on
  the same periodic tick and cutoff as the score-run and workflow sweeps.
- **Capability:** `connector.sync.status` is bound in the worker by
  `capabilities/builtin_executors.py`.

## Configuration

| Env var | Default | Effect |
|---------|---------|--------|
| `CHILI_CONNECTOR_FS_ROOT` | `/imports` | `allowed_root` of the worker's `FilesystemSourceAdapter`. |
| `CHILI_CONNECTOR_PAGE_LIMIT` | `500` | Rows per page; read once at import, non-positive / non-integer values fall back to the default. |

## Persistence

`database/migrations/versions/0025_connectors.py` creates `connectors`
(`ix_connectors_kb`), `connector_sync_runs`
(`ux_connector_sync_runs_idempotency`,
`ix_connector_sync_runs_connector_status`) and
`connector_quarantine_records` (`ix_connector_quarantine_run`,
`ix_connector_quarantine_connector`).
`0026_connector_sync_stale_index.py` adds
`ix_connector_sync_runs_status_updated` for the reconciler scan.

## Current gaps

- Nothing schedules runs: only `manual` mode is accepted.
- `ConnectorRepositoryProtocol` has no KB-scoped delete, and
  `knowledgebases/cleanup.py` does not touch connector tables.

## Tests

`tests/connectors/` — `test_service.py`, `test_executor.py`,
`test_reconciler.py`, `test_filesystem_source.py`, `test_status_adapter.py`,
`test_in_memory.py`, `test_postgres.py`.

See also: [records](../records/README.md), [execution](../execution/README.md),
[capabilities](../capabilities/README.md),
[event catalog](../../docs/ledger/event-catalog.md).
