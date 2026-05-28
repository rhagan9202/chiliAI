# chiliAI Complete Backlog — Design Spec

**Date:** 2026-05-24
**Status:** Executed on 2026-05-24; live backlog now resides under `docs/backlog/**`
**Author:** brainstorming session, chiliAI repo
**Supersedes:** `docs/archive/planning/agent_backlog_05_17.md`, `docs/archive/planning/graph_backlog_05_17.md`, `docs/archive/planning/ingestion_backlog_05_17.md`

---

## 1. Goal

Produce a complete, dependency-ordered backlog covering the full surface from the current chiliAI codebase to the architectural endgame defined in `docs/architecture.md` (including the §14.2 future capabilities table). The backlog is the single live source of truth for what is planned, in-progress, and done across every module, the frontend, infrastructure, and cross-cutting concerns.

This spec defines the artifact shape, the story format, the dependency DAG mechanics, the master index, a small consistency-pass script, the disposition of existing planning material, and the three-wave execution model that produces it.

Out of scope for this spec: doing the work the backlog will catalog. This spec produces the backlog only.

---

## 2. End state targeted by the backlog

The backlog catalogs every story required to take chiliAI from its current state to the **architectural endgame**, defined as everything in `docs/architecture.md` plus the §14.2 future-capabilities table:

- All current-target items: production-grade Medicare exemplar (multi-user, observable, persistent, deployable).
- §14.2 future capabilities: CI/CD deploy & promotion, production IdP profiles + tenant isolation + resource-level authorization, multi-tenancy, configuration UI wizard, model training pipeline, audit log, export/reporting, plugin system.

The backlog does **not** invent scope beyond what `architecture.md` describes. If the user changes architectural intent, `architecture.md` is updated first and backlog stories are reshaped to follow.

---

## 3. Decisions locked

| Decision | Choice | Rationale |
|---|---|---|
| End state | Architectural endgame including §14.2 | Broadest reasonable scope; matches "complete" intent. |
| Relationship to existing material | Full re-derivation from current code | 05_17 backlogs are stale relative to current code; specs and code-review plans become inputs. |
| Structure | Two-tier: master index + per-module/concern files at story depth | Navigable index + implementable stories; supports per-file ownership. |
| Prioritization | Dependency-ordered DAG (Prerequisites/Unblocks edges) | Execution-focused; no release/milestone labels. |
| Story shape | Rich format: ID, Status, Prerequisites, Unblocks, Estimated size, Spec, Done, As-a/I-need/So-that, Current State, Acceptance Criteria, Verification, Code touch points | Self-contained stories; navigable; ready for handoff. |
| Cross-cutting concerns | Dedicated underscore-prefixed files alongside module files | Cleanest separation; each cross-cutting concern has its own ID space. |
| Done items | Stay in file with `Status: done` + `Done:` line | Self-contained DAG; full traceability. |
| Acceptance-criteria checkboxes | Live `[ ]`/`[x]` checked as work lands | Per-AC progress visible without re-running the consistency pass. |
| Location | `docs/backlog/` | New top-level home; 05_17 files archive to `docs/archive/planning/`. |
| Consistency pass | `scripts/backlog_consistency.py` + tests + CI hook | Hand-maintained cross-references rot in days at this scale. |

---

## 4. Artifact tree

```
docs/backlog/
├── README.md                    # master index (DAG, status roll-up, links)
├── _cicd.md                     # cross-cutting: CI/CD pipeline + promotion
├── _infra.md                    # cross-cutting: K8s/Helm/Terraform/IaC
├── _multitenancy.md             # cross-cutting: tenant isolation across data/config/KB
├── _observability.md            # cross-cutting: logging/metrics/tracing/frontend RUM
├── _plugins.md                  # cross-cutting: third-party plugin system
├── _security.md                 # cross-cutting: IdP, secrets, TLS, RBAC hardening, audit log
├── agent.md
├── analytics.md                 # covers timeseries, gnn, risk, explainability, metrics subpkgs
├── api.md
├── config.md                    # incl. config UI wizard
├── database.md
├── embeddings.md
├── events.md
├── frontend.md                  # the entire chili_app SPA
├── graph.md
├── ingestion.md
├── knowledgebases.md
├── llm.md
├── monitoring.md
├── rag.md
├── records.md
├── shared.md
├── storage.md
└── vectorstore.md
```

