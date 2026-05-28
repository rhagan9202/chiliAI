---
name: refresh-requirements
description: 'Run a full refresh of the canonical chiliAI product requirements at docs/project/planning/requirements.md by invoking the requirements_gatherer agent with a standard refresh preamble. Use when the user types /refresh-requirements, asks to "refresh requirements", "redo the requirements doc", "rebuild the requirements list", or wants a from-scratch product-scope audit. Produces an updated requirements artifact with preserved REQ-IDs, 3–5 improvement suggestions, and a blocking-open-questions review gate.'
argument-hint: 'Optional focus area (e.g. "auth", "ingestion"); omit for a full-product refresh.'
---

# Refresh Requirements

## When to Use
- The user explicitly invokes `/refresh-requirements`.
- The user asks to refresh, rebuild, audit, or redo the canonical product requirements.
- A significant planning milestone has landed (new module, new domain, scope change) and the requirements artifact at `docs/project/planning/requirements.md` is suspected stale.
- Do NOT use for code-level changes, sprint planning, or module backlog edits.

## Outcome
An updated `docs/project/planning/requirements.md` (written only after explicit user approval), produced by the `requirements_gatherer` agent following its full approach including:
- Delegating planning-tier exploration to the `Explore` subagent.
- Preserving stable `REQ-<AREA>-<NNN>` IDs from the prior version.
- Blocking approval on any unresolved `[OPEN QUESTION]` items.
- Surfacing 3–5 product-level improvement suggestions.

## Procedure

1. **Detect optional focus argument.** If the user passed a focus area (e.g. `/refresh-requirements auth`), capture it; otherwise treat the run as a full-product refresh.

2. **Hand off to the `requirements_gatherer` agent.** Invoke it as a subagent and supply the following standard refresh preamble verbatim (substitute `<FOCUS>` with the captured focus argument or the literal string `full product`):

   > **Refresh preamble (standard)**
   >
   > Run a complete refresh of the canonical chiliAI product requirements.
   >
   > - Scope: `<FOCUS>`.
   > - Treat the existing `docs/project/planning/requirements.md` (if present) as the prior version. Preserve every existing `REQ-<AREA>-<NNN>` ID; only append new IDs for genuinely new requirements; mark removed scope as deprecated rather than deleting silently.
   > - Delegate exploration to the `Explore` subagent in `thorough` mode. Restrict Explore to planning-tier sources only: root `README.md` and `CLAUDE.md`; `.github/copilot-instructions.md` and `.github/instructions/**`; `docs/architecture.md`, `docs/onboarding.md`, `docs/security_checklist.md`, `docs/system_architecture_diagram.md`; `docs/planning/**`; `docs/superpowers/plans/**` and `docs/superpowers/specs/**` (titles, goals, architecture sections only); module-level `README.md` files; existing module backlog summaries. Explicitly exclude source code, tests, and per-task implementation detail.
   > - Synthesize findings into the canonical structure: Product Vision, Target Users & Domains, Functional Requirements (grouped by capability area with stable IDs), Non-Functional Requirements, Integration & Adapter Requirements, Out of Scope, Assumptions, Source Material.
   > - Produce 3–5 product-level improvement suggestions (scope/product only — never code-level).
   > - Resolve every `[OPEN QUESTION]` with the user before requesting approval; open questions block approval. `[ASSUMPTION]` items are non-blocking but must be surfaced for confirmation.
   > - Request explicit approval (`approve / revise / reject`) before writing. On approval, write `docs/project/planning/requirements.md`, creating parent directories if needed, and stamp it with today's date and an incremented version number.

3. **Do not bypass the agent's gates.** This skill is a thin invocation wrapper. It MUST NOT write `docs/project/planning/requirements.md` itself, MUST NOT skip the open-questions resolution loop, and MUST NOT auto-approve on the user's behalf.

4. **Report back.** After the `requirements_gatherer` returns control, surface a one-paragraph summary to the user noting: whether the artifact was written, the version number, the count of net-new / changed / deprecated requirements, and any `[ASSUMPTION]` items that need ongoing tracking.

## Constraints
- ONLY invoke the `requirements_gatherer` agent. Do not directly read sources, edit files, or invoke `Explore` from this skill.
- DO NOT alter the agent's approach, structure, or approval gates via the preamble — the preamble is a *trigger*, not an override.
- DO NOT run unattended; this skill always returns control to the user for approval.

## Related
- Agent: [`requirements_gatherer.agent.md`](../../agents/requirements_gatherer.agent.md) — owns the artifact and the approach.
- Artifact (output): `docs/project/planning/requirements.md`.
