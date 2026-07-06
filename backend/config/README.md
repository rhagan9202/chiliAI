# config — Domain Configuration

The domain-reconfigurability core of chiliAI. A single YAML/JSON "domain
pack" retargets the whole platform — entities, relationships, records feeds,
policy rules, alert thresholds, UI navigation/labels, and infra backend
selection — with **zero code changes**.

## Layout

- `schema.py` — `DomainConfig` (Pydantic) and all section sub-models. The
  `_validate_cross_references` model validator enforces referential integrity
  (see "Validation" below).
- `loader.py` — `load_config(path=None)`: resolves the file (explicit `path`
  argument, else the active-pack pointer, else `CHILI_CONFIG_PATH`), parses
  YAML/JSON, validates, and returns a `DomainConfig`. Raises
  `ConfigLoadError` on any failure.
- `store.py` — file-backed **active-pack pointer store**. Persists which
  pack is active in a small JSON state file, `data/config/active_pack.json`
  (in containers: `/app/data/config/active_pack.json` on the shared
  `chili-object-data` volume, so API and worker follow the same pointer).
  Atomic writes (temp file + `os.replace`). Public surface:
  `read_active_pack()`, `write_active_pack()`, `clear_active_pack()`,
  `resolve_config_path()` (precedence: pointer > `CHILI_CONFIG_PATH` >
  error). `CHILI_ACTIVE_PACK_STATE_PATH` relocates the state file (tests
  point it at a temp dir). The pointer is written by the admin config API
  (`POST /config/apply|switch`) only after the candidate pack fully
  validates; a corrupt pointer file fails loudly rather than silently
  reverting the deployment to a different domain.
- `defaults/` — the shipped domain packs:
  - `medicare_fraud_cms_desynpuf.yaml` — the exemplar pack (CMS DE-SynPUF
    Medicare fraud detection). **Default** for `make dev` and `make prod`.
  - `food_supply_chain.yaml` — food supply chain integrity (fraud,
    contamination, traceability). Exemplar-parity peer pack; proves the
    retargeting thesis.
  - `department_air_force_housing.yaml` — Department of the Air Force housing
    visibility, file/export feeds for UMD, BAH, inventory, market, and
    demographics, plus configurable UH/MFH scorecard templates.
  - `medicare_fraud.yaml`, `medicare_fraud_dev.yaml` — minimal/dev variants.

## Switching domains

Both compose files parameterize `CHILI_CONFIG_PATH` on the `api` **and**
`worker` services (they must always move together), defaulting to the
medicare exemplar:

```yaml
- CHILI_CONFIG_PATH=${CHILI_CONFIG_PATH:-/app/config/defaults/medicare_fraud_cms_desynpuf.yaml}
```

Switch the dev stack with the make target (validates the pack file exists):

```bash
make dev-domain DOMAIN=food_supply_chain
```

or set the env var directly (works for `make dev`, `make prod`, and raw
`docker compose` — the path is the in-container path under `/app`):

```bash
CHILI_CONFIG_PATH=/app/config/defaults/food_supply_chain.yaml make dev
```

Plain `make dev` / `make prod` behavior is unchanged (medicare exemplar).
For local host runs (no Docker), point at the file on disk:

```bash
CHILI_CONFIG_PATH=backend/config/defaults/food_supply_chain.yaml \
  uvicorn api.app:create_app --factory --port 8000
```

The frontend needs no configuration: it fetches `GET /config/domain` at
startup and renders entity labels, navigation, and feature gates from the
active pack.

A running stack can also be hot-swapped without restart from the
Configuration page (Config Manager) or the admin API
(`POST /config/switch`); the worker converges via a `config.updated` event.
See `docs/architecture.md` §9.3 for the swap pipeline and its constraints
(notably: a pack must not change the `events` transport across a hot-swap).

### Gotcha: the persisted pointer overrides `CHILI_CONFIG_PATH`

After **any** switch or apply through the UI/API, the active-pack pointer is
persisted to `data/config/active_pack.json` — and on every subsequent boot
the pointer **wins over** `CHILI_CONFIG_PATH`. Concretely: once you've
switched domains in the UI, `make dev-domain DOMAIN=...` (or editing
`CHILI_CONFIG_PATH`) will *not* retarget the stack on restart until the
pointer is cleared. To clear it, either:

- switch back to the desired pack via the UI / `POST /config/switch`
  (updates the pointer), or
