# chiliAI Code Ledger

**Generated:** 2026-05-22 (anchored to merge commit `acae4ac`, `feature/ingestion-pipeline-e2e-demo` → `prod`)
**Reviewed:** 2026-05-28 against the current working tree for docs-keeper consistency cleanup.
**Purpose:** Generated point-in-time snapshot and index of the codebase's public surface — module map, protocol contracts, event catalog, HTTP routes, config schema, and tooling inventory. Intended for agents and developers who need a fast structured overview without reading the full codebase. It is anchored to the commit noted above and goes stale between refreshes: where this ledger disagrees with the code or with `docs/wiki/`, they win.

## Contents

| File | Purpose |
|------|---------|
| [module-map.md](module-map.md) | Per-module purpose, public surface, adapters, and inter-module dependencies |
| [protocol-contracts.md](protocol-contracts.md) | Every `Protocol` in the codebase — methods and implementing adapters |
| [event-catalog.md](event-catalog.md) | Every event type in `backend/events/types.py` — payload shape, publisher, consumer |
| [http-routes.md](http-routes.md) | Every FastAPI route — method, path, request/response models, required role |
| [config-schema.md](config-schema.md) | `DomainConfig` top-level fields + medicare_fraud entity/relationship/feed inventory |
| [tooling-inventory.md](tooling-inventory.md) | `tools/` CLI tools and `scripts/` shell drivers |

## Relationship to Other Docs

- `docs/architecture.md` — *Why* and high-level system shape (C4 diagrams, guiding principles). This ledger indexes the *what* as of its snapshot date.
- `docs/wiki/` — Developer wiki (module pages, contracts, flows). The wiki is the maintained, authoritative narrative reference; this ledger is a generated index/snapshot that supplements it and defers to it where they disagree.
- `CLAUDE.md` — Operating rules and common commands.
