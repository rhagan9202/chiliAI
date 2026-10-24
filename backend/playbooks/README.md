# playbooks

Versioned **fraud playbooks** and their immutable, KB-scoped published
snapshots. Playbook definitions are authored in the active domain pack
(`DomainConfig.playbooks.items`, typed as `config.schema.FraudPlaybookConfig`);
this module lists those config seeds, publishes them as snapshots, and
exports/imports a portable `playbooks.v1` artifact. Nothing here hardcodes a
domain: a playbook is whatever the pack declares, and imports are validated
against that pack's typologies, feature catalog and policy rules.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `PlaybookSnapshot` (immutable published version), `PlaybookPage` / `PlaybookSnapshotPage`, `PlaybookPublishRequest`, `PlaybookImportArtifact` (`schema_version: "playbooks.v1"`, ≤ 100 playbooks, unique id/version pairs), `PlaybookImportResult`, `PlaybookRef` (historical id + version reference), `PlaybookStatus`, `PlaybookSnapshotSource`, `LEGACY_PLAYBOOK_KNOWLEDGE_BASE_ID` (`"__legacy__"`). |
| `repository.py` | `PlaybookRepository` protocol — `upsert_snapshot / get_snapshot / list_snapshots`. |
| `adapters/in_memory.py` | `InMemoryPlaybookRepository` for tests/dev. |
| `adapters/postgres.py` | `PostgresPlaybookRepository` over `database.ConnectionProvider`; `definition` stored as jsonb. |
| `service.py` | `PlaybookService` — config-seed listing/lookup, publish, export, import, legacy-snapshot adoption. |

## Contracts and invariants

- **Snapshots are immutable.** Natural key is
  `(knowledge_base_id, domain_name, playbook_id, version)`; `snapshot_id` is
  `"{kb}:{domain}:{playbook_id}:{version}"`. Re-publishing or re-importing an
  identical definition returns the existing snapshot; a *different* definition
  under the same key raises `ValueError` (both adapters' `upsert_snapshot`
  enforce this too). Published definitions are stored with `status="published"`.
- **Active domain only.** Every service entry point calls
  `_require_active_domain`, raising `KeyError` when `domain_name` is not the
  loaded pack's `domain.name`.
- **Import validation** (`import_playbooks`): every `typology_ids`,
  `feature_ids` and `policy_rule_ids` (`"{pack.id}.{rule.id}"`) reference must
  exist in the active `DomainConfig`; an imported version that collides with a
  config seed of the same id/version must match it exactly. Errors are joined
  into one `ValueError`. All snapshots are checked before any is written.
- **Export** returns the KB's published snapshots, falling back to the config
  seeds when nothing has been published yet.
- **Legacy adoption.** Snapshots created before KB scoping live under
  `knowledge_base_id = "__legacy__"`. `adopt_legacy_snapshots` copies any that
  the target KB lacks into that KB; publish, export and import call it first.
- `PlaybookRef` is consumed outside this module: `cases.models` carries a
  `playbook_ref`, and `analytics/explainability/service.py` copies it into
  evidence-pack metadata.

## How it is reached

Only through the API — routed by `api/routers/playbooks.py` under
`/knowledgebases/{knowledge_base_id}/playbooks`:

| Route | Role |
|-------|------|
| `GET ""` | viewer — page of config-authored playbooks |
| `GET /export` | viewer — `playbooks.v1` export artifact |
| `GET /{playbook_id}/versions/{version}` | viewer — one config playbook |
| `POST /{playbook_id}/publish` | admin — publish a config seed as a snapshot |
| `POST /import` | admin — import a `playbooks.v1` artifact |

`get_playbook_repository` / `get_playbook_service` in `api/dependencies.py`
select the in-memory adapter when no connection provider is configured,
otherwise Postgres. No worker event handlers consume or emit playbook events.

## Persistence

Table `fraud_playbook_snapshots`, created by
`database/migrations/versions/0019_fraud_playbooks.py` (which also adds the
`cases.playbook_ref` jsonb column) and re-keyed by `0020_playbook_snapshot_kb_scope.py`,
which adds `knowledge_base_id` (existing rows default to `__legacy__`) and makes
the primary key `(knowledge_base_id, domain_name, playbook_id, version)`.
CHECK constraints restrict `status` to `draft|published|retired` and `source`
to `domain_config|api_import|api_publish`.

`delete_by_kb` is the `playbooks` step of the KB-delete cascade
(`knowledgebases/cleanup.py`).

## Tests

`tests/playbooks/` (`test_in_memory.py`, `test_postgres.py`, `test_service.py`),
`tests/api/test_playbooks_router.py`, and the migration tests
`tests/database/test_fraud_playbooks_migration.py` / `test_migration_0020.py`.

See also: [`../cases/README.md`](../cases/README.md),
[`../config/README.md`](../config/README.md),
[`docs/architecture.md`](../../docs/architecture.md).
