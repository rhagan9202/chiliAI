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
  `ConfigLoadError` on any failure. After parsing the base file, if
  `CHILI_CONFIG_OVERLAY_PATH` is set it is split on commas into an ordered
  list of overlay file paths, layered onto the base via `overlay.py`'s
  `apply_overlays` (each overlay must declare `overlay_for` matching
  `domain.name`, or it is skipped with a warning), before schema validation
  runs. `overlay.py` — pure base+overlay deep-merge semantics (`ADR 0001`);
  see its module docstring for merge rules.
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
- `defaults/` — the shipped domain packs (each a complete, independently
  loadable `DomainConfig`; iterated by the config API's pack catalog, so
  every file here is discoverable/switchable via the Config Manager /
  `POST /config/switch`):
  - `medicare_fraud_cms_desynpuf.yaml` — the exemplar pack (CMS DE-SynPUF
    Medicare fraud detection). **Default** for `make dev` and `make prod`.
  - `food_supply_chain.yaml` — food supply chain integrity (fraud,
    contamination, traceability). Exemplar-parity peer pack; proves the
    retargeting thesis.
  - `department_air_force_housing.yaml` — Department of the Air Force housing
    visibility, file/export feeds for UMD, BAH, inventory, market,
    demographics, and resident experience, plus configurable UH (8-metric)
    and MFH (12-metric) statutory scorecard templates whose per-metric
    provenance is documented in
    [`../../docs/research/housing-scorecard-mandates.md`](../../docs/research/housing-scorecard-mandates.md).
  - `medicare_fraud.yaml` — minimal variant; also the base pack the dev
    overlay below layers onto.
- `overlays/` — environment overlay files (ADR 0001), layered onto a base
  pack via `CHILI_CONFIG_OVERLAY_PATH` (see "Config overlays" below). An
  overlay is a **partial** config — it omits required `DomainConfig`
  sections like `entities` — so it is never itself loadable as a standalone
  pack, and the pack catalog does not iterate this directory.
  - `medicare_fraud_dev.yaml` — the dev-environment overlay for
    `defaults/medicare_fraud.yaml`: dev-stack infra pins (Neo4j, Redis,
    Qdrant, Postgres, local object storage), `capabilities.peer_stats:
    false`, a lower `policy_rules` billing threshold, and a `ui` display-field
    addition. Moved here from `defaults/` and rewritten as a 115-line overlay
    (was a 284-line full-pack duplicate — a 59% reduction).

## Config overlays (base + environment layering)

Environment configs (dev/staging/prod knob flips) no longer duplicate the
whole domain surface. `CHILI_CONFIG_OVERLAY_PATH` names one or more overlay
files (comma-separated, declared order, last wins) layered onto the base
pack **before** schema validation:

```bash
CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml \
CHILI_CONFIG_OVERLAY_PATH=config/overlays/medicare_fraud_dev.yaml \
  uvicorn api.app:create_app --factory --reload --port 8000
```

Merge semantics (full rationale in
[`../../docs/architecture/decisions/0001-config-overlay-merge-semantics.md`](../../docs/architecture/decisions/0001-config-overlay-merge-semantics.md)):

- Mappings **deep-merge** — overlay keys win recursively.
- Lists and scalars **replace wholesale** — no list-merge-by-key.
- An explicit `null` sets a field to `None`; absence falls through to the
  base value or the schema default. There is no key-removal operator.
- Every overlay file must declare `overlay_for: <domain.name>`. If it
  matches the base's `domain.name` the overlay applies; a mismatch **skips
  the overlay with a warning** rather than failing the boot — this is what
  lets `CHILI_CONFIG_OVERLAY_PATH` survive a runtime hot-swap to a different
  pack (the swap just runs clean base config for the foreign overlay). A
  missing `overlay_for`, or any top-level key not in
  `DomainConfig.model_fields` (checked via the public
  `config.overlay.known_top_level_keys()`), is a hard `OverlayError` —
  raised as `ConfigLoadError` by `load_config` — so a typo like
  `embeddngs:` fails loudly instead of silently not applying.

