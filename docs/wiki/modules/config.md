# Module: config

**Verified against codebase:** 2026-05-20
**Source:** `backend/config/`

## Purpose

Domain configuration loading and schema validation. Produces the `DomainConfig` Pydantic model that drives backend behavior and frontend rendering.

---

## Public Surface

### `config/schema.py`

Exports `DomainConfig` and all sub-models. See [contracts/domain-config.md](../contracts/domain-config.md) for the full schema.

### `config/loader.py`

```python
def load_config(path: str | None = None) -> DomainConfig:
```
- When `path` is None, resolves via `config.store.resolve_config_path()`: active-pack pointer (`data/config/active_pack.json`) > `CHILI_CONFIG_PATH` env var > `ConfigLoadError`.
- Supports YAML (`.yaml`, `.yml`) and JSON (`.json`) files.
- Parses and validates against `DomainConfig`.
- Result is LRU-cached in `api/dependencies.py::get_domain_config()`.

---

## Default Config Files

Located in `backend/config/defaults/`:
- `medicare_fraud.yaml`
- `medicare_fraud_dev.yaml`
- `food_supply_chain.yaml`

---

## Module Dependencies

- `shared/types.py` — imports `EntityDefinition`, `RelationshipDefinition`, `PropertyDefinition`
- Standard library + `pydantic`

---

## Frontend Contract

The frontend fetches config at startup via `GET /config/domain`. The TypeScript mirror is `chili_app/src/types/domainConfig.ts`. The frontend uses config to:
- Render entity labels and icons
- Show/hide features based on `CapabilitiesConfig` flags
- Drive navigation via `UiConfig.navigation`
- Apply entity display field mappings (`UiConfig.display_fields`)
