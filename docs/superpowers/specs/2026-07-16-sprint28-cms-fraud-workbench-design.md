# Sprint 2026-28 — CMS Fraud Workbench: All Analytics Live + Demo (Design Note)

**Date:** 2026-07-16
**Status:** approved design, pre-plan
**Owner ruling:** the next development focus is shipping the full-feature fraud
detection / graph-visualization / investigative-analytics workbench for CMS
billing — all analytics live and visible (GNN integration, clustering,
policy/explainability engine), enabling a complete demo of all capabilities.

## 1. Current state (verified against `prod` @ 5b5ad92, 2026-07-16)

Already real, wired end-to-end through the event-driven worker pipeline, and
Postgres/Neo4j-backed:

- **Peer-group anomaly detection** — real z-scores over `raw_records` JSONB
  aggregates (`analytics/peerstats`), persisted to `entity_derived_signals`,
  ingest-triggered per feed.
- **Risk scoring** — `LinearScoringStrategy` weighted-sum over derived
  signals, trend vs. history, `RiskScoredEvent`, `risk_score_history`.
- **Explainability** — evidence packs built from real risk factors + real
  `graph.get_subgraph()` output; narrative is template-ish sentence joining.
  A real SHAP adapter exists (`ShapExplainabilityContextSource`) but is
  test-only, unwired.
- **Policy intelligence** — real predicate evaluation (`policy/evaluation.py`)
  against entities + graph metrics, ingest-triggered, durable `PolicyItem`
  lifecycle, live routes + page. (The old seeded `/policy/gaps` is gone.)
- **Monitoring/alerts** — threshold alerting off real risk scores with
  suppression, dedup, rate limiting; alert projection feeds `/alerts` + UI.
- **Graph visualization** — `GraphCanvas` (react-force-graph-2d) mounted in
  the Investigation Workbench: live search → neighborhood (depth 1–5) → risk
  factors → timeseries → evidence pack.
- **CMS data path** — `medicare_fraud_cms_desynpuf` pack fully maps DE-SynPUF
  + NPPES feeds; the TN subset is staged locally (157K NPIs, 294K
  beneficiaries, 4.7M carrier claims) with scripted 1% (`make demo-tn-subset`)
  and full-scale ingest paths.

The gaps this initiative closes:

1. **GNN is a functional no-op.** Real algorithms exist (Louvain communities,
   spectral embeddings, cosine link prediction, centrality scoring) but both
   factory sites hard-code an always-empty `InMemoryGraphSnapshotSource`, so
   the pipeline GNN stage skips on every run and `/analytics/gnn/clusters` +
   the Dashboard clusters panel are permanently empty.
2. **Timeseries anomaly detection is API-triggered only** — not an ingest
   pipeline stage.
3. **Explainability narrative is template joining**; SHAP is unwired.
4. **New analytics have no UI surface** (clusters, predicted links, feature
   attribution), and the workbench presentation is below the bar the demo
   needs.
5. **No scripted, mechanically-validated demo** of the full capability set.

Note: several `docs/backlog/*.md` module stories describe pre-shipped states
(frontend.01, monitoring.02, frontend.05 "Current State" text). Cross-check
`docs/project/planning/backlog.md` + code; clean up at closeout.

## 2. Owner decisions (2026-07-16 Q&A)

| Question | Ruling |
|---|---|
| GNN depth | **Both, staged**: wire the existing heuristic engine live first (demo-ready); trained GNN (BL-030, PyTorch Geometric) as a stretch behind the same protocols. |
| Demo shape | **Scripted 1% TN walkthrough**: `make demo-tn-subset`-scale data, written presenter script covering every capability; repeatable on a laptop. |
| UI scope | **IntegrityAI-inspired reshape**: `ui_reference_code/` mockup as design north star; dedicated design pass, then implementation. |
| Explainability | **LLM narratives + production SHAP**: LLM-generated evidence narratives with template fallback; SHAP wired into the pipeline attributing the linear risk strategy now (the trained GNN later, same seam). |
| Timeline | **One initiative, start now** — sprint 2026-28 theme; demo-ready at core completion; no external deadline. |
| Delivery | **Two-track**: backend stories sequential; UI design+implementation track in parallel; demo gates on both; stretch strictly after demo-ready. |

## 3. Architecture

### 3.1 Backend track

**B1 — GNN live** (analytics.03 + minimal analytics.04 + analytics.05 + analytics.24)

- New `GraphServiceSnapshotSource` implementing the existing
  `GraphSnapshotSourceProtocol` by wrapping `GraphServiceProtocol` — backend
  agnostic (works on Neo4j and in-memory identically), no new `DomainConfig`
  adapter literals. Builds per-KB `GraphSnapshot`s: node feature vectors
  derived from domain-config-declared numeric entity properties plus degree;
  edges carry existing weights.
- Both factory sites (`agent/coordinator.build_graph_snapshot_source`,
  `api/dependencies.get_graph_snapshot_source`) switch to it.
- Bounded compute: config-knobbed node cap with top-degree selection;
  link-prediction pair budget capped (the O(n²) loop must not melt on the TN
  subset). Caps logged when they truncate — no silent partiality.
