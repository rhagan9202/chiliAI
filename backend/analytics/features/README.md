# analytics/features

Read surface for the active domain pack's **feature catalog** and fraud
**typologies**, plus the contract for normalized per-entity feature values.
The catalog itself is configuration, not code: `DomainConfig.feature_catalog`
(`config.schema.FeatureCatalogConfig` — a `version` plus a list of
`FeatureDefinitionConfig`) and `DomainConfig.typologies`
(`FraudTypologyConfig`). This package exposes them through a small service and
defines `FeatureValueRecord` for values computed against a catalog version.

Part of the analytics package family — see [`../README.md`](../README.md) for
shared conventions; this package is one of the submodules that deviates from
the standard template (no `service_models.py`, `exceptions.py` or Postgres
adapter).

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `FeatureValueRecord` — KB-scoped `entity_type` / `entity_id` / `feature_id`, raw `value`, `normalized_value` in `[0, 1]`, `catalog_version`, `transformation_version`, `source_refs`, `observed_at` (normalized to UTC), optional `score_run_id`. |
| `protocols.py` | `FeatureValueRepositoryProtocol` — `upsert`, `list_for_entity`, `delete_by_kb`. |
| `adapters/in_memory.py` | `InMemoryFeatureValueRepository`; upsert key is `(kb, entity_type, entity_id, feature_id, catalog_version, transformation_version, score_run_id)`; `list_for_entity` sorts by `(feature_id, observed_at)`. |
| `service.py` | `FeatureCatalogService` (`get_catalog`, `list_typologies`, `list_entity_values`) and `create_feature_catalog_service`. |

## Contracts

- `FeatureCatalogService` holds no state beyond the injected `DomainConfig`;
  switching packs switches the catalog.
- `FeatureValueRecord` is also used by `analytics/risk/projection_service.py`,
  which carries feature values on its projections.
- The catalog `version` is load-bearing elsewhere: the score-run batch
  executor (`analytics/score_runs/executor.py`) fails a run whose recorded
  catalog version differs from the active pack's `feature_catalog.version`
  (`catalog_version_changed`), and playbook imports validate `feature_ids`
  against this catalog (see [`../../playbooks/README.md`](../../playbooks/README.md)).

## How it is reached

API only, via `get_feature_catalog_service` in `api/dependencies.py`; both
routes live in `api/routers/knowledgebases.py`, require the viewer role, and
404 for an unknown KB:

- `GET /knowledgebases/{knowledge_base_id}/features/catalog` — catalog
  version, typologies and feature definitions.
- `GET /knowledgebases/{knowledge_base_id}/entities/{entity_type}/{entity_id}/features`
  — normalized feature values for one entity.

No worker handlers or events.

## Persistence

None. The catalog comes from the domain pack; `FeatureValueRepositoryProtocol`
has only the in-memory adapter.

## Current gaps

- `FeatureCatalogService.list_entity_values` returns an empty list
  unconditionally (its docstring defers durable feature-value persistence), so
  the entity-features route always returns no items.
- `InMemoryFeatureValueRepository` is not wired into the API or worker; no
  production code writes `FeatureValueRecord`s through the protocol.

## Tests

`tests/analytics/features/test_in_memory.py`; route coverage in
`tests/api/test_knowledgebases_router.py`.