- delete the state file (`/app/data/config/active_pack.json` inside the
  api/worker containers, on the `chili-object-data` volume) or call
  `config.store.clear_active_pack()` — the stack then falls back to plain
  env-based `CHILI_CONFIG_PATH` resolution on next boot.

## Pack-authoring contract

A pack is a single YAML (or JSON) file validated against `DomainConfig`.
Use `medicare_fraud_cms_desynpuf.yaml` and `food_supply_chain.yaml` as
references. Required top-level sections: `domain`, `entities`,
`relationships`, `capabilities`, `ingestion`, `alerts`; everything else is
optional and falls back to in-memory/local defaults.

Section checklist for a first-class pack:

1. **`domain`** — `name` (snake_case identifier), `display_name`,
   `description`.
2. **`entities`** — each with `name`, `display_label`, `icon`, a
   `natural_key` list, and typed `properties` (`string`, `integer`,
   `decimal`, `date`, `list`, `boolean`, `enum`, `nested`). `enum`
   properties **must** declare `enum_values`.
3. **`relationships`** — `name`, `display_label`, `source`, `target`;
   source/target must name declared entities.
4. **`capabilities`** — feature gates (`timeseries`, `gnn`, `risk_scoring`,
   `rag_chat`, `explainability`, `structured_ingestion`, `peer_stats`).
   These gate both backend behavior and UI pages.
5. **`records.feeds`** — structured-ingestion feeds. Each feed declares a
   `record_schema`, an `id_field` (or `id_template`), and mappings from rows
   to `entities`, `relationships`, and scored `observations`. All references
   are cross-validated at load (see below).
6. **`policy_rules`** — rule packs with `thresholds` referenced by
   `config_ref` predicates; unknown refs fail at load.
7. **`scorecards.templates`** — safe configurable report templates. Each
   template declares category, scope, period, sections, metrics, bounded
   formula operators (`ratio`, `sum`, `mean`, `weighted_mean`, `latest`),
   record-feed inputs, thresholds, freshness windows, and export formats.
   The Air Force housing pack ships UH and MFH templates exporting JSON and
   Markdown.
8. **`alerts.thresholds`** — per-entity-type metric thresholds.
9. **`ui`** — this drives dynamic frontend rendering: `default_entity_type`,
   `navigation.pages` (id/label/route, optional `capability` gate),
   `display_fields` per entity (`title`/`subtitle`/`chips` naming entity
   properties), and `roles` (landing page + page list + permission hints).
   Cover **every** entity in `display_fields` so all entity types render.
10. **Infra sections** (`graph`, `vectorstore`, `embeddings`, `llm`,
   `storage`, `events`, `database`, `monitoring`, `analytics`, `rag`) —
   omit for in-memory/local defaults, or pin real backends. The shipped
   packs pin the dev-stack services (neo4j, qdrant, redis, postgres, local
   object storage, local LLM with fallback chain). Only implemented adapter
   backends are legal literals. Secrets are **never** inline — use the
   `*_env_var` pattern (the value is the *name* of an environment variable).

## Validation

`DomainConfig` fails fast at load on:

- duplicate entity/relationship names;
- relationship `source`/`target` not matching a declared entity;
- `enum` properties without `enum_values`;
- records-feed integrity: `id_field` and every mapping `id_field` /
  observation `score_field` must exist in the feed's `record_schema`; entity
  mappings must reference declared entities; relationship mappings must
  reference declared relationship types whose endpoints are mapped by the
  same feed; observation entity types must be mapped by the feed;
- scorecard template integrity: duplicate template/section IDs fail, duplicate
  metric IDs fail within a section, record-feed inputs must reference declared
  feeds, formula input references must name declared metric inputs, and metric
  freshness windows must be positive;
- policy-rule `config_ref`s not declared in the owning pack's `thresholds`;
- `vectorstore.dimensions` != `embeddings.dimensions` when both are set.

Verify a pack without booting anything:

```bash
cd backend
.venv/bin/python -c "from config.loader import load_config; load_config('config/defaults/food_supply_chain.yaml')"
.venv/bin/pytest tests/config -q
```

`tests/config/test_food_supply_chain_pack.py` is the reference for what a
pack test should assert (load via `CHILI_CONFIG_PATH`, feed cross-validation,
complete `ui` section, entity/relationship referential integrity, compose
parameterization).
