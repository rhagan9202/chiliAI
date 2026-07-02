# chiliAI Backlog

> Single source of truth for what's planned, in-progress, and done across the platform.
> See [docs/architecture.md](../architecture.md) for the target architecture this backlog drives toward.
> Design spec: [docs/superpowers/specs/2026-05-24-complete-backlog-design.md](../superpowers/specs/2026-05-24-complete-backlog-design.md).

## How to read this
- Stories live in `docs/backlog/<module>.md` and `docs/backlog/_<concern>.md`.
- Each story carries fields: `ID`, `Status` (planned/in-progress/done/dropped), `Prerequisites`, `Unblocks` (derived), `Estimated size` (S/M/L/XL), `Spec` (optional), `Done` (when status=done).
- Acceptance Criteria are live checkboxes `[ ]`/`[x]` — checked as work lands.
- Cross-file prerequisites are explicit; the consistency pass enforces no cycles and rewrites `Unblocks` lines.
- Design specs in `docs/superpowers/specs/` are linked from individual stories via `Spec:`.

## Status roll-up
<!-- BEGIN: status-rollup -->
| File | Planned | In-progress | Done | Total | % done |
|------|---------|-------------|------|-------|--------|
| _cicd.md | 20 | 1 | 0 | 21 | 0% |
| _infra.md | 19 | 0 | 0 | 19 | 0% |
| _multitenancy.md | 16 | 0 | 0 | 16 | 0% |
| _observability.md | 11 | 1 | 0 | 13 | 0% |
| _plugins.md | 16 | 0 | 0 | 16 | 0% |
| _security.md | 12 | 0 | 0 | 12 | 0% |
| agent.md | 19 | 0 | 1 | 20 | 5% |
| analytics.md | 33 | 0 | 0 | 33 | 0% |
| api.md | 27 | 0 | 1 | 29 | 3% |
| config.md | 15 | 0 | 0 | 15 | 0% |
| database.md | 13 | 0 | 0 | 13 | 0% |
| embeddings.md | 12 | 0 | 0 | 12 | 0% |
| events.md | 14 | 2 | 0 | 16 | 0% |
| frontend.md | 24 | 0 | 2 | 26 | 7% |
| graph.md | 20 | 0 | 0 | 20 | 0% |
| ingestion.md | 25 | 0 | 10 | 35 | 28% |
| knowledgebases.md | 13 | 0 | 0 | 13 | 0% |
| llm.md | 17 | 0 | 0 | 17 | 0% |
| monitoring.md | 20 | 0 | 0 | 20 | 0% |
| rag.md | 17 | 0 | 0 | 17 | 0% |
| records.md | 10 | 2 | 1 | 13 | 7% |
| shared.md | 17 | 1 | 0 | 18 | 0% |
| storage.md | 14 | 0 | 0 | 14 | 0% |
| vectorstore.md | 14 | 0 | 0 | 14 | 0% |
| **Total** | 418 | 7 | 15 | 442 | 3% |
<!-- END: status-rollup -->

