# Complete Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Current status:** Executed on 2026-05-24. The live outputs are `docs/backlog/**`, `docs/backlog/README.md`, `scripts/backlog_consistency.py`, and the archived superseded planning files under `docs/archive/planning/`. The unchecked task boxes below are preserved as the original execution plan, not current open work.

**Goal:** Re-derive chiliAI's complete dependency-ordered backlog from current code state up to the architectural endgame (architecture.md + §14.2 future capabilities), per the design spec at `docs/superpowers/specs/2026-05-24-complete-backlog-design.md`.

**Architecture:** Four execution waves. Wave 0 prepares the working branch (this worktree is currently 247 commits behind `prod`; the audit must run against current code). Wave 1 produces an epic list per file (24 files) and pauses at a hard user-approval gate. Wave 2 dispatches 24 parallel subagents to expand approved epics into full rich-format stories. Wave 3 implements the consistency-pass script via TDD, writes the master index, runs the script, adds the CI hook, archives superseded material, and updates root/module READMEs.

**Tech Stack:** Markdown for backlog files; Python 3.12 stdlib only for `scripts/backlog_consistency.py`; pytest for the script's tests; GitHub Actions for the CI hook.

---

## Spec reference

This plan executes `docs/superpowers/specs/2026-05-24-complete-backlog-design.md`. Every plan task implements one or more spec sections:

| Spec section | Plan tasks |
|---|---|
| §4 Artifact tree | Tasks 1.0, 2.x, 3.14, 3.17–3.18 |
| §5 Story format | Tasks 2.1–2.6 (subagent prompts include the format verbatim) |
| §6 DAG mechanics | Tasks 3.3–3.13 (script validators) |
| §7 Master index | Task 3.14 |
| §8 Consistency script | Tasks 3.1–3.13, 3.16 |
| §9 Disposition of existing material | Tasks 3.17–3.22 |
| §10 Wave 1 | Tasks 1.0–1.8 |
| §10 Wave 2 | Tasks 2.0–2.8 |
| §10 Wave 3 | Tasks 3.0–3.24 |

---

## File structure

Files created or modified by this plan:

| Path | Created by | Disposition |
|---|---|---|
| `docs/backlog/README.md` | Task 3.14 | Permanent — master index |
| `docs/backlog/_cicd.md` | Task 2.1 | Permanent |
| `docs/backlog/_infra.md` | Task 2.1 | Permanent |
| `docs/backlog/_multitenancy.md` | Task 2.1 | Permanent |
| `docs/backlog/_observability.md` | Task 2.1 | Permanent |
| `docs/backlog/_plugins.md` | Task 2.1 | Permanent |
| `docs/backlog/_security.md` | Task 2.1 | Permanent |
| `docs/backlog/agent.md` … `docs/backlog/vectorstore.md` (18 module files) | Tasks 2.2–2.6 | Permanent |
| `docs/backlog/_epics_drafts/*.md` (24 working files) | Tasks 1.1–1.2 | Deleted by Task 2.8 |
| `docs/backlog/_DRAFT_epics.md` | Task 1.3 | Deleted by Task 2.8 |
| `docs/backlog/_LOCKED_id_space.md` | Task 2.0 | Deleted by Task 2.8 |
| `scripts/backlog_consistency.py` | Tasks 3.1–3.13 | Permanent — used by CI |
| `tests/scripts/test_backlog_consistency.py` | Tasks 3.1–3.13 | Permanent — used by CI |
| `.github/workflows/ci.yml` | Task 3.16 | Modified — adds backlog-consistency step |
| `docs/archive/planning/agent_backlog_05_17.md` | Task 3.17 | Moved from `docs/` |
| `docs/archive/planning/graph_backlog_05_17.md` | Task 3.17 | Moved from `docs/` |
| `docs/archive/planning/ingestion_backlog_05_17.md` | Task 3.17 | Moved from `docs/` |
| `docs/archive/planning/2026-05-24-code-review/` | Task 3.18 | Moved from `docs/planning/` |
| `docs/archive/planning/p3_watch_items_2026-05-12.md` | Task 3.18 | Moved from `docs/planning/` |
| `README.md` | Task 3.19 | Modified — pointer to backlog |
| `CLAUDE.md` | Task 3.20 | Modified — pointer to backlog |
| `.github/copilot-instructions.md` | Task 3.21 | Modified — pointer to backlog |
| `backend/README.md` | Task 3.22 | Modified — Current State cites backlog |
| `chili_app/README.md` | Task 3.22 | Modified — Current State cites backlog |

---

## Wave 0 — Working branch setup

### Task 0.0: Reconcile worktree branch with `prod`

**Files:**
- No files created. Pure git operation.

**Why this task exists:** The current worktree (`worktree-backlog-design-spec`) was branched from `origin/main` and is 247 commits behind `origin/prod`. The audit cannot run against `main` — the spec, the `database/`/`knowledgebases/`/`records/` modules, the 05_17 backlogs, and 9 of 10 design specs only exist on `prod`. We must bring `prod`'s state into the working branch before proceeding.

**Sub-steps:**

- [ ] **Step 1: Confirm the gap.** Run:
  ```bash
  git log --oneline origin/main..origin/prod | wc -l
  ```
  Expected: a non-trivial number (~247 at plan-write time). If 0, this task is a no-op; skip to Task 1.0.

- [ ] **Step 2: Ask the user to choose merge vs. rebase.** Present the choice:
  - **Merge `origin/prod` into the worktree branch (recommended):** preserves the design-spec commit, keeps history linear from prod's perspective. Risk: a merge commit appears.
  - **Rebase the worktree branch onto `origin/prod`:** rewrites the worktree branch's design-spec commit on top of prod's HEAD. Risk: the prior commit hash changes.
  Default to merge.

- [ ] **Step 3: Execute the chosen operation.** For merge:
  ```bash
  git fetch origin
  git merge origin/prod --no-edit
  ```
  For rebase:
  ```bash
  git fetch origin
  git rebase origin/prod
  ```
  Expected: clean merge/rebase. The only commit on this branch before this step is the design spec at `docs/superpowers/specs/2026-05-24-complete-backlog-design.md`, which lives in a path no other commit touches — conflict risk is near zero.

- [ ] **Step 4: Verify the working tree.** Confirm the modules and files the plan needs are present:
  ```bash
  ls docs/agent_backlog_05_17.md docs/graph_backlog_05_17.md docs/ingestion_backlog_05_17.md
  ls backend/database backend/knowledgebases backend/records
  ls docs/planning/code_review_2026-05-24.md docs/planning/code-review-2026-05-24/
  ls docs/superpowers/specs/ | wc -l    # expect ≥ 11
  ```
  Expected: all paths exist; spec count ≥ 11. If any are missing, stop and report — the plan's assumptions about disposition are broken.

- [ ] **Step 5: No commit.** Merge produces its own commit; rebase rewrites. Don't add anything extra.

---

## Wave 1 — Epic shaping

### Task 1.0: Bootstrap `docs/backlog/` skeleton

**Files:**
- Create: `docs/backlog/_epics_drafts/.gitkeep`

**Sub-steps:**

- [ ] **Step 1:** Create the directory and placeholder:
  ```bash
  mkdir -p docs/backlog/_epics_drafts
  touch docs/backlog/_epics_drafts/.gitkeep
  ```

- [ ] **Step 2:** Commit:
  ```bash
  git add docs/backlog/_epics_drafts/.gitkeep
  git commit -m "chore(backlog): bootstrap docs/backlog/ working dir"
  ```

### Task 1.1: Audit the 6 cross-cutting concerns (parallel dispatch)

**Files:**
- Create: `docs/backlog/_epics_drafts/_observability.md`
- Create: `docs/backlog/_epics_drafts/_security.md`
- Create: `docs/backlog/_epics_drafts/_multitenancy.md`
- Create: `docs/backlog/_epics_drafts/_infra.md`
- Create: `docs/backlog/_epics_drafts/_cicd.md`
- Create: `docs/backlog/_epics_drafts/_plugins.md`

**Subagent prompt template** (substitute the per-concern values from the table below):

> You are auditing the chiliAI codebase to identify backlog epics for the **{CONCERN}** cross-cutting concern. The repo is at the current working directory.
>
> **Read first:**
> - The design spec: `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` (especially §2, §5, §6) — this is the format and constraints contract.
> - `docs/architecture.md` sections: **{ARCH_SECTIONS}**.
> - Existing inputs: **{INPUTS}**.
> - Current relevant code paths: **{CODE_PATHS}**.
>
> **Your output:** a markdown fragment in this exact shape, no extra prose:
>
> ```markdown
> ## File: docs/backlog/{FILE}.md
>
> **Scope:** <one-line scope summary for this concern>
>
> ### Epics
> 1. <Epic title> — <1-line gap statement; cite file:line if relevant>
> 2. <Epic title> — <1-line gap statement>
> …  (target 5–12 epics; fewer if the concern is truly small; more if genuinely needed)
>
> ### Provisional cross-file edges
> - <Epic title from this file> depends on <Epic title in {other_file}.md> — <why>
> - …  (omit section if no edges)
>
> ### Open questions
> - <ambiguity in current code that the user should resolve before Wave 2>
> - …  (omit section if no open questions)
> ```
>
> **Constraints:**
> - Every epic must be tied to a real gap between current code and the architectural endgame. Do not invent work the spec/architecture does not motivate.
> - If a concern is greenfield (no current code), say so explicitly in the Scope line and propose foundation epics (e.g., "Define the {CONCERN} surface").
> - Do not write story bodies. One line per epic. Wave 2 expands them.
> - Cross-file edges are provisional; Wave 2 subagents will refine them.
>
> **Self-check before returning:**
> - Every epic has a 1-line gap statement.
> - Epic titles are imperative phrases ("Add tenant-scoped KB queries"), not nouns ("Tenant-scoped KB queries").
> - No epic restates the spec/architecture without proposing concrete work.

**Per-concern dispatch table:**

| Concern | `{CONCERN}` | `{FILE}` | `{ARCH_SECTIONS}` | `{INPUTS}` | `{CODE_PATHS}` |
|---|---|---|---|---|---|
| Observability | Observability | _observability | §11, §14.2 | `docs/onboarding.md`, `docs/security_checklist.md` | `backend/**/*.py` (grep for `logging`, `metrics`, `prometheus`, `OTEL`), `chili_app/src/**/*.ts` (grep for RUM/error tracking) |
| Security | Security & RBAC | _security | §12, §14.2 | `docs/security_checklist.md`, `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md` | `backend/api/auth/`, `backend/api/middleware/`, any `*rbac*` files, `backend/config/` for secret handling |
| Multi-tenancy | Multi-tenancy | _multitenancy | §12.3, §14.2 | none | `backend/knowledgebases/`, `backend/api/dependencies.py`, `backend/agent/coordinator.py` — search for tenant/org scoping (likely absent) |
| Infrastructure | Infrastructure & IaC | _infra | §10, §14.2 | none | `infra/`, `docker-compose*.yaml`, `backend/Dockerfile`, `chili_app/Dockerfile` if present, `Makefile` |
| CI/CD | CI/CD pipeline | _cicd | §10, §14.2 | none | `.github/workflows/`, `scripts/`, `Makefile` |
| Plugins | Plugin system | _plugins | §14.2 (Plugin system row) | none | (likely greenfield — search for plugin/extension patterns) |

