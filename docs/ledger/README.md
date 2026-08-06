# chiliAI Code Ledger

**Generated:** 2026-05-22 (anchored to merge commit `acae4ac`, `feature/ingestion-pipeline-e2e-demo` → `prod`)
**Reviewed:** 2026-05-28 against the current working tree for docs-keeper consistency cleanup.
**Purpose:** Generated point-in-time snapshot and index of the codebase's public surface — module map, protocol contracts, event catalog, HTTP routes, config schema, and tooling inventory. Intended for agents and developers who need a fast structured overview without reading the full codebase. It is anchored to the commit noted above and goes stale between refreshes: where this ledger disagrees with the code or with `docs/wiki/`, they win.

## Contents

| File | Purpose |
|------|---------|
| [module-map.md](module-map.md) | Per-module purpose, public surface, adapters, and inter-module dependencies |
| [protocol-contracts.md](protocol-contracts.md) | Selected `Protocol`s — methods and implementing adapters. **Partial:** ~20 of ~30 public repository protocols; the SAFE-CMS repository protocols are absent |
| [event-catalog.md](event-catalog.md) | Event types in `backend/events/types.py` — payload shape, publisher, consumer. Union reconciled to 32 members 2026-08-06; per-event sections still reflect the 2026-05-22 sweep |
| [http-routes.md](http-routes.md) | FastAPI routes — method, path, request/response models, required role. **Partial:** 49 of 105 paths; see the coverage warning in the file |
| [config-schema.md](config-schema.md) | `DomainConfig` top-level fields + medicare_fraud entity/relationship/feed inventory |
| [tooling-inventory.md](tooling-inventory.md) | `tools/` CLI tools and `scripts/` shell drivers |

## Relationship to Other Docs

- `docs/architecture.md` — *Why* and high-level system shape (C4 diagrams, guiding principles). This ledger indexes the *what* as of its snapshot date.
- `docs/wiki/` — Developer wiki (module pages, contracts, flows). The wiki is the maintained, authoritative narrative reference; this ledger is a generated index/snapshot that supplements it and defers to it where they disagree.
- `CLAUDE.md` — Operating rules and common commands.
