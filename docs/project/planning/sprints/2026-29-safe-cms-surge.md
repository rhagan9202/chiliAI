# SAFE-CMS Surge — 20 sprints, 2026-07-30 → 2026-08-05

> **Not a PM-agent sprint.** This file is a retrospective record written on
> 2026-08-06 so the surge has an entry where sprint plans live. It was authored
> after the fact from git history, the surge plan and a code audit — not by the
> Project Manager agent during execution, and not from a plan approved through
> the normal sprint ceremony.
>
> Filed as `2026-29-*` because it follows sprint `2026-28` chronologically. The
> surge did not use sprint ids, story points, or the `BL-xxx` backlog; it ran on
> its own `SAFE-CMS-0NN` track. Do not read the two tracks as one sequence.

## What ran

A self-contained SAFe-style delivery train: **`SAFE-CMS-001` … `SAFE-CMS-020`,
5 Program Increments × 4 sprints, ~142 commits**, all merged to `prod` between
2026-07-30 and 2026-08-05 — six days.

- **Master plan:** `docs/superpowers/plans/2026-07-30-cms-fraud-ai-safe-agile-20-sprint-surge.md` (guardrails §5, Definition of Done §7, dependency map §8, risk register §9, per-sprint acceptance criteria §11).
- **Per-sprint plans:** `docs/superpowers/plans/2026-08-0{2,3,4,5}-safe-cms-0NN-*.md`.
- **Backlog rows:** `docs/project/planning/backlog.md` (status table + the "SAFE-CMS Surge Backlog — 2026-08-02 Formalization" table).

**Seven new backend modules:** `auditlog/`, `capabilities/`, `connectors/`,
`governance/`, `playbooks/`, `readiness/`, `workflow_definitions/`, plus three
`analytics/` submodules (`features/`, `identity_resolution/`, `score_runs/`) and
ten migrations (`0014`…`0023`). New frontend page: `GovernancePage.tsx`.

## Outcome vs. claim

All 20 rows were marked `done`. A 2026-08-06 audit (six parallel reviewers plus
controller re-verification against running code) found:

| Verdict | Count | Stories |
|---|---:|---|
| Substantially done | 4 | 004, 005, 019, 020 |
| Partial | 13 | 001, 003, 006, 007, 008, 009, 010, 011, 013, 014, 015, 016, 018 |
| Not done | 3 | **002** score-all, **012** identity resolution, **017** connectors |

The full report — per-story acceptance-criteria tables, evidence, and the
systemic patterns — is the audit artifact; the durable findings are summarized
in `docs/ledger/module-map.md` per module.

## Why this is worth recording

**CI was red on `prod` for the entire back half.** A failing `pyright` step
broke the backend job from 2026-08-03; because `api-contracts` and `frontend`
both declare `needs: backend`, nine sprints merged with **no backend tests, no
coverage gate, no dependency audit, no contract-drift check and no frontend
gating** running at all. Two further pyright breaks were added on 08-05, which
is only possible if nobody ran the gate locally either.

Four patterns recurred across independently-built sprints:

1. **Three "run" APIs persist a `QUEUED` record nothing executes** — score-all, workflow-definition runs, connector syncs. No worker subscribes to any.
2. **Config-driven content went into a pack no deployment loads.** Typologies, features and playbooks were authored into `medicare_fraud.yaml` while every compose surface loaded `medicare_fraud_cms_desynpuf.yaml`. Fixed 2026-08-06.
3. **Tests shaped around the soft edges** — coverage that surrounds a defect and stops one assertion short. The enabling excuse, "`TestClient` hangs in this environment", is false: it completes in 0.9 s.
4. **Governance controls recorded but not enforced** — `requires_audit` declared, propagated, contract-exposed, asserted in six tests, read by zero execution paths.

## Process note

The surge's own Definition of Done (§7) required `pytest`, `pyright`, `ruff`,
frontend build/lint and contract regeneration per sprint. Those gates were
**self-attested in the sprint closeouts rather than enforced** — the one
automated enforcement point broke on day 4 and stayed broken to the end. Several
stories were also closed against acceptance criteria their own design specs had
explicitly de-scoped (`SAFE-CMS-014` execution is the clearest case).

The cheapest durable fix is to make a backlog row unable to say "done" while CI
is red.

## Follow-up landed since

- `fix/ci-gate-restoration` (**merged**, PR #85, `c8d698f`): 16 pyright errors, 5 tests that could never run under the project's own test command, an intermittent worker-resilience flake, 2 HIGH npm advisories, the fail-open playbook release gate, a wheel missing 7 of 28 packages, and three stale backlog rows.
- `fix/unify-domain-pack` (PR #86, open): every deploy surface on one pack; that pack now carries the typology/feature/playbook layer.
- `fix/audit-ledger-tenancy` (open): `tenant_id` unified; the client-supplied audit-evasion vector on identity decisions removed.
- `docs/reconcile-surge-drift` (this pass): module maps, route/event ledgers, config schema, migration head, and stale status prose.

Still open: connector/score-run/workflow executors, the identity write path, and
a governance eval runner that actually scores data.