Total: 25 files (1 README + 6 cross-cutting + 18 module/surface files).

- Underscore-prefixed cross-cutting files sort first for visibility.
- `analytics.md` is a single file covering its sub-packages (they share contracts).
- `frontend.md` is a single file for the SPA, not split per page or concern.
- A temporary working file `docs/backlog/_DRAFT_epics.md` is created in Wave 1 and deleted at the end of Wave 3; it is not part of the final tree.

---

## 5. Story format

Every story uses this exact shape:

```markdown
## Story <module>.<n>: <Short title>

**ID:** <module>.<n>                      # e.g., vectorstore.04 ; cross-cutting uses underscore: _observability.03
**Status:** planned | in-progress | done | dropped  # `dropped` is post-hoc only — never set on a new story
**Prerequisites:** [<id>, <id>]           # other story IDs that must complete first; [] if none
**Unblocks:** [<id>, <id>]                # derived/redundant edge for navigability; [] if none
**Estimated size:** S | M | L | XL        # S<1d, M=1-3d, L=3-7d, XL=7d+ (split if XL)
**Spec:** docs/superpowers/specs/<file>.md  # optional; list multiple if applicable; omit if none
**Done:** <YYYY-MM-DD> · <commit-sha> · <PR#>  # only present when Status=done

**As a** <role>,
**I need** <capability>,
**so that** <outcome>.

### Current State
- <2-6 bullets describing what exists in the code TODAY with file:line refs>
- <or "Nothing exists yet" for greenfield items>

### Acceptance Criteria
- [ ] <testable, observable criterion>
- [ ] <each criterion is a checkbox so progress is visible>
- [ ] <typed: file path, function signature, endpoint, manifest, doc updated, test passes>

### Verification
- <how a reviewer confirms this is done — concrete commands or steps>
- <coverage gate where applicable: "≥ 85% on <package>">

### Code touch points
- <path/to/file.py> (modify | new | delete)
- <path/to/other.py>
```

### Field rules

- **ID is permanent.** Once assigned, never renumber. A dropped story's ID is retired (`Status: dropped` is allowed only as a post-hoc state, never assigned to a fresh story).
- **Prerequisites is the source of truth for the DAG.** `Unblocks` is derived in Wave 3 and rewritten in place — writers leave it as `[]`.
- **Estimated size is human judgment.** Size XL must be split before merge.
- **Spec** links one or more design specs in `docs/superpowers/specs/` if applicable. Omit field if none.
- **Done** is filled when Status flips to done. Provenance only — change details live in git.
- **Acceptance-criteria checkboxes** are live: `[x]` when satisfied. Story Status reflects AC-checkbox state plus verification, not just intent.
  - A story is `in-progress` only when a branch/PR is open.
  - A story is `done` only when **every** AC box is checked AND Verification has been performed.
- **Current State** must cite real code with `file:line` refs (or state "Nothing exists yet" explicitly).

---

## 6. Dependency DAG mechanics

### Edge semantics

`Prerequisites: [a, b]` on story X means a and b must be `Status: done` before X can move from `planned` to `in-progress`. Edges are hard requirements ("cannot proceed without"), not soft "should follow."

### Implicit prereq rule

A story does not declare its own module's protocol/adapter foundation as a prereq — those are foundational and assumed. Only declare genuine dependencies on sibling or cross-file stories.

### Cross-module edges are explicit

If `monitoring.07` requires `events.02`, declare it in `monitoring.07.Prerequisites`. No implicit cross-module edges.

### Cycles are illegal

The consistency pass runs a topological sort (initially during Wave 3, and on every subsequent PR via the CI hook). Cycles are hard errors. Resolutions:
1. Merge two co-dependent stories into one.
2. Split a story to break the cycle.
3. Demote an over-stated edge.

### Unblocks is computed, not hand-maintained

Wave-3 derives the inverse graph: for every edge `X.Prerequisites ⊇ {Y}`, append `X` to `Y.Unblocks`. The script rewrites all `Unblocks:` lines in place. Writers do not maintain it.

### Critical path

Wave-3 computes the longest path through the DAG by weighted size: S=1, M=2, L=5, XL=10. The master index renders the critical path so reviewers see the minimum chain that must be funded to reach endgame.

