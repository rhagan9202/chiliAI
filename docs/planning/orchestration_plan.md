# chiliAI — Story Implementation Orchestration Plan

> **Created**: 2026-04-26
> **Scope**: 77 remaining stories across E4–E10 (E1, E2, E3, E4-S01 already complete)
> **Strategy**: Wave-based execution. Parallel subagents for file-independent stories within each wave. Validate (pytest + pyright + ruff) and commit at every wave boundary before advancing.

## Operating Principles

1. **Dependency-respecting waves.** Cross-wave deps must clear before the next wave starts. Within a wave, run parallel agents only when their target files do not overlap.
2. **One agent per story OR per coherent chain.** Stories that touch the same files (e.g., E4-S02..S05 in `coordinator.py`) go to one sequential agent. Stories that touch disjoint files run in parallel.
3. **Subagents read `docs/planning/subagent_brief.md`.** That brief encodes the conventions every implementer must follow (architecture rules, patterns, test/coverage expectations) so they don't need to be re-derived per task.
4. **Validate at every wave boundary** — `pytest --cov`, `pyright`, `ruff check`. No advance until green.
5. **Commit at every wave boundary** with the conventional message format used by recent commits ("feat(<module>): …" / "Implement <story> …").
6. **Stop and confirm** if a wave reveals an architectural ambiguity that the story prompt does not resolve.

## Wave Plan

### Wave 1 — Pipeline Completion (E4 remaining)

Closes the Tier-1 production blocker (config-driven wiring) and finishes Flow A.

| Order | Story | Agent | Notes |
|-------|-------|-------|-------|
| 1 (seq) | **E4-S08** Config-driven adapter wiring | A1 | Touches `api/dependencies.py` + `agent/coordinator.py`. Must land first — every later coordinator change builds on it. |
| 2 (seq) | **E4-S02** Wire vector indexing → **E4-S03** kb.ready → **E4-S04** DLQ → **E4-S05** retry/backoff | A2 | One agent, sequential within. Same file (`coordinator.py`). |
| 2 (par) | **E4-S06** Graceful shutdown | A3 | Disjoint changes (signal handling). |
| 2 (par) | **E4-S07** Worker health endpoint | A4 | New file in `agent/`. |

**Validation gate**: All E4 tests green; `pytest tests/agent tests/events tests/api --cov`; `pyright agent api events`.

### Wave 2 — API Routers (E5)

6 missing routers + register them.

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (par) | **E5-S01, S02** alerts router | B1 | New file `api/routers/alerts.py`. |
| 1 (par) | **E5-S03, S04** investigation router | B2 | New file `api/routers/investigation.py`. |
| 1 (par) | **E5-S05, S06** RAG router (stub backend) | B3 | New file `api/routers/rag.py`. |
| 1 (par) | **E5-S07, S08** WebSocket router | B4 | New file `api/routers/ws.py`. |
| 1 (par) | **E5-S09, S10** analytics router | B5 | New file `api/routers/analytics.py`. |
| 1 (par) | **E5-S11, S12, S13** knowledgebases router extension | B6 | Extends existing `api/routers/knowledgebases.py`. |
| 2 (seq) | **E5-S14** Register routers in app factory | B7 | Modifies `api/app.py` after all routers exist. |

**Validation gate**: `pytest tests/api --cov`; OpenAPI schema reachable on `/openapi.json`.

### Wave 3 — RAG Pipeline (E6)

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (par) | **E6-S01** QueryEmbedder + **E6-S02** ContextRetriever | C1 | Reuses embeddings + vectorstore protocols. |
| 1 (par) | **E6-S03** GraphContextExpander + **E6-S04** AnswerGenerator | C2 | Reuses graph + LLM protocols. |
| 2 (par) | **E6-S05** Domain prompts | C3 | Depends on E6-S04. |
| 2 (par) | **E6-S06** Streaming + **E6-S07** Citations | C4 | Depends on E6-S04. |
| 3 (seq) | **E6-S08** Coverage ≥85% | C5 | Final. |

**Validation gate**: `pytest tests/rag --cov-report=term-missing` ≥85%.

### Wave 4 — Analytics (E7)

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (par) | **E7-S01..S03** timeseries | D1 | One module. |
| 1 (par) | **E7-S04..S05** GNN | D2 | One module. |
| 1 (par) | **E7-S06..S07** risk scoring | D3 | One module. |
| 1 (par) | **E7-S08..S09** explainability | D4 | One module. |
| 2 (seq) | **E7-S10** wire to coordinator → **E7-S11** self-reinforcing loop → **E7-S12** coverage | D5 | After D1–D4 done. |

**Note**: GNN and timeseries may need simpler heuristic implementations if full ML libs are out of scope. Stories prefer scikit-learn / NetworkX over heavyweight torch-geometric.

### Wave 5 — Monitoring (E8)

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (par) | **E8-S01..S04** windowing, dedup, suppression, rate-limit | E1 | All compose into alerting service. |
| 1 (par) | **E8-S05..S06** lifecycle, grouping | E2 | |
| 2 (seq) | **E8-S07** consumer → **E8-S08** coverage | E3 | |

### Wave 6 — Frontend (E9)

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (seq) | **E9-S01..S03** shell, config provider, state mgmt | F1 | Foundation. |
| 2 (par) | **E9-S04** Dashboard, **E9-S05** KB Manager, **E9-S06** Alert Feed | F2/F3/F4 | Pages. |
| 2 (par) | **E9-S07** Investigation, **E9-S08** RAG Chat, **E9-S09** Config Editor | F5/F6/F7 | Pages. |
| 3 (par) | **E9-S10** graph viz, **E9-S11** WebSocket, **E9-S12** notifications | F8/F9/F10 | |
| 4 (seq) | **E9-S13** theming/polish | F11 | |

### Wave 7 — Quality, Security, Ops (E10)

| Order | Stories | Agent | Notes |
|-------|---------|-------|-------|
| 1 (par) | **E10-S01** CI, **E10-S02..S05** coverage closure | G1 | |
| 1 (par) | **E10-S06** auth, **E10-S07** RBAC | G2 | |
| 1 (par) | **E10-S08** structlog, **E10-S09** Prometheus, **E10-S14** OTel | G3 | |
| 1 (par) | **E10-S10** input validation hardening | G4 | |
| 1 (par) | **E10-S11** K8s, **E10-S12** TLS/secrets | G5 | |
| 2 (seq) | **E10-S13** E2E, **E10-S15** security audit | G6 | |

## Pre-flight: Already Complete (do not re-do)

E1-S01 to E1-S10 · E2-S01 to E2-S06 · E3-S01 to E3-S08 · E4-S01

(Working tree contains uncommitted output from E3-S03..S08 and E4-S01. Commit these as the first wave-boundary commit before starting Wave 1.)

## Stop Conditions

- A wave's validation gate fails twice → halt and surface to user.
- An agent reports a missing dependency or ambiguous spec → fix story prompt or escalate.
- Coverage falls below 85% on any module touched in the wave → keep the wave open.