## Ready set (work that can start today)
> **Priority flag (ingestion):** the graph-corrupting relationship defects are fixed — `ingestion.30` (use the model's relationship output instead of fabricating Cartesian edges), `ingestion.31` (resolve endpoints onto cross-chunk-deduplicated survivors), `ingestion.32` (failure-event escape paths), and `ingestion.33` (full-digest document identity) are all done. `ingestion.34` (record-derived entities now stamped `source_kind="record"`) is done. `ingestion.35` (documents with zero valid entities silently marked ready) has its core fix shipped — empty/degraded extractions now emit a durable `DocumentsExtractionWarningEvent` and the validator strips hallucinated extra properties instead of dropping entities — but it stays `planned` pending its metrics (`ingestion.17`) and status-projection/API (`ingestion.18`) cross-edges. See [ingestion.md](ingestion.md) story 35.
<!-- BEGIN: ready-set -->
- [_cicd.01] _cicd — size S — prereqs done
- [api.26] api — size S — prereqs done
- [shared.01] shared — size S — prereqs done
- [shared.17] shared — size S — prereqs done
- [_cicd.02] _cicd — size M — prereqs done
- [_cicd.03] _cicd — size M — prereqs done
- [_cicd.04] _cicd — size M — prereqs done
- [_infra.02] _infra — size M — prereqs done
- [_security.09] _security — size M — prereqs done
- [_security.11] _security — size M — prereqs done
- [agent.01] agent — size M — prereqs done
- [agent.04] agent — size M — prereqs done
- [agent.11] agent — size M — prereqs done
- [agent.13] agent — size M — prereqs done
- [agent.15] agent — size M — prereqs done
- [analytics.33] analytics — size M — prereqs done
- [config.02] config — size M — prereqs done
- [config.03] config — size M — prereqs done
- [database.03] database — size M — prereqs done
- [database.04] database — size M — prereqs done
- [database.05] database — size M — prereqs done
- [database.07] database — size M — prereqs done
- [embeddings.01] embeddings — size M — prereqs done
- [embeddings.06] embeddings — size M — prereqs done
- [frontend.06] frontend — size M — prereqs done
- [frontend.10] frontend — size M — prereqs done
- [frontend.13] frontend — size M — prereqs done
- [frontend.14] frontend — size M — prereqs done
- [ingestion.35] ingestion — size M — prereqs done
- [knowledgebases.03] knowledgebases — size M — prereqs done
- …23 more
<!-- END: ready-set -->

## Critical path
<!-- BEGIN: critical-path -->
> Longest dependency chain by weighted size (S=1, M=2, L=5, XL=10).
1. database.03 (M=2) →
2. database.02 (L=5) →
3. config.06 (L=5) →
4. config.07 (M=2) →
5. config.05 (L=5) →
6. config.08 (L=5) →
7. config.14 (L=5) →
8. config.15 (M=2) →
9. monitoring.07 (L=5) →
10. monitoring.15 (L=5) →
11. monitoring.16 (M=2) →
12. api.05 (L=5) →
13. api.06 (M=2) →
14. monitoring.01 (M=2) →
15. api.01 (L=5) →
16. api.28 (L=5) →
17. api.29 (M=2) →
18. rag.01 (L=5) →
19. llm.07 (L=5) →
20. ingestion.11 (L=5) →
21. analytics.01 (L=5) →
22. analytics.31 (L=5) →
23. analytics.32 (M=2) →
24. _plugins.01 (L=5) →
25. _plugins.02 (L=5) →
26. _plugins.13 (L=5) →
27. _plugins.14 (M=2) →
28. _plugins.03 (L=5) →
29. _plugins.05 (L=5) →
30. _plugins.15 (L=5) →
31. _plugins.16 (M=2) →
32. _plugins.07 (L=5) →
33. _plugins.09 (L=5)

**Total weight: 135**
<!-- END: critical-path -->

## Cross-cutting epics
- [_cicd.md](_cicd.md) — CI/CD deploy & promotion
- [_infra.md](_infra.md) — K8s manifests, Helm chart, Terraform/Pulumi IaC
- [_multitenancy.md](_multitenancy.md) — tenant scoping across data/config/KB
- [_observability.md](_observability.md) — logging, metrics (Prometheus/OTEL), tracing, frontend RUM
- [_plugins.md](_plugins.md) — third-party plugin SPI
- [_security.md](_security.md) — IdP profiles, secrets, TLS, RBAC hardening, audit log

## Module backlogs
- [agent.md](agent.md) — workflow coordinator, run lifecycle, DLQ ops
- [analytics.md](analytics.md) — timeseries, gnn, risk, explainability, metrics
- [api.md](api.md) — FastAPI gateway, DI wiring, route surface, contracts
- [config.md](config.md) — domain config schema, loader, hot-reload, UI wizard
- [database.md](database.md) — Postgres + TimescaleDB + Alembic
- [embeddings.md](embeddings.md) — embedder protocol + adapters
- [events.md](events.md) — Redis Streams events + consumer groups
- [frontend.md](frontend.md) — React analyst workbench SPA
- [graph.md](graph.md) — graph DB protocol + adapters
- [ingestion.md](ingestion.md) — document parsing, chunking, extraction
- [knowledgebases.md](knowledgebases.md) — KB metadata persistence + lifecycle
- [llm.md](llm.md) — LLM client protocol + adapters
- [monitoring.md](monitoring.md) — claim stream consumer, alert generation
- [rag.md](rag.md) — query → embed → search → graph expand → LLM
- [records.md](records.md) — structured/tabular ingestion (CSV/JSONL/api-push)
- [shared.md](shared.md) — domain types, protocols, utilities
- [storage.md](storage.md) — object storage protocol + adapters
- [vectorstore.md](vectorstore.md) — vector store protocol + adapters

## Archived / superseded
- `docs/agent_backlog_05_17.md` → [docs/archive/planning/agent_backlog_05_17.md](../archive/planning/agent_backlog_05_17.md) — superseded by [agent.md](agent.md) on 2026-05-24
- `docs/graph_backlog_05_17.md` → [docs/archive/planning/graph_backlog_05_17.md](../archive/planning/graph_backlog_05_17.md) — superseded by [graph.md](graph.md) on 2026-05-24
- `docs/ingestion_backlog_05_17.md` → [docs/archive/planning/ingestion_backlog_05_17.md](../archive/planning/ingestion_backlog_05_17.md) — superseded by [ingestion.md](ingestion.md) on 2026-05-24

## Design specs (referenced from stories)
Stories link to specs via the `Spec:` field. Specs currently referenced (hand-maintained list):
- `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md`
- `docs/superpowers/specs/2026-05-14-backend-persistence-design.md`
- `docs/superpowers/specs/2026-05-17-ingestion-studio-ui-ux-design.md`
- `docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md`
- `docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md`
- `docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md`
- `docs/superpowers/specs/2026-05-21-ingestion-prerequisite-vs-error-design.md`
- `docs/superpowers/specs/2026-05-21-kb-contextual-entry-points-design.md`
- `docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md`
- `docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`
- `docs/superpowers/specs/2026-05-24-complete-backlog-design.md`

## Maintenance
- **Adding a story:** pick the file, allocate the next free `<file>.<n>` ID, fill the rich format (see [spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format)), run `python scripts/backlog_consistency.py`.
- **Closing a story:** flip Status to `done`, fill `Done:`, check the AC boxes, run the consistency pass.
- **Consistency pass:** `python scripts/backlog_consistency.py` (writes) or `--check` (CI mode, read-only).