### Ready set

A story is **ready** when `Status=planned` AND every `Prerequisites` entry has `Status=done`. The master index renders the Ready set as a flat list — that's what an executor can pick up today without re-reading the DAG.

### Done is permanent

A done story never reopens. If work needs redoing, create a new story with the original as a Prerequisite. Keeps the DAG monotonic.

### Maintenance contract

When code lands that closes a story:
1. The PR/commit flips `Status: planned → done`, fills `Done:`, checks the AC boxes.
2. If the PR creates follow-up work, add a new story to the appropriate file in the same commit. Don't reopen the done story.
3. The consistency pass (`scripts/backlog_consistency.py --check`) runs in CI on any PR that touches `docs/backlog/`.

---

## 7. Master index — `docs/backlog/README.md`

The README has hand-curated sections plus three auto-generated sections (between marker comments) regenerated by the consistency pass.

### Structure

```markdown
# chiliAI Backlog

> Single source of truth for what's planned, in-progress, and done across the platform.
> See [docs/architecture.md](../architecture.md) for the target architecture this backlog drives toward.

## How to read this
- Legend (Status, Estimated size, ID format, prereq semantics)
- Stories live in `docs/backlog/<module>.md` and `docs/backlog/_<concern>.md`.
- Design specs in `docs/superpowers/specs/` are linked from individual stories via `Spec:`.

## Status roll-up
<!-- BEGIN: status-rollup -->
| File | Planned | In-progress | Done | Total | % done |
| ... auto-generated ... |
<!-- END: status-rollup -->

## Ready set (work that can start today)
<!-- BEGIN: ready-set -->
- [vectorstore.04] Qdrant snapshot scheduling — size M — prereqs done
- ... auto-generated; capped at top 30, "…N more" line if longer ...
<!-- END: ready-set -->

## Critical path
<!-- BEGIN: critical-path -->
> Longest dependency chain by weighted size (S=1, M=2, L=5, XL=10).
1. shared.02 (S=1) → events.03 (M=2) → ... total weight: NN
<!-- END: critical-path -->

## Cross-cutting epics
- [_observability.md](_observability.md) — logging, metrics, tracing, frontend RUM
- [_security.md](_security.md) — IdP, secrets, TLS, RBAC hardening, audit log
- [_multitenancy.md](_multitenancy.md) — tenant scoping across data/config/KB
- [_infra.md](_infra.md) — K8s manifests, Helm hardening, Terraform/Pulumi
- [_cicd.md](_cicd.md) — deploy/promotion, release workflows
- [_plugins.md](_plugins.md) — third-party plugin SPI

## Module backlogs
- [agent.md](agent.md) — workflow coordinator, run lifecycle, DLQ ops
- [analytics.md](analytics.md) — timeseries, gnn, risk, explainability, metrics
- ... (one bullet per module, one-line scope summary) ...

## Archived / superseded
- agent_backlog_05_17.md → archive/planning/ — superseded by [agent.md](agent.md) on YYYY-MM-DD
- graph_backlog_05_17.md → archive/planning/ — superseded by [graph.md](graph.md) on YYYY-MM-DD
- ingestion_backlog_05_17.md → archive/planning/ — superseded by [ingestion.md](ingestion.md) on YYYY-MM-DD

## Design specs (referenced from stories)
- List of files in `docs/superpowers/specs/` paired with the IDs of backlog stories that link to them via `Spec:`. Hand-maintained.

## Maintenance
- Adding a story: pick the file, allocate next free `<file>.<n>` ID, fill the rich format, run the consistency pass.
- Closing a story: flip Status to done, fill Done line, check AC boxes, run the consistency pass.
- Consistency-pass script lives at `scripts/backlog_consistency.py`.
```

Only the three `<!-- BEGIN: ... --> ... <!-- END: ... -->` blocks are auto-generated. All other sections are hand-curated.

---

## 8. Consistency-pass script — `scripts/backlog_consistency.py`

A small Python script using only stdlib + already-present deps. Not an installed CLI; invoked as `python scripts/backlog_consistency.py`.

### Inputs

Every `*.md` in `docs/backlog/` except `README.md`.

### Parser