- Cluster persistence so `GET /analytics/gnn/clusters` serves real
  communities; `cluster_id` + predicted links written back onto graph
  entities via the existing analytics write-back path.
- No new pipeline wiring: `GraphUpdatedEvent → analyze()` already fires and
  stops no-oping the moment the source is real. Stage failure remains
  non-fatal (existing catch/skip semantics).

**B2 — Timeseries into the pipeline** (analytics.06/07)

- Ingest-triggered anomaly-detection stage after peerstats for feeds with
  timeseries-mapped metrics; anomalies persisted; anomaly signals join
  z-scores as monitoring inputs. The workbench chart (already on
  `useTimeseries`) then shows pipeline-produced anomalies.

**B3 — Explainability engine** (analytics.13/14)

- **LLM narratives:** `ExplainabilityService` gains an LLM-backed narrative
  generator using the existing `llm/` protocol clients (prompt over risk
  factors + subgraph). Config-gated; degrades to the current template joiner
  when no LLM is configured or the call fails.
- **Production SHAP:** wire `ShapExplainabilityContextSource` into the
  pipeline attributing `LinearScoringStrategy` over each entity's
  `entity_derived_signals` feature vector; attributions become a
  feature-attribution section in the evidence pack. The stretch trained GNN
  attributes through the same seam later. SHAP failure degrades to
  factor-only packs.

End-to-end data flow after B1–B3 (two ingest-triggered branches that
converge on risk): records ingest → graph upsert → `GraphUpdated` → GNN on a
real snapshot → clusters persisted + written back to entities; in parallel,
records ingest → peerstats z-scores + timeseries anomalies →
`entity_derived_signals` → risk scoring → explainability (SHAP attribution +
LLM narrative) → alerts → UI.

### 3.2 UI track

**U1 — Reshape design pass** (design-only story)

- Mine `ui_reference_code/code-starters/ui/integrity-ai.jsx` +
  `demo/presenter-script.md` for what makes the mockup persuasive; translate
  into a concrete visual direction: typography/spacing/color system,
  per-page layouts (Investigation Workbench, Dashboard, Alert Feed),
  component inventory (exists vs. new).
- Hard constraints: fully domain-config-driven (must render the housing pack
  correctly — labels/entities/pages come from `DomainConfig`); deliverable is
  an approved design doc + annotated mockups, **no code**.

**U2 — Reshape + surfacing implementation**

- Execute U1's design while surfacing every new analytic:
  community-colored cluster overlays + membership panel on `GraphCanvas`;
  predicted links as visually-distinct (dashed) edges with confidence; SHAP
  feature-attribution bars in the evidence viewer; LLM narrative as the
  evidence pack lead; policy items on entity/alert views; pipeline anomaly
  markers on the timeseries chart; Dashboard clusters panel live.
- Playwright e2e per surfaced capability against the full running stack.

### 3.3 Demo

**D1 — Complete demo** (gates on B1–B3 + U1–U2)

- Presenter script at `docs/demo/` walking every capability on the 1% TN
  subset: ingest → graph → clusters → risk → alerts → evidence (SHAP + LLM
  narrative) → policy → RAG chat.
- `make demo-cms` target orchestrating stack-up + data staging + ingest.
- Demo-tuned CMS fraud rule packs (2–3 realistic patterns, e.g. outlier
  billing concentration, referral-ring exposure) expressed in the existing
  policy-rule schema — configured, not coded.
- A full-stack e2e spec mechanically validating the walkthrough path so the
  demo cannot silently rot.

### 3.4 Stretch (strictly after D1 is demo-ready)

**S1 — Trained GNN (BL-030 pulled forward as stretch)**

- PyTorch Geometric behind the existing `GnnService` / snapshot protocols;
  optional `[torch-geometric]` extra; model-artifact persistence
  (analytics.02); config-selected with the heuristic engine remaining the
  default. The demo never depends on S1.

## 4. Out of scope

- Full analytics.04 large-graph hardening beyond the caps B1 needs.
- frontend.15 graph-explorer performance hardening at 100K+ nodes (demo is
  1% TN scale; full-TN-scale graph viz is follow-on).
- New alert rule library (monitoring.13) beyond the 2–3 demo-tuned policy
  packs in D1.
- Multi-KB RAG (BL-028), DR band, load testing — unchanged backlog priority.
- Any new domain pack work (`ui_reference_code/domain-packs/` is reference
  only).

## 5. Quality gates and verification

Unchanged repo standards per story: pyright strict (0 errors), ≥85%
coverage, ruff clean, contract regen + `npm run build` on any
frontend-consumed model change, browser verification for all UI work, live
verification against `make dev` per story, full-stack Playwright e2e for the
demo path. Live verification and Docker steps stay in the controller/main
session (no Docker in subagents).

## 6. Cadence artifacts

- New BL rows (B1–B3, U1–U2, D1, S1) in `docs/project/planning/backlog.md`
  as the sprint 2026-28 committed set; sprint file
  `docs/project/planning/sprints/2026-28.md`.
- Per-story specs + implementation plans under `docs/superpowers/` per the
  established flow; SDD execution.
- Closeout hygiene: correct the stale module-story "Current State" texts the
  survey identified (frontend.01, monitoring.02, frontend.05 at minimum).