`config/overlay.py` implements the pure merge (`merge_config_layers`) and
the guarded per-overlay application (`apply_overlays`); `config/loader.py`
wires `CHILI_CONFIG_OVERLAY_PATH` into every `load_config` call — explicit
`path`, plain env resolution, and the pointer-following `load_active_config`
all apply the same overlay stack, since `load_active_config` delegates to
`load_config`.

`backend/tests/config/test_overlay.py` covers this with hypothesis
property tests (deep-merge associativity **on type-stable stacks**, empty-
overlay identity, list-replacement — see ADR 0001 for the type-flip
boundary case) plus example-based tests (`overlay_for` match/mismatch/
missing, unknown-key rejection, comma-separated stacking order) and a golden
equivalence test (`test_medicare_dev_overlay_reproduces_old_full_config`)
that proves `medicare_fraud.yaml ⊕ overlays/medicare_fraud_dev.yaml`
reproduces the retired full dev file byte-for-byte (modulo the documented
`peer_stats` exception), loading the retired file from a checked-in fixture
(`backend/tests/config/fixtures/medicare_fraud_dev_full_snapshot.yaml`)
rather than git history, since CI's checkout is shallow.

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
   are cross-validated at load (see below). Observation scores are hard-bound
   to `[0, 1]` (`MonitoringObservation.score`); a `score_field` on another
   scale (e.g. a 0–100 index) declares `score_max` on the observation mapping
   and the mapper divides raw values by it (`score = value / score_max`).
   `score_max` is a scale conversion only — values still out of range after
   division raise a hard `RecordMappingError` (never clamped), so raw counts
   with no natural upper bound cannot be observations; model them as entity
   properties / scorecard record-feed inputs instead.
6. **`policy_rules`** — rule packs with `thresholds` referenced by
   `config_ref` predicates; unknown refs fail at load.
7. **`scorecards.templates`** — safe configurable report templates. Each
   template declares category, scope, period, sections, metrics, bounded
   formula operators (`ratio`, `sum`, `mean`, `weighted_mean`, `latest`),
   record-feed inputs, thresholds, freshness windows, and export formats.
   Formula fields are operator-specific: ratios use numerator/denominator,
   sums/means/latest use value, and weighted means use value/weight. Record
   feed inputs must name a declared feed field. Thresholds grade in exactly
   one direction per metric: higher-is-better (`pass_min`/`warn_min`/
   `fail_max`) **or** lower-is-better (`pass_max`/`warn_max`/`fail_min`) —
   mixing directions is a load error, at least one bound is required, and
   bounds must be ordered so grading bands cannot overlap. The Air Force
   housing pack ships UH and MFH templates exporting JSON and Markdown.
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
- observation bound proof: every observation `score_field` must be provable
  at load time to land in `[0, 1]` for all in-schema values. Concretely, the
  `record_schema` field must (a) be a numeric type (`integer` or `decimal` —
  bounds on non-numeric types are not enforced at record intake, so anything
  else is rejected), (b) declare `min_value >= 0`, and (c) declare
  `max_value <= 1`, **or** the observation sets `score_max` (a `> 0`
  normalization divisor) with a declared `max_value <= score_max`. A field
  with no `max_value` can never carry `score_max` — an unbounded field cannot
  be proven to normalize. This turns the runtime worker failure
  (retries → DLQ → run `failed`) into an unloadable config;
- scorecard template integrity: duplicate template/section IDs fail, metric
  IDs must be unique across each template, record-feed inputs must reference
  declared feeds and fields in those feeds, formula shapes must match their
  operators, formula input references must name declared metric inputs,
  metric freshness windows must be positive, and thresholds must use a
  single grading direction with coherent (non-overlapping) bound ordering;
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