- Stories start with `## Story <id>:`.
- Field block follows immediately, format `**Key:** value`. List-valued fields use `[a, b]`.
- Field block ends at first `### Current State` heading.
- Acceptance-criteria boxes are parsed (count `[x]` vs `[ ]` for per-story progress numbers).
- Malformed stories are hard errors, not warnings.

### Validations (each is a hard error unless noted)

- Duplicate ID across all files.
- `Prerequisites` ID that doesn't resolve to any known story.
- Cycle in the Prerequisites DAG (reports the cycle path).
- `Status: done` story missing the `Done:` line.
- `Status: done` story with any unchecked AC box.
- `Status: in-progress` story whose Prerequisites contain any non-done story.
- `Estimated size: XL` — warning by default; error under `--strict` (so XL stories can be added then split before merge).
- `Unblocks:` line disagreeing with derived inverse of Prerequisites — script auto-rewrites in place (not an error); reports what it changed.

### Generated outputs (in-place rewrite of `README.md`)

- `<!-- BEGIN: status-rollup -->` … `<!-- END: status-rollup -->`
- `<!-- BEGIN: ready-set -->` … `<!-- END: ready-set -->` — top 30, sorted by size then ID
- `<!-- BEGIN: critical-path -->` … `<!-- END: critical-path -->` — longest weighted path

### Side effects

- In-place rewrite of every story's `Unblocks:` line to match derived inverse of Prerequisites.
- Script is **not read-only by default**.
- `--check` flag makes it read-only and exits non-zero on any drift (for CI).

### Excluded

No Mermaid DAG diagram generation.

### Tests

`tests/scripts/test_backlog_consistency.py` covers:
- Round-trip on fixture story sets.
- Each error class.
- In-place rewrite of Unblocks.
- `--check` flag drift detection.

Targets ≥ 85% coverage per the repo's gate.

### CI hook

New step added to the existing GitHub Actions workflow:

```yaml
- name: Backlog consistency
  run: python scripts/backlog_consistency.py --check
  if: contains(github.event.pull_request.changed_files, 'docs/backlog/')
```

Fails the PR on validation errors or on Unblocks drift. No-op when no backlog files changed.

---

## 9. Disposition of existing material

| Artifact | Disposition |
|---|---|
| `docs/agent_backlog_05_17.md` | Move to `docs/archive/planning/` in Wave 3 step 5 (batched with the other two 05_17 archives). Stories re-derived against current code; IDs do not carry over. |
| `docs/graph_backlog_05_17.md` | Same — archived in Wave 3 step 5. |
| `docs/ingestion_backlog_05_17.md` | Same — archived in Wave 3 step 5. |
| `docs/superpowers/specs/*.md` (10 design specs) | Stay in place. Linked from stories via `Spec:`. |
| `docs/planning/code_review_2026-05-24.md` + `code-review-2026-05-24/` subdir | Consumed into stories, then archived as `docs/archive/planning/2026-05-24-code-review/`. |
| `docs/planning/p3_watch_items_2026-05-12.md` | Consumed into stories, then archived. |
| `docs/ledger/*` | Stay in place. Reference docs, not backlog. |
| `docs/wiki/*` | Stay in place. Reference docs, not backlog. |
| `docs/onboarding.md`, `docs/security_checklist.md`, `docs/system_architecture_diagram.md` | Stay in place. Reference docs. |
| `docs/architecture.md` | Stay in place as source of truth. Stories cite it; stories don't redefine architectural decisions. |
| Root `README.md` | Add pointer to `docs/backlog/README.md` in Documentation table. Update Current State note to reference the backlog as live status. |
| Root `CLAUDE.md` and `.github/copilot-instructions.md` | Update references from the three 05_17 backlogs to `docs/backlog/README.md`. |
| `backend/README.md`, `chili_app/README.md` | Update Current State sections to cite `docs/backlog/<module>.md` for known gaps. |

Notes:

- Specs are not stories. They describe a designed feature; backlog stories are the implementation increments. If a spec's design has drifted from code, add a story to revise the spec rather than silently superseding it.
- The 05_17 backlogs are archived even if some stories aren't yet done. The new backlog is re-derived from current code; what was P0 in May may now be done, deprioritized, or split. No ID mapping; archived files are historical context only.

---