**Sub-steps:**

- [ ] **Step 1: Dispatch 6 subagents in parallel.** Send one message with 6 Agent tool calls (subagent_type: `general-purpose`), each instantiating the template with one row of the table. Each returns its markdown fragment.

- [ ] **Step 2: Review each returned fragment.** Verify the self-check criteria (1-line gap per epic, imperative titles, real code references, endgame coverage). Re-dispatch any that fail.

- [ ] **Step 3: Write each fragment to `docs/backlog/_epics_drafts/{file}.md`** (exact filenames from the table's `{FILE}` column with `.md` appended).

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/_epics_drafts/_*.md
  git commit -m "docs(backlog): wave 1 cross-cutting epic audits"
  ```

### Task 1.2: Audit the 18 module/surface files (parallel dispatch in batches)

**Files:**
- Create: `docs/backlog/_epics_drafts/agent.md`
- Create: `docs/backlog/_epics_drafts/analytics.md`
- Create: `docs/backlog/_epics_drafts/api.md`
- Create: `docs/backlog/_epics_drafts/config.md`
- Create: `docs/backlog/_epics_drafts/database.md`
- Create: `docs/backlog/_epics_drafts/embeddings.md`
- Create: `docs/backlog/_epics_drafts/events.md`
- Create: `docs/backlog/_epics_drafts/frontend.md`
- Create: `docs/backlog/_epics_drafts/graph.md`
- Create: `docs/backlog/_epics_drafts/ingestion.md`
- Create: `docs/backlog/_epics_drafts/knowledgebases.md`
- Create: `docs/backlog/_epics_drafts/llm.md`
- Create: `docs/backlog/_epics_drafts/monitoring.md`
- Create: `docs/backlog/_epics_drafts/rag.md`
- Create: `docs/backlog/_epics_drafts/records.md`
- Create: `docs/backlog/_epics_drafts/shared.md`
- Create: `docs/backlog/_epics_drafts/storage.md`
- Create: `docs/backlog/_epics_drafts/vectorstore.md`

**Subagent prompt template** (same shape as Task 1.1, substitute per-module values):

> You are auditing the chiliAI codebase to identify backlog epics for the **{MODULE}** module. The repo is at the current working directory.
>
> **Read first:**
> - The design spec: `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` (§2, §5, §6).
> - `docs/architecture.md` sections: **{ARCH_SECTIONS}**.
> - Existing 05_17 backlog (if any): **{OLD_BACKLOG}**. Treat this as historical context only; do not carry over story IDs.
> - Existing design specs touching this module: **{SPECS}**.
> - Current module code: **{CODE_PATH}**.
> - Relevant module README(s): **{READMES}**.
>
> **Your output:** the same markdown fragment shape as Task 1.1, with `## File: docs/backlog/{FILE}.md` as the heading.
>
> **Constraints:**
> - Read the actual code at `{CODE_PATH}` before writing epics. Cite `file:line` in gap statements.
> - Carry forward the *intent* of relevant 05_17 stories that aren't yet done in code, but rewrite as new epics — the new backlog re-derives, doesn't migrate IDs.
> - If a story from the 05_17 backlog is now done in code, do not include it as an epic.
> - Cover the architectural endgame including §14.2 future capabilities that touch this module.
> - 5–15 epics per module. If a module needs more, split into provisional groups; the user will reshape at the gate.
>
> **Self-check before returning:** same criteria as Task 1.1.

**Per-module dispatch table:**

| Module | `{MODULE}` | `{FILE}` | `{ARCH_SECTIONS}` | `{OLD_BACKLOG}` | `{SPECS}` | `{CODE_PATH}` | `{READMES}` |
|---|---|---|---|---|---|---|---|
| agent | Agent / coordinator | agent | §5.2 agent, §6.x worker flows | `docs/agent_backlog_05_17.md` | none | `backend/agent/` | `backend/agent/README.md` if exists, `backend/README.md` |
| analytics | Analytics (timeseries/gnn/risk/explainability/metrics) | analytics | §5.2 analytics, §6.2 | none | none | `backend/analytics/` | `backend/analytics/README.md` if exists, `backend/README.md` |
| api | FastAPI gateway | api | §5.2 api, §4 container | none | none | `backend/api/` | `backend/api/README.md` if exists, `backend/README.md` |
| config | Domain configuration | config | §9, §14.2 (Configuration UI wizard) | none | none | `backend/config/` | `backend/config/README.md` if exists |
| database | Postgres + Timescale + Alembic | database | §5.2 database, §6.4 Plan C | none | `docs/superpowers/specs/2026-05-14-backend-persistence-design.md` | `backend/database/` | `backend/database/README.md` if exists |
| embeddings | Embeddings | embeddings | §5.2 embeddings | none | `docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md` | `backend/embeddings/` | `backend/embeddings/README.md` if exists |
| events | Redis Streams events | events | §5.2 events, §4 communication | none | none | `backend/events/` | `backend/events/README.md` if exists |
| frontend | React analyst workbench | frontend | §8 (all subsections), §14.2 (Config UI wizard) | none | `docs/superpowers/specs/2026-05-17-ingestion-studio-ui-ux-design.md`, `docs/superpowers/specs/2026-05-21-kb-contextual-entry-points-design.md` | `chili_app/src/` | `chili_app/README.md` |
| graph | Graph DB | graph | §5.2 graph, §6.x | `docs/graph_backlog_05_17.md` | `docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md`, `docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md` | `backend/graph/` | `backend/graph/README.md` if exists |
| ingestion | Document ingestion | ingestion | §5.2 ingestion, §6.1, §6.5 | `docs/ingestion_backlog_05_17.md` | `docs/superpowers/specs/2026-05-21-ingestion-prerequisite-vs-error-design.md`, `docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md` | `backend/ingestion/` | `backend/ingestion/README.md` if exists |
| knowledgebases | KB metadata | knowledgebases | §7, §5.2 knowledgebases | none | none | `backend/knowledgebases/` | `backend/knowledgebases/README.md` if exists |
| llm | LLM clients | llm | §5.2 llm | none | none | `backend/llm/` | `backend/llm/README.md` if exists |
| monitoring | Claim-stream + alerting | monitoring | §5.2 monitoring, §6.2 | none | none | `backend/monitoring/` | `backend/monitoring/README.md` if exists |
| rag | RAG service | rag | §5.2 rag, §6.2 | none | none | `backend/rag/` | `backend/rag/README.md` if exists |
| records | Structured record ingestion | records | §5.2 records, §6.3 | none | none | `backend/records/` | `backend/records/README.md` if exists |
| shared | Shared contracts | shared | §5.2 shared, §2.3 | none | none | `backend/shared/` | `backend/shared/README.md` if exists |
| storage | Object storage | storage | §5.2 storage | none | none | `backend/storage/` | `backend/storage/README.md` if exists |
| vectorstore | Vector store | vectorstore | §5.2 vectorstore | none | `docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md` | `backend/vectorstore/` | `backend/vectorstore/README.md` if exists |

**Sub-steps:**

- [ ] **Step 1: Dispatch in two parallel batches of 9.** Batching avoids overwhelming the platform with 18 concurrent subagents. Batch A: agent, analytics, api, config, database, embeddings, events, frontend, graph. Batch B: ingestion, knowledgebases, llm, monitoring, rag, records, shared, storage, vectorstore. Wait for Batch A to complete before dispatching Batch B.

- [ ] **Step 2: Review each returned fragment.** Same self-check as Task 1.1. Re-dispatch any that fail.

- [ ] **Step 3: Write each fragment to `docs/backlog/_epics_drafts/{file}.md`.**

- [ ] **Step 4: Commit Batch A:**
  ```bash
  git add docs/backlog/_epics_drafts/agent.md docs/backlog/_epics_drafts/analytics.md docs/backlog/_epics_drafts/api.md docs/backlog/_epics_drafts/config.md docs/backlog/_epics_drafts/database.md docs/backlog/_epics_drafts/embeddings.md docs/backlog/_epics_drafts/events.md docs/backlog/_epics_drafts/frontend.md docs/backlog/_epics_drafts/graph.md
  git commit -m "docs(backlog): wave 1 module epic audits batch A"
  ```

- [ ] **Step 5: Commit Batch B:**
  ```bash
  git add docs/backlog/_epics_drafts/ingestion.md docs/backlog/_epics_drafts/knowledgebases.md docs/backlog/_epics_drafts/llm.md docs/backlog/_epics_drafts/monitoring.md docs/backlog/_epics_drafts/rag.md docs/backlog/_epics_drafts/records.md docs/backlog/_epics_drafts/shared.md docs/backlog/_epics_drafts/storage.md docs/backlog/_epics_drafts/vectorstore.md
  git commit -m "docs(backlog): wave 1 module epic audits batch B"
  ```

### Task 1.3: Assemble `_DRAFT_epics.md` with allocated IDs

**Files:**
- Create: `docs/backlog/_DRAFT_epics.md`

**Sub-steps:**

- [ ] **Step 1: Concatenate fragments in canonical order.** Order: cross-cutting first (underscore-prefixed, alphabetical), then modules (alphabetical). The `_DRAFT_epics.md` header:
  ```markdown
  # Wave 1 Draft Epics

  > **Status:** Wave 1 draft pending user approval. This file is temporary and is deleted at the end of Wave 3.
  > **Date:** YYYY-MM-DD (fill in)
  > **Source fragments:** docs/backlog/_epics_drafts/*.md
  >
  > Wave 2 expands these epics into rich-format stories. IDs allocated here are LOCKED — Wave 2 subagents may only cite IDs that appear in this document.

  ## Legend
  - **ID format:** `<file>.<n>` for modules (e.g., `vectorstore.04`); `_<concern>.<n>` for cross-cutting (e.g., `_observability.03`).
  - **Epic numbering:** sequential starting at .01 per file, in the order they appear in the source fragment.
  ```

- [ ] **Step 2: Allocate IDs.** For each file's section, walk its epic list in order and prepend an ID to each epic line:
  ```
  Before:  1. Add tenant-scoped KB queries — KB endpoints currently accept no tenant context (backend/knowledgebases/service.py:42)
  After:   - **_multitenancy.01** — Add tenant-scoped KB queries — KB endpoints currently accept no tenant context (backend/knowledgebases/service.py:42)
  ```
  Drop the `1.`, `2.`, … markdown numbering — IDs are the canonical identifier.

- [ ] **Step 3: Rewrite cross-file edges to use IDs.** Where a fragment says "depends on <Epic title in other_file.md>", replace the title reference with the allocated ID. If the referenced epic title can't be found in the assembled doc, leave a `[UNRESOLVED]` marker — the user resolves at the gate.

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/_DRAFT_epics.md
  git commit -m "docs(backlog): wave 1 assembled draft with allocated IDs"
  ```

### Task 1.4: 🚨 USER APPROVAL GATE — Wave 1 review

**This task does no file work. It halts the plan until the user explicitly approves Wave 1.**

**Sub-steps:**

- [ ] **Step 1: Present the draft.** Output:
  - Path: `docs/backlog/_DRAFT_epics.md`
  - Total epic count
  - Per-file epic count (table)
  - Any `[UNRESOLVED]` cross-file edge markers (list each one — user must resolve before Wave 2)
  - Open questions raised by audits

- [ ] **Step 2: Ask explicitly:**
  > "Wave 1 produced {N} epics across 24 files. Please review `docs/backlog/_DRAFT_epics.md` and approve to proceed to Wave 2, or request reshaping (add/drop/rename epics, re-edge prereqs, resolve UNRESOLVED markers)."

- [ ] **Step 3: HALT.** Do not begin Wave 2 until the user explicitly approves. The string "approved" (or equivalent) must appear in the user's reply. Any other reply (questions, requests for changes, "looks mostly good but…") is *not* approval.

- [ ] **Step 4: If the user requests reshaping:**
  1. Edit `_DRAFT_epics.md` in place to apply the requested changes.
  2. **Critical:** if an epic is dropped, do not re-use its ID. If a new epic is added, allocate the next free ID for its file.
  3. Commit each reshape:
     ```bash
     git add docs/backlog/_DRAFT_epics.md
     git commit -m "docs(backlog): wave 1 reshape per user feedback"
     ```
  4. Loop back to Step 2.

---

## Wave 2 — Story expansion

### Task 2.0: Lock the epic ID space

**Files:**
- Create: `docs/backlog/_LOCKED_id_space.md`

**Sub-steps:**

- [ ] **Step 1: Extract every ID from `_DRAFT_epics.md`.** Use grep:
  ```bash
  grep -oE '\*\*(_?[a-z]+\.[0-9]+)\*\*' docs/backlog/_DRAFT_epics.md | tr -d '*' | sort -u > /tmp/ids.txt
  wc -l /tmp/ids.txt
  ```
  The count should equal the total epic count from Task 1.4 Step 1.

- [ ] **Step 2: Write `_LOCKED_id_space.md`.** Content:
  ```markdown
  # Wave 2 Locked ID Space

  > **Status:** Locked. Wave 2 subagents may only cite IDs that appear in this list as `Prerequisites:` values.
  > Source: docs/backlog/_DRAFT_epics.md (Wave 1, user-approved).

  ## Legal IDs ({N} total)

  <one ID per line, sorted, in fenced code block>
  ```

- [ ] **Step 3: Commit:**
  ```bash
  git add docs/backlog/_LOCKED_id_space.md
  git commit -m "docs(backlog): wave 2 lock ID space (N epics)"
  ```

### Task 2.1: Expand cross-cutting epics into stories (6 parallel subagents)

**Files:**
- Create: `docs/backlog/_observability.md`
- Create: `docs/backlog/_security.md`
- Create: `docs/backlog/_multitenancy.md`
- Create: `docs/backlog/_infra.md`
- Create: `docs/backlog/_cicd.md`
- Create: `docs/backlog/_plugins.md`

**Subagent prompt template** (substitute per-file values):

> You are expanding Wave 1 epics into full rich-format backlog stories for the **{CONCERN}** cross-cutting concern (file `docs/backlog/{FILE}.md`).
>
> **Inputs:**
> - The design spec: `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` (§5 story format is contractual — match it exactly).
> - The Wave 1 draft for context: `docs/backlog/_DRAFT_epics.md`.
> - The locked ID space: `docs/backlog/_LOCKED_id_space.md`. You may only cite IDs in this list as `Prerequisites:` values.
> - Your epic list section in the draft: search `_DRAFT_epics.md` for the section starting `## File: docs/backlog/{FILE}.md`.
> - Architecture sections: **{ARCH_SECTIONS}**.
> - Code paths to read for accurate `Current State` and `Code touch points`: **{CODE_PATHS}**.
>
> **Your output:** the full contents of `docs/backlog/{FILE}.md`, ready to write to disk. Structure:
>
> ```markdown
> # {File-title} backlog
>
> > Scope: <one-line scope summary, copied/refined from Wave 1>.
> > Story format and rules: see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).
>
> <one Story block per epic, in epic-list order, using the rich format below>
> ```
>
> **Story format (verbatim from spec §5):**
>
> ```markdown
> ## Story <id>: <Short title>
>
> **ID:** <id>
> **Status:** planned | in-progress | done | dropped
> **Prerequisites:** [<id>, <id>]
> **Unblocks:** []
> **Estimated size:** S | M | L | XL
> **Spec:** docs/superpowers/specs/<file>.md   # optional; omit if none
> **Done:** <YYYY-MM-DD> · <commit-sha> · <PR#>   # only if Status=done
>
> **As a** <role>,
> **I need** <capability>,
> **so that** <outcome>.
>
> ### Current State
> - <2–6 bullets describing what exists in code TODAY with file:line refs>
> - <or "Nothing exists yet" explicitly>
>
> ### Acceptance Criteria
> - [ ] <testable, observable criterion>
> - [ ] <typed: file path, function signature, endpoint, manifest, doc updated, test passes>
>
> ### Verification
> - <how a reviewer confirms this is done — concrete commands or steps>
> - <coverage gate where applicable: "≥ 85% on <package>">
>
> ### Code touch points
> - <path/to/file.py> (modify | new | delete)
> ```
>
> **Field rules (must follow):**
> - Use the ID assigned in the Wave 1 draft — do not renumber.
> - Set Status: based on whether the work is already complete in the current code:
>   - `done` if all acceptance criteria already pass against current code AND you can identify the commit that completed it (search `git log --oneline -- <file>` for the relevant change).
>   - `in-progress` only if you can see an open branch or in-flight PR — for re-derivation Wave 2, default to `planned` and let the user mark in-progress later.
>   - `planned` otherwise.
> - Set `Unblocks: []` — Wave 3's consistency pass computes this.
> - `Prerequisites:` may only list IDs that appear in `_LOCKED_id_space.md`. Cite cross-file edges (e.g., `[events.03, shared.02]`) when there's a genuine dependency. Empty list `[]` when none.
> - `Estimated size:` your judgment. S < 1 day, M = 1–3 days, L = 3–7 days, XL = 7+ days. Split XL stories into two if you can.
> - `Spec:` link any design spec that designs this story's feature.
> - `Current State:` cite real `file:line` refs from the code you read. "Nothing exists yet" is acceptable when greenfield.
> - `Acceptance Criteria:` checkboxes start unchecked `[ ]` for `planned` stories; checked `[x]` for `done` stories.
> - `Verification:` concrete commands. For tests, name the test file path.
> - `Code touch points:` real file paths. Mark each as `modify | new | delete`.
>
> **Self-check before returning:**
> - Every story has all required fields.
> - Every `Prerequisites:` ID appears in `_LOCKED_id_space.md`.
> - Story IDs in this file match the order/numbering in `_DRAFT_epics.md`.
> - No story has unchecked AC boxes AND `Status: done`.
> - No story is `Status: in-progress` (Wave 2 only emits planned/done).
> - Every `Current State` bullet either cites `file:line` or says "Nothing exists yet".
> - Output is a complete file ready to write — no placeholders, no commentary.

**Per-concern dispatch table:**

| `{CONCERN}` | `{FILE}` | `{ARCH_SECTIONS}` | `{CODE_PATHS}` |
|---|---|---|---|
| Observability | _observability | §11, §14.2 | backend logging usage, frontend RUM, dashboards |
| Security & RBAC | _security | §12, §14.2 | `backend/api/auth/`, middleware, `docs/security_checklist.md`, auth spec |
| Multi-tenancy | _multitenancy | §12.3, §14.2 | `backend/knowledgebases/`, `backend/api/dependencies.py`, `backend/agent/` |
| Infrastructure & IaC | _infra | §10, §14.2 | `infra/`, `docker-compose*.yaml`, Dockerfiles, `Makefile` |
| CI/CD pipeline | _cicd | §10, §14.2 | `.github/workflows/`, `scripts/`, `Makefile` |
| Plugin system | _plugins | §14.2 | (greenfield — likely "Nothing exists yet" for most stories) |

**Sub-steps:**

- [ ] **Step 1: Dispatch 6 subagents in parallel** with the template, one row per concern. Subagent type: `general-purpose`.

- [ ] **Step 2: Review each returned file.** For each: check self-check criteria. If any criterion fails, re-dispatch with corrective feedback.

- [ ] **Step 3: Write each to `docs/backlog/{file}.md`.**

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/_observability.md docs/backlog/_security.md docs/backlog/_multitenancy.md docs/backlog/_infra.md docs/backlog/_cicd.md docs/backlog/_plugins.md
  git commit -m "docs(backlog): wave 2 cross-cutting story expansion"
  ```

### Tasks 2.2–2.5: Expand module epics (18 subagents in 2 batches of 9)

Each module file is one dispatch using the same template as Task 2.1, with these per-module substitutions:

| `{CONCERN}` (used as "module" in the prompt) | `{FILE}` | `{ARCH_SECTIONS}` | `{CODE_PATHS}` |
|---|---|---|---|
| Agent / coordinator | agent | §5.2 agent | `backend/agent/` |
| Analytics | analytics | §5.2 analytics, §6.2 | `backend/analytics/` |
| FastAPI gateway | api | §5.2 api, §4 | `backend/api/` |
| Domain configuration | config | §9, §14.2 | `backend/config/` |
| Database (Postgres + Timescale + Alembic) | database | §5.2 database, §6.4 | `backend/database/` |
| Embeddings | embeddings | §5.2 embeddings | `backend/embeddings/` |
| Events (Redis Streams) | events | §5.2 events, §4 | `backend/events/` |
| Frontend (React workbench) | frontend | §8, §14.2 | `chili_app/src/` |
| Graph | graph | §5.2 graph, §6.x | `backend/graph/` |
| Ingestion | ingestion | §5.2 ingestion, §6.1, §6.5 | `backend/ingestion/` |
| Knowledge bases | knowledgebases | §7, §5.2 | `backend/knowledgebases/` |
| LLM | llm | §5.2 llm | `backend/llm/` |
| Monitoring | monitoring | §5.2 monitoring, §6.2 | `backend/monitoring/` |
| RAG | rag | §5.2 rag, §6.2 | `backend/rag/` |
| Records (structured ingestion) | records | §5.2 records, §6.3 | `backend/records/` |
| Shared contracts | shared | §5.2 shared, §2.3 | `backend/shared/` |
| Object storage | storage | §5.2 storage | `backend/storage/` |
| Vector store | vectorstore | §5.2 vectorstore | `backend/vectorstore/` |

### Task 2.2: Dispatch Batch A (9 modules)

**Files:**
- Create: `docs/backlog/agent.md`, `docs/backlog/analytics.md`, `docs/backlog/api.md`, `docs/backlog/config.md`, `docs/backlog/database.md`, `docs/backlog/embeddings.md`, `docs/backlog/events.md`, `docs/backlog/frontend.md`, `docs/backlog/graph.md`

**Sub-steps:**

- [ ] **Step 1: Dispatch 9 subagents in parallel** for these modules using the Task 2.1 template, substituting from the per-module table above.

- [ ] **Step 2: Review each returned file** against the same self-check criteria as Task 2.1. Re-dispatch failures.

- [ ] **Step 3: Write each file.**

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/agent.md docs/backlog/analytics.md docs/backlog/api.md docs/backlog/config.md docs/backlog/database.md docs/backlog/embeddings.md docs/backlog/events.md docs/backlog/frontend.md docs/backlog/graph.md
  git commit -m "docs(backlog): wave 2 module story expansion batch A"
  ```

### Task 2.3: Dispatch Batch B (9 modules)

**Files:**
- Create: `docs/backlog/ingestion.md`, `docs/backlog/knowledgebases.md`, `docs/backlog/llm.md`, `docs/backlog/monitoring.md`, `docs/backlog/rag.md`, `docs/backlog/records.md`, `docs/backlog/shared.md`, `docs/backlog/storage.md`, `docs/backlog/vectorstore.md`

**Sub-steps:** mirror Task 2.2 with Batch B modules.

- [ ] **Step 1: Dispatch 9 subagents in parallel** for these modules.
- [ ] **Step 2: Review.** Re-dispatch failures.
- [ ] **Step 3: Write each file.**
- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/ingestion.md docs/backlog/knowledgebases.md docs/backlog/llm.md docs/backlog/monitoring.md docs/backlog/rag.md docs/backlog/records.md docs/backlog/shared.md docs/backlog/storage.md docs/backlog/vectorstore.md
  git commit -m "docs(backlog): wave 2 module story expansion batch B"
  ```

### Task 2.4: Cross-file validation pass

Verify Wave 2 output is internally consistent before Wave 3.

**Sub-steps:**

- [ ] **Step 1: Verify every story ID is unique across all files:**
  ```bash
  grep -hE '^\*\*ID:\*\*' docs/backlog/*.md | sort | uniq -d
  ```
  Expected: empty output. If duplicates appear, identify which file's subagent over-allocated and have it fix.

- [ ] **Step 2: Verify every Prerequisites ID resolves:**
  ```bash
  grep -hE '^\*\*ID:\*\*' docs/backlog/*.md | sed 's/.*\*\*ID:\*\* *//' | sort -u > /tmp/declared_ids.txt
  grep -hE '^\*\*Prerequisites:\*\*' docs/backlog/*.md | grep -oE '\b_?[a-z]+\.[0-9]+\b' | sort -u > /tmp/cited_prereqs.txt
  comm -23 /tmp/cited_prereqs.txt /tmp/declared_ids.txt
  ```
  Expected: empty output (no cited ID without a declared ID). Any line is an unresolved prereq — find the file citing it and have its subagent fix.

- [ ] **Step 3: Verify field presence on every story.** Run a quick sanity script:
  ```bash
  for f in docs/backlog/*.md; do
    [ "$f" = "docs/backlog/README.md" ] && continue
    [ "$f" = "docs/backlog/_DRAFT_epics.md" ] && continue
    [ "$f" = "docs/backlog/_LOCKED_id_space.md" ] && continue
    expected=$(grep -c '^## Story' "$f")
    for field in 'ID:' 'Status:' 'Prerequisites:' 'Unblocks:' 'Estimated size:'; do
      got=$(grep -c "^\*\*$field\*\*" "$f")
      if [ "$got" != "$expected" ]; then echo "$f: $field count $got, expected $expected"; fi
    done
  done
  ```
  Expected: no output. Any line is a missing-field bug — fix the file or re-dispatch.

- [ ] **Step 4: No commit** — this task is verification only. If fixes were needed, they were committed by the re-dispatch tasks.

### Task 2.5: Clean up Wave 1 working files

**Files:**
- Delete: `docs/backlog/_DRAFT_epics.md`
- Delete: `docs/backlog/_LOCKED_id_space.md`
- Delete: `docs/backlog/_epics_drafts/` (entire directory)

**Sub-steps:**

- [ ] **Step 1: Verify all 24 final files exist** before deleting working files:
  ```bash
  ls docs/backlog/*.md | wc -l    # expect 24 (6 cross-cutting + 18 module; README.md not yet written)
  ```
  If not 24, do NOT delete the working files — fix Wave 2 first.

- [ ] **Step 2: Delete working files:**
  ```bash
  git rm docs/backlog/_DRAFT_epics.md docs/backlog/_LOCKED_id_space.md
  git rm -r docs/backlog/_epics_drafts
  ```

- [ ] **Step 3: Commit:**
  ```bash
  git commit -m "chore(backlog): remove wave 1 working files"
  ```

---

## Wave 3 — Consistency script + master index + archival

### Tasks 3.1–3.13: TDD the consistency-pass script

The script is built up in 13 TDD increments, one validator or function per task. Each task: write failing test → run → implement → run → commit.

**Files (all tasks):**
- Create/extend: `scripts/backlog_consistency.py`
- Create/extend: `tests/scripts/test_backlog_consistency.py`
- Create as needed: `tests/scripts/fixtures/` for sample backlog files

**Common imports and dataclass** (Task 3.1 establishes; later tasks add):

```python
# scripts/backlog_consistency.py
from __future__ import annotations
import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Story:
    id: str
    file: Path
    status: str  # planned | in-progress | done | dropped
    prerequisites: list[str]
    unblocks: list[str]
    estimated_size: str  # S | M | L | XL
    spec: list[str]
    done_line: str | None
    acceptance_total: int
    acceptance_checked: int
```

### Task 3.1: Story parser — happy path

**Sub-steps:**

- [ ] **Step 1: Create fixture:** `tests/scripts/fixtures/simple.md` with two well-formed stories:
  ```markdown
  # Test fixture

  ## Story foo.01: First

  **ID:** foo.01
  **Status:** planned
  **Prerequisites:** []
  **Unblocks:** []
  **Estimated size:** S

  **As a** user, **I need** thing, **so that** outcome.

  ### Current State
  - Nothing exists yet.

  ### Acceptance Criteria
  - [ ] First criterion.
  - [ ] Second criterion.

  ### Verification
  - Run the test.

  ### Code touch points
  - src/foo.py (new)

  ## Story foo.02: Second

  **ID:** foo.02
  **Status:** done
  **Prerequisites:** [foo.01]
  **Unblocks:** []
  **Estimated size:** M
  **Done:** 2026-05-24 · abc1234 · #42

  **As a** user, **I need** more, **so that** outcome.

  ### Current State
  - Exists at src/foo.py:1.

  ### Acceptance Criteria
  - [x] Criterion one.
  - [x] Criterion two.

  ### Verification
  - pytest tests/foo/

  ### Code touch points
  - src/foo.py (modify)
  ```

- [ ] **Step 2: Write the failing test:**
  ```python
  # tests/scripts/test_backlog_consistency.py
  from pathlib import Path
  from scripts.backlog_consistency import parse_file, Story

  FIXTURES = Path(__file__).parent / "fixtures"

  def test_parse_file_simple():
      stories = parse_file(FIXTURES / "simple.md")
      assert len(stories) == 2
      first = stories[0]
      assert first.id == "foo.01"
      assert first.status == "planned"
      assert first.prerequisites == []
      assert first.unblocks == []
      assert first.estimated_size == "S"
      assert first.spec == []
      assert first.done_line is None
      assert first.acceptance_total == 2
      assert first.acceptance_checked == 0
      second = stories[1]
      assert second.id == "foo.02"
      assert second.status == "done"
      assert second.prerequisites == ["foo.01"]
      assert second.done_line == "2026-05-24 · abc1234 · #42"
      assert second.acceptance_total == 2
      assert second.acceptance_checked == 2
  ```

- [ ] **Step 3: Run test, verify failure:**
  ```bash
  pytest tests/scripts/test_backlog_consistency.py::test_parse_file_simple -v
  ```
  Expected: FAIL (`parse_file` not defined).

- [ ] **Step 4: Implement `parse_file`:**
  ```python
  STORY_HEADING = re.compile(r"^## Story (\S+):", re.MULTILINE)
  FIELD = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.*?)\s*$", re.MULTILINE)
  AC_BOX = re.compile(r"^- \[(?P<mark>[ xX])\]", re.MULTILINE)
  ID_LIST = re.compile(r"\[(?P<inner>[^\]]*)\]")

  def _parse_id_list(raw: str) -> list[str]:
      m = ID_LIST.search(raw)
      if not m:
          return []
      inner = m.group("inner").strip()
      if not inner:
          return []
      return [x.strip() for x in inner.split(",")]

  def parse_file(path: Path) -> list[Story]:
      text = path.read_text(encoding="utf-8")
      headings = list(STORY_HEADING.finditer(text))
      stories: list[Story] = []
      for i, heading in enumerate(headings):
          start = heading.end()
          end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
          body = text[start:end]
          fields: dict[str, str] = {}
          for fmatch in FIELD.finditer(body):
              fields[fmatch.group("key").strip()] = fmatch.group("value").strip()
          # Truncate to Current State to avoid pulling fields out of later sections
          # (parser stops at the first "### " sub-heading by way of FIELD only matching field-shaped lines)
          ac_section_start = body.find("### Acceptance Criteria")
          ac_section_end_candidates = [body.find(h, ac_section_start) for h in ("### Verification", "### Code touch points", "## Story") if ac_section_start != -1]
          ac_section_end_candidates = [c for c in ac_section_end_candidates if c != -1]
          if ac_section_start == -1:
              ac_total = ac_checked = 0
          else:
              ac_end = min(ac_section_end_candidates) if ac_section_end_candidates else len(body)
              ac_body = body[ac_section_start:ac_end]
              ac_marks = AC_BOX.findall(ac_body)
              ac_total = len(ac_marks)
              ac_checked = sum(1 for m in ac_marks if m in ("x", "X"))
          stories.append(Story(
              id=fields["ID"],
              file=path,
              status=fields["Status"],
              prerequisites=_parse_id_list(fields.get("Prerequisites", "[]")),
              unblocks=_parse_id_list(fields.get("Unblocks", "[]")),
              estimated_size=fields["Estimated size"],
              spec=[s.strip() for s in fields.get("Spec", "").split(",") if s.strip()] if fields.get("Spec") else [],
              done_line=fields.get("Done"),
              acceptance_total=ac_total,
              acceptance_checked=ac_checked,
          ))
      return stories
  ```

- [ ] **Step 5: Run test, verify pass:**
  ```bash
  pytest tests/scripts/test_backlog_consistency.py::test_parse_file_simple -v
  ```
  Expected: PASS.

- [ ] **Step 6: Commit:**
  ```bash
  git add scripts/backlog_consistency.py tests/scripts/test_backlog_consistency.py tests/scripts/fixtures/simple.md
  git commit -m "feat(backlog-script): parse stories from a single file"
  ```

### Task 3.2: Story parser — malformed input is a hard error

**Sub-steps:**

- [ ] **Step 1: Create fixture** `tests/scripts/fixtures/missing_field.md` with a story missing the `Status:` field.

- [ ] **Step 2: Write the failing test:**
  ```python
  import pytest
  from scripts.backlog_consistency import parse_file

  def test_parse_file_missing_field_raises():
      with pytest.raises(KeyError, match="Status"):
          parse_file(FIXTURES / "missing_field.md")
  ```

- [ ] **Step 3: Run, verify failure.**

- [ ] **Step 4: Confirm `parse_file` already raises** `KeyError` from `fields["Status"]` access — should pass without changes.

- [ ] **Step 5: Run, verify pass.**

- [ ] **Step 6: Add a second fixture** `tests/scripts/fixtures/bad_id.md` with `ID: foo` (missing dot+number). Add a test:
  ```python
  ID_RE = re.compile(r"^_?[a-z]+\.\d+$")

  def test_parse_file_bad_id_raises():
      with pytest.raises(ValueError, match="ID"):
          parse_file(FIXTURES / "bad_id.md")
  ```
  Add ID validation in `parse_file` after extracting `fields["ID"]`:
  ```python
  if not ID_RE.match(fields["ID"]):
      raise ValueError(f"Invalid ID format in {path}: {fields['ID']!r}")
  ```

- [ ] **Step 7: Commit:**
  ```bash
  git add scripts/backlog_consistency.py tests/scripts/test_backlog_consistency.py tests/scripts/fixtures/
  git commit -m "feat(backlog-script): hard-error on malformed stories"
  ```

### Task 3.3: `parse_all` — load every backlog file into one ID map

**Sub-steps:**

- [ ] **Step 1: Write failing test:**
  ```python
  from scripts.backlog_consistency import parse_all

  def test_parse_all_loads_directory(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      (tmp_path / "b.md").write_text("# empty\n")  # no stories
      stories = parse_all(tmp_path)
      assert set(stories.keys()) == {"foo.01", "foo.02"}
  ```

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Implement:**
  ```python
  def parse_all(backlog_dir: Path) -> dict[str, Story]:
      result: dict[str, Story] = {}
      for path in sorted(backlog_dir.glob("*.md")):
          if path.name == "README.md":
              continue
          for story in parse_file(path):
              if story.id in result:
                  raise ValueError(f"Duplicate ID {story.id} in {path} (also in {result[story.id].file})")
              result[story.id] = story
      return result
  ```

- [ ] **Step 4: Add duplicate-ID test:**
  ```python
  def test_parse_all_duplicate_id_raises(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      (tmp_path / "b.md").write_text((FIXTURES / "simple.md").read_text())
      with pytest.raises(ValueError, match="Duplicate ID foo.01"):
          parse_all(tmp_path)
  ```

- [ ] **Step 5: Run all, verify pass.**

- [ ] **Step 6: Commit:**
  ```bash
  git commit -am "feat(backlog-script): parse_all aggregates stories with duplicate-ID check"
  ```

### Task 3.4: Validate prereq references resolve

- [ ] **Step 1: Write failing test:**
  ```python
  from scripts.backlog_consistency import validate_prereq_references

  def test_validate_prereq_references_passes(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      stories = parse_all(tmp_path)
      errors = validate_prereq_references(stories)
      assert errors == []

  def test_validate_prereq_references_unresolved(tmp_path):
      # Use a fixture where foo.02 cites foo.99 (doesn't exist)
      bad = (FIXTURES / "simple.md").read_text().replace("[foo.01]", "[foo.99]")
      (tmp_path / "a.md").write_text(bad)
      stories = parse_all(tmp_path)
      errors = validate_prereq_references(stories)
      assert len(errors) == 1
      assert "foo.02" in errors[0] and "foo.99" in errors[0]
  ```

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Implement:**
  ```python
  def validate_prereq_references(stories: dict[str, Story]) -> list[str]:
      errors: list[str] = []
      for story in stories.values():
          for pid in story.prerequisites:
              if pid not in stories:
                  errors.append(f"Story {story.id} ({story.file.name}) cites prerequisite {pid!r} that does not exist")
      return errors
  ```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit:**
  ```bash
  git commit -am "feat(backlog-script): validate prereq references resolve"
  ```

### Task 3.5: Cycle detection via topological sort

- [ ] **Step 1: Create fixture `tests/scripts/fixtures/cycle.md`** with two stories that depend on each other:
  ```markdown
  ## Story foo.01: First
  **ID:** foo.01
  **Status:** planned
  **Prerequisites:** [foo.02]
  **Unblocks:** []
  **Estimated size:** S

  **As a** x, **I need** y, **so that** z.
  ### Current State
  - x
  ### Acceptance Criteria
  - [ ] a
  ### Verification
  - x
  ### Code touch points
  - x

  ## Story foo.02: Second
  **ID:** foo.02
  **Status:** planned
  **Prerequisites:** [foo.01]
  **Unblocks:** []
  **Estimated size:** S

  **As a** x, **I need** y, **so that** z.
  ### Current State
  - x
  ### Acceptance Criteria
  - [ ] a
  ### Verification
  - x
  ### Code touch points
  - x
  ```

- [ ] **Step 2: Write failing test:**
  ```python
  from scripts.backlog_consistency import detect_cycles

  def test_detect_cycles_finds_pair(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "cycle.md").read_text())
      stories = parse_all(tmp_path)
      cycles = detect_cycles(stories)
      assert len(cycles) >= 1
      assert set(cycles[0]) == {"foo.01", "foo.02"}

  def test_detect_cycles_clean(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      stories = parse_all(tmp_path)
      assert detect_cycles(stories) == []
  ```

- [ ] **Step 3: Run, verify failure.**

- [ ] **Step 4: Implement using Kahn's algorithm:**
  ```python
  def detect_cycles(stories: dict[str, Story]) -> list[list[str]]:
      in_deg: dict[str, int] = {sid: len(s.prerequisites) for sid, s in stories.items()}
      reverse: dict[str, list[str]] = defaultdict(list)
      for sid, story in stories.items():
          for p in story.prerequisites:
              if p in stories:  # skip unresolved (caught by validate_prereq_references)
                  reverse[p].append(sid)
      ready = [sid for sid, d in in_deg.items() if d == 0]
      visited: set[str] = set()
      while ready:
          sid = ready.pop()
          visited.add(sid)
          for child in reverse[sid]:
              in_deg[child] -= 1
              if in_deg[child] == 0:
                  ready.append(child)
      cyclic = [sid for sid in stories if sid not in visited]
      if not cyclic:
          return []
      # Find one representative cycle within the cyclic set
      cycle = _find_cycle(cyclic, stories)
      return [cycle]

  def _find_cycle(cyclic: list[str], stories: dict[str, Story]) -> list[str]:
      # DFS from any cyclic node until we revisit
      start = cyclic[0]
      path: list[str] = []
      seen: set[str] = set()
      def dfs(sid: str) -> list[str] | None:
          if sid in seen:
              i = path.index(sid)
              return path[i:]
          seen.add(sid)
          path.append(sid)
          for p in stories[sid].prerequisites:
              if p in cyclic:
                  result = dfs(p)
                  if result:
                      return result
          path.pop()
          return None
      return dfs(start) or [start]
  ```

- [ ] **Step 5: Run, verify pass.**

- [ ] **Step 6: Commit:**
  ```bash
  git commit -am "feat(backlog-script): detect cycles via topological sort"
  ```

### Task 3.6: Validate status invariants

Done stories need `Done:`, every AC `[x]`. In-progress stories need all prereqs done. Dropped is always valid.

- [ ] **Step 1: Add fixtures:** `done_missing_done_line.md`, `done_unchecked_ac.md`, `in_progress_with_planned_prereq.md`.

- [ ] **Step 2: Write failing tests:**
  ```python
  from scripts.backlog_consistency import validate_status_invariants

  def test_status_done_must_have_done_line(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "done_missing_done_line.md").read_text())
      errors = validate_status_invariants(parse_all(tmp_path))
      assert any("Done line" in e for e in errors)

  def test_status_done_must_have_all_ac_checked(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "done_unchecked_ac.md").read_text())
      errors = validate_status_invariants(parse_all(tmp_path))
      assert any("unchecked acceptance criteria" in e for e in errors)

  def test_status_in_progress_needs_done_prereqs(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "in_progress_with_planned_prereq.md").read_text())
      errors = validate_status_invariants(parse_all(tmp_path))
      assert any("not all prerequisites are done" in e for e in errors)
  ```

- [ ] **Step 3: Run, verify failures.**

- [ ] **Step 4: Implement:**
  ```python
  def validate_status_invariants(stories: dict[str, Story]) -> list[str]:
      errors: list[str] = []
      for s in stories.values():
          if s.status == "done":
              if not s.done_line:
                  errors.append(f"Story {s.id}: Status=done but Done line is missing")
              if s.acceptance_total > 0 and s.acceptance_checked < s.acceptance_total:
                  errors.append(f"Story {s.id}: Status=done but {s.acceptance_total - s.acceptance_checked} unchecked acceptance criteria")
          if s.status == "in-progress":
              unmet = [p for p in s.prerequisites if p in stories and stories[p].status != "done"]
              if unmet:
                  errors.append(f"Story {s.id}: Status=in-progress but not all prerequisites are done: {unmet}")
          if s.status not in ("planned", "in-progress", "done", "dropped"):
              errors.append(f"Story {s.id}: invalid Status {s.status!r}")
      return errors
  ```

- [ ] **Step 5: Run, verify pass.**

- [ ] **Step 6: Commit:**
  ```bash
  git commit -am "feat(backlog-script): validate status invariants (done/in-progress/dropped)"
  ```

### Task 3.7: XL size warning (and `--strict` upgrade)

- [ ] **Step 1: Fixture** `xl_story.md` with one story sized XL.

- [ ] **Step 2: Failing tests:**
  ```python
  from scripts.backlog_consistency import warn_xl_size

  def test_warn_xl_size_returns_warnings(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "xl_story.md").read_text())
      stories = parse_all(tmp_path)
      warnings = warn_xl_size(stories)
      assert len(warnings) == 1
      assert "XL" in warnings[0]
  ```

- [ ] **Step 3: Run, fail.**

- [ ] **Step 4: Implement:**
  ```python
  def warn_xl_size(stories: dict[str, Story]) -> list[str]:
      return [f"Story {s.id}: Estimated size XL — split before merge" for s in stories.values() if s.estimated_size == "XL"]
  ```

- [ ] **Step 5: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): warn on XL stories"
  ```

### Task 3.8: Compute Unblocks (inverse graph)

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import compute_unblocks

  def test_compute_unblocks_inverts(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      stories = parse_all(tmp_path)
      result = compute_unblocks(stories)
      assert result["foo.01"] == ["foo.02"]
      assert result["foo.02"] == []
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  def compute_unblocks(stories: dict[str, Story]) -> dict[str, list[str]]:
      result: dict[str, list[str]] = {sid: [] for sid in stories}
      for s in stories.values():
          for p in s.prerequisites:
              if p in result:
                  result[p].append(s.id)
      for k in result:
          result[k].sort()
      return result
  ```

- [ ] **Step 3: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): compute Unblocks as inverse of Prerequisites"
  ```

### Task 3.9: Rewrite Unblocks lines in place

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import rewrite_unblocks

  def test_rewrite_unblocks_updates_file(tmp_path):
      src = (FIXTURES / "simple.md").read_text()
      # simple.md has foo.01.Unblocks=[] — should become [foo.02]
      target = tmp_path / "a.md"
      target.write_text(src)
      stories = parse_all(tmp_path)
      computed = compute_unblocks(stories)
      changes = rewrite_unblocks(stories, computed, check_only=False)
      assert len(changes) == 1
      # foo.01.Unblocks should now be [foo.02]
      new_text = target.read_text()
      assert "**Unblocks:** [foo.02]" in new_text

  def test_rewrite_unblocks_check_only_reports_no_write(tmp_path):
      src = (FIXTURES / "simple.md").read_text()
      target = tmp_path / "a.md"
      target.write_text(src)
      stories = parse_all(tmp_path)
      computed = compute_unblocks(stories)
      changes = rewrite_unblocks(stories, computed, check_only=True)
      assert len(changes) == 1
      # File unchanged
      assert target.read_text() == src
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  UNBLOCKS_LINE = re.compile(r"^\*\*Unblocks:\*\* \[[^\]]*\]\s*$", re.MULTILINE)

  def _format_id_list(ids: list[str]) -> str:
      return "[" + ", ".join(ids) + "]"

  def rewrite_unblocks(stories: dict[str, Story], computed: dict[str, list[str]], check_only: bool) -> list[str]:
      changes: list[str] = []
      # Group stories by file
      by_file: dict[Path, list[Story]] = defaultdict(list)
      for s in stories.values():
          by_file[s.file].append(s)
      for path, file_stories in by_file.items():
          text = path.read_text(encoding="utf-8")
          new_text = text
          # Walk through each story heading and patch the next Unblocks line.
          for s in file_stories:
              expected = computed.get(s.id, [])
              if sorted(s.unblocks) == sorted(expected):
                  continue
              # Find this story's heading and the next Unblocks: line after it
              heading = f"## Story {s.id}:"
              h_pos = new_text.find(heading)
              if h_pos == -1:
                  raise RuntimeError(f"Could not find heading for {s.id} in {path}")
              ub_match = UNBLOCKS_LINE.search(new_text, h_pos)
              if not ub_match:
                  raise RuntimeError(f"Could not find Unblocks line for {s.id} in {path}")
              old_line = ub_match.group(0)
              new_line = f"**Unblocks:** {_format_id_list(expected)}"
              new_text = new_text[:ub_match.start()] + new_line + new_text[ub_match.end():]
              changes.append(f"{path.name}:{s.id} {old_line.strip()} -> {new_line}")
          if new_text != text and not check_only:
              path.write_text(new_text, encoding="utf-8")
      return changes
  ```

- [ ] **Step 3: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): rewrite Unblocks lines in place"
  ```

### Task 3.10: Compute ready set

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import compute_ready_set

  def test_ready_set(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      stories = parse_all(tmp_path)
      ready = compute_ready_set(stories)
      # foo.01 is planned with no prereqs -> ready. foo.02 is done -> not in ready.
      assert [s.id for s in ready] == ["foo.01"]
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  SIZE_ORDER = {"S": 1, "M": 2, "L": 3, "XL": 4}

  def compute_ready_set(stories: dict[str, Story]) -> list[Story]:
      ready: list[Story] = []
      for s in stories.values():
          if s.status != "planned":
              continue
          if all(p in stories and stories[p].status == "done" for p in s.prerequisites):
              ready.append(s)
      ready.sort(key=lambda s: (SIZE_ORDER.get(s.estimated_size, 99), s.id))
      return ready
  ```

- [ ] **Step 3: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): compute ready set"
  ```

### Task 3.11: Compute critical path

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import compute_critical_path

  def test_critical_path(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      stories = parse_all(tmp_path)
      path = compute_critical_path(stories)
      # foo.01 (S=1) -> foo.02 (M=2) — total 3
      assert [s.id for s in path] == ["foo.01", "foo.02"]
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  SIZE_WEIGHT = {"S": 1, "M": 2, "L": 5, "XL": 10}

  def compute_critical_path(stories: dict[str, Story]) -> list[Story]:
      # Longest path in a DAG: topo order, then DP.
      in_deg = {sid: 0 for sid in stories}
      for s in stories.values():
          for p in s.prerequisites:
              if p in stories:
                  in_deg[s.id] += 1
      reverse: dict[str, list[str]] = defaultdict(list)
      for s in stories.values():
          for p in s.prerequisites:
              if p in stories:
                  reverse[p].append(s.id)
      order: list[str] = []
      ready = [sid for sid, d in in_deg.items() if d == 0]
      while ready:
          sid = ready.pop()
          order.append(sid)
          for child in reverse[sid]:
              in_deg[child] -= 1
              if in_deg[child] == 0:
                  ready.append(child)
      if len(order) != len(stories):
          return []  # cycle present; caller should run detect_cycles separately
      best: dict[str, tuple[int, list[str]]] = {}
      for sid in order:
          s = stories[sid]
          w = SIZE_WEIGHT.get(s.estimated_size, 1)
          best_pred: tuple[int, list[str]] = (0, [])
          for p in s.prerequisites:
              if p in best and best[p][0] > best_pred[0]:
                  best_pred = best[p]
          best[sid] = (best_pred[0] + w, best_pred[1] + [sid])
      _, path_ids = max(best.values(), key=lambda x: x[0]) if best else (0, [])
      return [stories[i] for i in path_ids]
  ```

- [ ] **Step 3: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): compute critical path by weighted size"
  ```

### Task 3.12: Render generated sections + rewrite README markers

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import rewrite_readme

  def test_rewrite_readme_replaces_marker_sections(tmp_path):
      (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
      readme = tmp_path / "README.md"
      readme.write_text(
          "# X\n\n"
          "<!-- BEGIN: status-rollup -->\nOLD\n<!-- END: status-rollup -->\n\n"
          "<!-- BEGIN: ready-set -->\nOLD\n<!-- END: ready-set -->\n\n"
          "<!-- BEGIN: critical-path -->\nOLD\n<!-- END: critical-path -->\n"
      )
      stories = parse_all(tmp_path)
      changes = rewrite_readme(readme, stories, check_only=False)
      assert len(changes) == 3
      new_text = readme.read_text()
      assert "OLD" not in new_text
      assert "foo.01" in new_text  # ready set rendered
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  def render_status_rollup(stories: dict[str, Story]) -> str:
      by_file: dict[str, dict[str, int]] = defaultdict(lambda: {"planned": 0, "in-progress": 0, "done": 0, "dropped": 0})
      for s in stories.values():
          by_file[s.file.name][s.status] += 1
      lines = ["| File | Planned | In-progress | Done | Total | % done |", "|------|---------|-------------|------|-------|--------|"]
      grand = {"planned": 0, "in-progress": 0, "done": 0, "dropped": 0}
      for fname in sorted(by_file):
          counts = by_file[fname]
          total = sum(counts.values())
          pct = (counts["done"] * 100 // total) if total else 0
          lines.append(f"| {fname} | {counts['planned']} | {counts['in-progress']} | {counts['done']} | {total} | {pct}% |")
          for k, v in counts.items():
              grand[k] += v
      gtotal = sum(grand.values())
      gpct = (grand["done"] * 100 // gtotal) if gtotal else 0
      lines.append(f"| **Total** | {grand['planned']} | {grand['in-progress']} | {grand['done']} | {gtotal} | {gpct}% |")
      return "\n".join(lines)

  def render_ready_set(ready: list[Story]) -> str:
      capped = ready[:30]
      lines = [f"- [{s.id}] {s.file.stem} — size {s.estimated_size} — prereqs done" for s in capped]
      if len(ready) > 30:
          lines.append(f"- …{len(ready) - 30} more")
      return "\n".join(lines) if lines else "- (no ready stories)"

  def render_critical_path(path: list[Story]) -> str:
      if not path:
          return "- (no path — DAG empty or contains a cycle)"
      total = sum(SIZE_WEIGHT.get(s.estimated_size, 1) for s in path)
      lines = ["> Longest dependency chain by weighted size (S=1, M=2, L=5, XL=10)."]
      for i, s in enumerate(path, 1):
          w = SIZE_WEIGHT.get(s.estimated_size, 1)
          arrow = " → " if i < len(path) else ""
          lines.append(f"{i}. {s.id} ({s.estimated_size}={w}){arrow}")
      lines.append(f"\n**Total weight: {total}**")
      return "\n".join(lines)

  MARKER_RE = {
      "status-rollup": re.compile(r"<!-- BEGIN: status-rollup -->.*?<!-- END: status-rollup -->", re.DOTALL),
      "ready-set": re.compile(r"<!-- BEGIN: ready-set -->.*?<!-- END: ready-set -->", re.DOTALL),
      "critical-path": re.compile(r"<!-- BEGIN: critical-path -->.*?<!-- END: critical-path -->", re.DOTALL),
  }

  def rewrite_readme(readme_path: Path, stories: dict[str, Story], check_only: bool) -> list[str]:
      text = readme_path.read_text(encoding="utf-8")
      ready = compute_ready_set(stories)
      crit = compute_critical_path(stories)
      sections = {
          "status-rollup": render_status_rollup(stories),
          "ready-set": render_ready_set(ready),
          "critical-path": render_critical_path(crit),
      }
      changes: list[str] = []
      new_text = text
      for name, body in sections.items():
          pat = MARKER_RE[name]
          if not pat.search(new_text):
              raise RuntimeError(f"README missing marker for {name}")
          replacement = f"<!-- BEGIN: {name} -->\n{body}\n<!-- END: {name} -->"
          patched = pat.sub(replacement, new_text)
          if patched != new_text:
              changes.append(name)
              new_text = patched
      if not check_only and new_text != text:
          readme_path.write_text(new_text, encoding="utf-8")
      return changes
  ```

- [ ] **Step 3: Run, pass. Commit:**
  ```bash
  git commit -am "feat(backlog-script): render and rewrite README marker sections"
  ```

### Task 3.13: CLI entry point + `--check` mode

- [ ] **Step 1: Failing test:**
  ```python
  from scripts.backlog_consistency import main

  def test_main_passes_on_clean_fixture(tmp_path, capsys):
      backlog = tmp_path / "backlog"
      backlog.mkdir()
      (backlog / "a.md").write_text((FIXTURES / "simple.md").read_text())
      readme = backlog / "README.md"
      readme.write_text(
          "<!-- BEGIN: status-rollup -->\n\n<!-- END: status-rollup -->\n"
          "<!-- BEGIN: ready-set -->\n\n<!-- END: ready-set -->\n"
          "<!-- BEGIN: critical-path -->\n\n<!-- END: critical-path -->\n"
      )
      rc = main(["--backlog-dir", str(backlog)])
      assert rc == 0

  def test_main_check_flag_fails_on_drift(tmp_path):
      backlog = tmp_path / "backlog"
      backlog.mkdir()
      (backlog / "a.md").write_text((FIXTURES / "simple.md").read_text())
      readme = backlog / "README.md"
      readme.write_text(
          "<!-- BEGIN: status-rollup -->\n\n<!-- END: status-rollup -->\n"
          "<!-- BEGIN: ready-set -->\n\n<!-- END: ready-set -->\n"
          "<!-- BEGIN: critical-path -->\n\n<!-- END: critical-path -->\n"
      )
      rc = main(["--backlog-dir", str(backlog), "--check"])
      assert rc != 0  # drift: stories file has Unblocks=[] but should be [foo.02]
  ```

- [ ] **Step 2: Fail. Implement:**
  ```python
  def main(argv: list[str] | None = None) -> int:
      parser = argparse.ArgumentParser(description="chiliAI backlog consistency pass")
      parser.add_argument("--backlog-dir", default="docs/backlog", help="Directory containing backlog files")
      parser.add_argument("--check", action="store_true", help="Read-only mode: exit non-zero on any drift; never write")
      parser.add_argument("--strict", action="store_true", help="Upgrade XL warnings to errors")
      args = parser.parse_args(argv)

      backlog_dir = Path(args.backlog_dir)
      readme = backlog_dir / "README.md"
      if not readme.exists():
          print(f"error: {readme} does not exist", file=sys.stderr)
          return 2

      stories = parse_all(backlog_dir)
      errors: list[str] = []
      errors.extend(validate_prereq_references(stories))
      cycles = detect_cycles(stories)
      for c in cycles:
          errors.append(f"Cycle detected: {' -> '.join(c)} -> {c[0]}")
      errors.extend(validate_status_invariants(stories))
      xl_warnings = warn_xl_size(stories)
      if args.strict:
          errors.extend(xl_warnings)

      computed = compute_unblocks(stories)
      unblocks_changes = rewrite_unblocks(stories, computed, check_only=args.check)
      readme_changes = rewrite_readme(readme, stories, check_only=args.check)

      for e in errors:
          print(f"error: {e}", file=sys.stderr)
      for w in xl_warnings:
          if not args.strict:
              print(f"warning: {w}", file=sys.stderr)
      if args.check:
          for ch in unblocks_changes:
              print(f"drift: {ch}", file=sys.stderr)
          for name in readme_changes:
              print(f"drift: README section {name}", file=sys.stderr)
          if errors or unblocks_changes or readme_changes:
              return 1
      else:
          if errors:
              return 1
          for ch in unblocks_changes:
              print(f"rewrote: {ch}")
          for name in readme_changes:
              print(f"rewrote: README section {name}")
      return 0

  if __name__ == "__main__":
      raise SystemExit(main())
  ```

- [ ] **Step 3: Run, pass.**

- [ ] **Step 4: Run the full test suite with coverage:**
  ```bash
  pytest tests/scripts/test_backlog_consistency.py --cov=scripts.backlog_consistency --cov-report=term-missing
  ```
  Expected: ≥ 85% coverage. If under, add tests for uncovered branches before commit.

- [ ] **Step 5: Commit:**
  ```bash
  git commit -am "feat(backlog-script): CLI with --check and --strict flags"
  ```

### Task 3.14: Write `docs/backlog/README.md` with curated sections + markers

**Files:**
- Create: `docs/backlog/README.md`

**Sub-steps:**

- [ ] **Step 1: Write the README** per spec §7. Hand-write the curated parts (How to read, Cross-cutting epics, Module backlogs, Archived, Design specs, Maintenance). Include the marker stubs for the script to populate. Use exact bullet text:
  ```markdown
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
  (auto-generated by scripts/backlog_consistency.py)
  <!-- END: status-rollup -->

  ## Ready set (work that can start today)
  <!-- BEGIN: ready-set -->
  (auto-generated by scripts/backlog_consistency.py)
  <!-- END: ready-set -->

  ## Critical path
  <!-- BEGIN: critical-path -->
  (auto-generated by scripts/backlog_consistency.py)
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
  - `docs/agent_backlog_05_17.md` → [docs/archive/planning/agent_backlog_05_17.md](../archive/planning/agent_backlog_05_17.md) — superseded by [agent.md](agent.md) on YYYY-MM-DD
  - `docs/graph_backlog_05_17.md` → [docs/archive/planning/graph_backlog_05_17.md](../archive/planning/graph_backlog_05_17.md) — superseded by [graph.md](graph.md) on YYYY-MM-DD
  - `docs/ingestion_backlog_05_17.md` → [docs/archive/planning/ingestion_backlog_05_17.md](../archive/planning/ingestion_backlog_05_17.md) — superseded by [ingestion.md](ingestion.md) on YYYY-MM-DD

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

  ## Maintenance
  - **Adding a story:** pick the file, allocate the next free `<file>.<n>` ID, fill the rich format (see [spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format)), run `python scripts/backlog_consistency.py`.
  - **Closing a story:** flip Status to `done`, fill `Done:`, check the AC boxes, run the consistency pass.
  - **Consistency pass:** `python scripts/backlog_consistency.py` (writes) or `--check` (CI mode, read-only).
  ```

- [ ] **Step 2: Substitute today's date** for the `YYYY-MM-DD` placeholders in the archived section.

- [ ] **Step 3: Commit:**
  ```bash
  git add docs/backlog/README.md
  git commit -m "docs(backlog): write master index README"
  ```

### Task 3.15: Run the consistency pass; fix any errors

**Sub-steps:**

- [ ] **Step 1: Run:**
  ```bash
  python scripts/backlog_consistency.py
  ```
  Expected: zero errors; may print `warning: ... XL` lines; may print `rewrote: ...` lines as it patches Unblocks and README sections.

- [ ] **Step 2: If errors:**
  - Cycles → split or merge the cited stories.
  - Unresolved prereqs → fix typo in the citing story, or add a missing story (re-dispatch the relevant Wave 2 subagent).
  - Status-invariant violations → fix the offending story.
  - Re-run until clean.

- [ ] **Step 3: Verify README marker sections populated:**
  ```bash
  grep -A 5 'BEGIN: status-rollup' docs/backlog/README.md | head -20
  ```
  Expected: a table with real per-file counts.

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/
  git commit -m "docs(backlog): first consistency-pass output (rewrites + README sections)"
  ```

### Task 3.16: Add CI hook

**Files:**
- Modify: `.github/workflows/ci.yml`

**Sub-steps:**

- [ ] **Step 1: Inspect existing CI:**
  ```bash
  cat .github/workflows/ci.yml
  ```
  Identify a Python job (one with `setup-python` or `uv`) to append the step to.

- [ ] **Step 2: Add this step** to the chosen job, after Python setup but before test steps:
  ```yaml
        - name: Backlog consistency
          run: python scripts/backlog_consistency.py --check
          if: |
            contains(toJson(github.event.pull_request.changed_files), 'docs/backlog/') ||
            contains(toJson(github.event.head_commit.modified), 'docs/backlog/') ||
            contains(toJson(github.event.head_commit.added), 'docs/backlog/')
  ```
  Note: GitHub Actions `contains()` over changed_files requires the JSON-array trick; if your existing CI uses a different change-detection pattern, mirror it. If unsure, drop the `if:` — running the script unconditionally is fast.

- [ ] **Step 3: Verify locally:** the workflow YAML still parses (use a YAML validator or rely on CI rejection on push).

- [ ] **Step 4: Commit:**
  ```bash
  git add .github/workflows/ci.yml
  git commit -m "ci: enforce backlog consistency on PRs touching docs/backlog/"
  ```

### Task 3.17: Archive the three 05_17 backlogs

**Files:**
- Move: `docs/agent_backlog_05_17.md` → `docs/archive/planning/agent_backlog_05_17.md`
- Move: `docs/graph_backlog_05_17.md` → `docs/archive/planning/graph_backlog_05_17.md`
- Move: `docs/ingestion_backlog_05_17.md` → `docs/archive/planning/ingestion_backlog_05_17.md`

**Sub-steps:**

- [ ] **Step 1: Ensure target dir exists:**
  ```bash
  mkdir -p docs/archive/planning
  ```

- [ ] **Step 2: Move with git:**
  ```bash
  git mv docs/agent_backlog_05_17.md docs/archive/planning/
  git mv docs/graph_backlog_05_17.md docs/archive/planning/
  git mv docs/ingestion_backlog_05_17.md docs/archive/planning/
  ```

- [ ] **Step 3: Update the archived-section link target dates in `docs/backlog/README.md`** if they're still `YYYY-MM-DD` placeholders — replace with today's date.

- [ ] **Step 4: Commit:**
  ```bash
  git add docs/backlog/README.md docs/
  git commit -m "docs(archive): retire 2026-05-17 module backlogs (superseded by docs/backlog/)"
  ```

### Task 3.18: Archive the planning docs

**Files:**
- Move: `docs/planning/code_review_2026-05-24.md` + `docs/planning/code-review-2026-05-24/` → `docs/archive/planning/2026-05-24-code-review/`
- Move: `docs/planning/p3_watch_items_2026-05-12.md` → `docs/archive/planning/`

**Sub-steps:**

- [ ] **Step 1: Verify their content is represented in stories.** Run a quick grep audit:
  ```bash
  # Each top-level theme/heading in code_review_2026-05-24.md should map to at least one story in the new backlog.
  grep -E '^## |^### ' docs/planning/code_review_2026-05-24.md
  ```
  For each theme line, manually verify a story exists. If a theme isn't covered, **stop** — add the missing story to the appropriate `docs/backlog/<file>.md` (or re-dispatch its Wave-2 subagent), commit, then resume.

- [ ] **Step 2: Move:**
  ```bash
  mkdir -p docs/archive/planning/2026-05-24-code-review
  git mv docs/planning/code_review_2026-05-24.md docs/archive/planning/2026-05-24-code-review/
  git mv docs/planning/code-review-2026-05-24/ docs/archive/planning/2026-05-24-code-review/plans
  git mv docs/planning/p3_watch_items_2026-05-12.md docs/archive/planning/
  ```

- [ ] **Step 3: If `docs/planning/` is now empty**, remove the directory:
  ```bash
  rmdir docs/planning 2>/dev/null || true
  ```

- [ ] **Step 4: Commit:**
  ```bash
  git commit -m "docs(archive): retire 2026-05-24 code review and p3 watch items (consumed into backlog)"
  ```

### Task 3.19: Update root `README.md`

**Files:**
- Modify: `README.md`

**Sub-steps:**

- [ ] **Step 1: Read the current Documentation table:**
  ```bash
  grep -nA 20 '^## Documentation' README.md
  ```

- [ ] **Step 2: Replace the row referencing the three 05_17 backlogs** with a single row pointing to `docs/backlog/README.md`. Concretely, find the line:
  ```markdown
  | [`docs/agent_backlog_05_17.md`](docs/agent_backlog_05_17.md) / [`graph_backlog_05_17.md`](docs/graph_backlog_05_17.md) / [`ingestion_backlog_05_17.md`](docs/ingestion_backlog_05_17.md) | Module production-readiness backlogs |
  ```
  And replace with:
  ```markdown
  | [`docs/backlog/README.md`](docs/backlog/README.md) | Live, dependency-ordered platform backlog (planned/in-progress/done across all modules and cross-cutting concerns) |
  ```

- [ ] **Step 3: Update the Current state note** (around line 112) to add `See [`docs/backlog/README.md`](docs/backlog/README.md) for the live status of every module.`

- [ ] **Step 4: Commit:**
  ```bash
  git add README.md
  git commit -m "docs(readme): point to docs/backlog/ as live status surface"
  ```

### Task 3.20: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Sub-steps:**

- [ ] **Step 1: Find the references to the 05_17 backlogs:**
  ```bash
  grep -nE 'backlog_05_17|agent_backlog|graph_backlog|ingestion_backlog' CLAUDE.md
  ```

- [ ] **Step 2: Replace each reference** with a single pointer to `docs/backlog/README.md`. Specifically the line that reads:
  ```markdown
  Verify behavior by reading the code and tests, and use `backend/README.md` § Current State plus the module backlog docs (`docs/agent_backlog_05_17.md`, `docs/graph_backlog_05_17.md`, `docs/ingestion_backlog_05_17.md`) for production-readiness gaps.
  ```
  Replace with:
  ```markdown
  Verify behavior by reading the code and tests, and use `backend/README.md` § Current State plus `docs/backlog/README.md` (and the per-module files it links) for production-readiness gaps and dependency-ordered work items.
  ```

- [ ] **Step 3: Commit:**
  ```bash
  git add CLAUDE.md
  git commit -m "docs(claude): point CLAUDE.md to docs/backlog/ as gap source"
  ```

### Task 3.21: Update `.github/copilot-instructions.md`

**Files:**
- Modify: `.github/copilot-instructions.md`

**Sub-steps:**

- [ ] **Step 1: Grep:**
  ```bash
  grep -nE 'backlog_05_17|agent_backlog|graph_backlog|ingestion_backlog' .github/copilot-instructions.md
  ```

- [ ] **Step 2: Replace** any references with `docs/backlog/README.md`. Phrasing should mirror the change in Task 3.20.

- [ ] **Step 3: Commit:**
  ```bash
  git add .github/copilot-instructions.md
  git commit -m "docs(copilot): point copilot-instructions to docs/backlog/"
  ```

### Task 3.22: Update `backend/README.md` and `chili_app/README.md`

**Files:**
- Modify: `backend/README.md`
- Modify: `chili_app/README.md`

**Sub-steps:**

- [ ] **Step 1: backend/README.md** — find the Current State section. Add a paragraph after it:
  ```markdown
  For the live, dependency-ordered list of production-readiness work per backend module, see [`docs/backlog/README.md`](../docs/backlog/README.md) and the per-module files (`docs/backlog/agent.md`, `docs/backlog/graph.md`, etc.).
  ```

- [ ] **Step 2: chili_app/README.md** — find the equivalent Current State section. Add:
  ```markdown
  For the live, dependency-ordered list of production-readiness work for the SPA, see [`docs/backlog/frontend.md`](../docs/backlog/frontend.md) (rolled up in [`docs/backlog/README.md`](../docs/backlog/README.md)).
  ```

- [ ] **Step 3: Commit:**
  ```bash
  git add backend/README.md chili_app/README.md
  git commit -m "docs: point module READMEs to docs/backlog/ for live gap status"
  ```

### Task 3.23: Final consistency pass + script test run

**Sub-steps:**

- [ ] **Step 1:** Run the consistency pass in check mode — should be clean now:
  ```bash
  python scripts/backlog_consistency.py --check
  echo "exit=$?"
  ```
  Expected: `exit=0`.

- [ ] **Step 2:** Run the script's test suite with coverage:
  ```bash
  pytest tests/scripts/test_backlog_consistency.py --cov=scripts.backlog_consistency --cov-report=term-missing
  ```
  Expected: all green, coverage ≥ 85%.

- [ ] **Step 3:** If either fails, fix and commit. If both pass, no commit needed — the work is verified.

### Task 3.24: Handoff to the user

**Sub-steps:**

- [ ] **Step 1: Summarize what was produced:**
  ```bash
  git log --oneline origin/prod..HEAD
  wc -l docs/backlog/*.md
  python scripts/backlog_consistency.py --check 2>&1 | tail -20
  ```

- [ ] **Step 2: Report to the user:**
  > "Backlog complete on branch `worktree-backlog-design-spec`. N commits ahead of `prod`. Total of M stories across 24 files. Critical path weight: W. Ready set: K stories. Consistency pass clean.
  >
  > To merge into `prod`:
  > ```bash
  > git checkout prod
  > git merge worktree-backlog-design-spec
  > ```
  > Or to inspect first:
  > ```bash
  > git diff prod..worktree-backlog-design-spec --stat
  > ```
  > To remove the worktree once merged: use `ExitWorktree` with `action: remove`."

- [ ] **Step 3: Do NOT auto-merge or auto-exit the worktree.** The user controls integration.

---

## Self-review

**Spec coverage check:**
- §2 End state targeted: drives Wave 1/2 epic scope (covered by audits that read §14.2).
- §3 Decisions locked: enforced by Wave 2 subagent prompts and the consistency script.
- §4 Artifact tree: Task 1.0 bootstraps; Tasks 2.x produce final files; Task 2.5 cleans working files. ✓
- §5 Story format: Task 2.1's template includes the format verbatim; field rules enforced. ✓
- §6 DAG mechanics: Tasks 3.3 (prereq refs), 3.5 (cycles), 3.6 (status invariants), 3.8–3.9 (Unblocks), 3.10–3.11 (ready/critical). ✓
- §7 Master index: Task 3.14 (curated parts), Task 3.12 (auto sections). ✓
- §8 Consistency script: Tasks 3.1–3.13 (TDD); Task 3.16 (CI hook). ✓
- §9 Disposition: Tasks 3.17 (05_17 backlogs), 3.18 (planning), 3.19 (README), 3.20 (CLAUDE.md), 3.21 (copilot), 3.22 (module READMEs). ✓
- §10 Wave 1: Tasks 1.0–1.4 including the hard approval gate at 1.4. ✓
- §10 Wave 2: Tasks 2.0–2.5. ✓
- §10 Wave 3: Tasks 3.1–3.24. ✓
- §11 Scope excluded: not implemented (correctly absent). ✓

**Placeholder scan:** no `TBD`, `TODO`, `implement later`, or "fill in details" phrases. All script tasks ship full code. All template substitutions have concrete per-row values.

**Type consistency check:**
- `Story` dataclass introduced in Task 3.1 header; same shape used through 3.13. ✓
- `parse_file`/`parse_all` signatures consistent across uses. ✓
- `rewrite_unblocks` and `rewrite_readme` both take `check_only: bool`. ✓
- `Story.estimated_size` is a `str` (`"S"|"M"|"L"|"XL"`); `SIZE_ORDER` (Task 3.10) and `SIZE_WEIGHT` (Task 3.11) both map from `str`. ✓
- ID format regex `r"^_?[a-z]+\.\d+$"` (Task 3.2) matches the convention used in Wave 1 ID allocation (Task 1.3 Step 2). ✓

**Approval gate:** Task 1.4 is explicitly a HALT — the plan cannot proceed past it without user approval. The execution sub-skills (subagent-driven-development, executing-plans) honor checkbox-blocking tasks. ✓

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-complete-backlog.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Best for this plan because Wave 1 and Wave 2 already dispatch subagents per task (the sub-skill naturally composes); Wave 3 TDD tasks each map cleanly to one subagent dispatch with a review checkpoint.

2. **Inline Execution** — execute tasks in this session using `executing-plans`. Faster for Wave 3 (script TDD doesn't need fresh context per task) but the parallel subagent dispatches in Waves 1 and 2 still happen the same way.

Which approach?
