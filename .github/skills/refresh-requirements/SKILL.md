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

2. **Hand off to the `requirements_gatherer` agent.** Invoke it as a subagent with this trigger prompt (substitute `<FOCUS>` with the captured focus argument or the literal string `full product`):

   > Run a complete refresh of the canonical chiliAI product requirements. Scope: `<FOCUS>`. Follow your standard Approach, Constraints, and Output Format exactly as defined in your agent definition ([`requirements_gatherer.agent.md`](../../agents/requirements_gatherer.agent.md)) — including prior-version REQ-ID preservation, Explore-delegated planning-tier-only exploration, 3–5 product-level improvement suggestions, the blocking open-questions loop, and the explicit approve/revise/reject gate before writing.

   The agent definition is the single source of the refresh procedure — this skill deliberately does not restate it. If the procedure needs to change, change the agent definition, not this file.

3. **Do not bypass the agent's gates.** This skill is a thin invocation wrapper. It MUST NOT write `docs/project/planning/requirements.md` itself, MUST NOT skip the open-questions resolution loop, and MUST NOT auto-approve on the user's behalf.

4. **Report back.** After the `requirements_gatherer` returns control, surface a one-paragraph summary to the user noting: whether the artifact was written, the version number, the count of net-new / changed / deprecated requirements, and any `[ASSUMPTION]` items that need ongoing tracking.

## Constraints
- ONLY invoke the `requirements_gatherer` agent. Do not directly read sources, edit files, or invoke `Explore` from this skill.
- DO NOT alter the agent's approach, structure, or approval gates via the trigger prompt — it is a *trigger*, not an override.
- DO NOT run unattended; this skill always returns control to the user for approval.

## Related
- Agent: [`requirements_gatherer.agent.md`](../../agents/requirements_gatherer.agent.md) — owns the artifact and the approach.
- Artifact (output): `docs/project/planning/requirements.md`.