## 10. Execution waves

### Wave 1 — Epic shaping (sequential, by me)

For each of the 24 final files (25 in the tree minus `README.md`, which is produced in Wave 3), read the relevant module/concern code and produce an **epic list**: titles + 1-line "what gap" notes. No story bodies. Output: a single working document `docs/backlog/_DRAFT_epics.md` containing:

- Per-file epic lists (titles only)
- Cross-cutting epics with their per-module fan-out
- Provisional dependency edges between epics
- Open questions for any module where current code state is ambiguous

**Checkpoint:** user reviews and reshapes the draft. No story bodies have been written, so reshaping is cheap. **Hard approval gate before Wave 2.**

### Wave 2 — Story expansion (parallel subagents)

Once epics are approved, dispatch one subagent per file in parallel. Each subagent receives:

- The full approved epic list across all files (legal ID space).
- The rich-format story template from §5.
- The strict field rules from §5.
- A pointer to the relevant module's code path.

Each subagent:

- Expands its file's epics into full rich-format stories.
- Cites accurate prereq edges using only IDs in the approved epic list.
- Provides real `file:line` refs in Current State.
- Provides real acceptance criteria, real verification steps, real code touch points.
- Leaves `Unblocks:` as `[]` (derived in Wave 3).
- Self-checks story format before returning.

Returned content is committed file-by-file as it lands.

**Risks and mitigations:**

- Story-format drift → template included literally in subagent prompts; self-check before return.
- Fabricated prereq IDs → only IDs in the approved epic list are legal; consistency pass catches any not in space.
- Stale code reads → all subagents dispatched at one HEAD; resync if work lands mid-wave.

### Wave 3 — Consistency, master index, archival (sequential, by me)

1. Implement `scripts/backlog_consistency.py` per §8 with its tests.
2. Run it against Wave-2 output. Fix validation errors by amending files. Loop until clean.
3. Hand-write the curated sections of `docs/backlog/README.md` (legend, file links, archived list, maintenance section).
4. Run the consistency pass once more to fill the auto-generated sections.
5. Move the three `*_backlog_05_17.md` files to `docs/archive/planning/`.
6. Verify `docs/planning/code_review_2026-05-24.md` and `p3_watch_items_2026-05-12.md` items are represented as stories; then archive them.
7. Update root `README.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `backend/README.md`, `chili_app/README.md` per §9.
8. Add the CI hook per §8.
9. Final commit with README and CI changes.

### Deliverables

- [ ] `docs/backlog/README.md`
- [ ] `docs/backlog/<module>.md` × 18 (agent, analytics, api, config, database, embeddings, events, frontend, graph, ingestion, knowledgebases, llm, monitoring, rag, records, shared, storage, vectorstore)
- [ ] `docs/backlog/_<concern>.md` × 6
- [ ] `scripts/backlog_consistency.py` + `tests/scripts/test_backlog_consistency.py`
- [ ] CI hook in existing GitHub Actions workflow
- [ ] 3 × archived `*_backlog_05_17.md` in `docs/archive/planning/`
- [ ] 2 × archived planning artifacts (`2026-05-24-code-review/`, `p3_watch_items_2026-05-12.md`) in `docs/archive/planning/`
- [ ] Updates to root `README.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `backend/README.md`, `chili_app/README.md`

---

## 11. Scope explicitly excluded

- Executing the work the stories will catalog. This spec produces the backlog only.
- Splitting `analytics.md` per sub-package.
- Splitting `frontend.md` per page or concern.
- Generating a Mermaid DAG diagram.
- Touching `docs/ledger/` or `docs/wiki/`.
- Migrating story IDs from the 05_17 backlogs.
- Any ranking beyond Status/Size/Prereqs (no points, no WSJF, no velocity).
- Release/milestone labels (v1.0/v1.1/v2.0) — dependency-ordered only.

---

## 12. Open questions

None. All scoping and shape decisions are locked in §3.

---

## 13. Next steps

After this spec is approved by the user:

1. Hand off to the `superpowers:writing-plans` skill to produce a step-by-step implementation plan.
2. The plan will turn each Wave (1, 2, 3) into ordered tasks with concrete commands, file-touch lists, and checkpoint criteria.
3. The plan executes; this spec is the design contract it executes against.
