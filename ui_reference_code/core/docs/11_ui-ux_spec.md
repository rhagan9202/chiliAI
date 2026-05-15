# UI/UX Specification (Core) — v0.1

## Purpose
Defines minimum screens, user stories, permissions, and integration patterns for the accelerator UI.

The UI must:
- support investigator triage and evidence review
- capture structured feedback for evaluation and monitoring
- enforce guardrails (triage support, not automation)
- provide auditable change control and pause/resume controls

## Personas
- PI Ops Lead (queue owner)
- Investigator (case reviewer)
- Investigator Lead (quality owner)
- Analytics/ML (indicator/model owner)
- Security/Privacy (audit owner)

## Screens (minimum)
1) Use-case canvas (SME framing)
2) Indicator builder (indicator definition)
3) Risk dashboard (entity-level)
4) Triage queue (ranked items with filters)
5) Evidence bundle viewer (timeline + raw events + network subgraph where applicable)
6) Feedback capture (labels + reason tags + usefulness)
7) Indicator health dashboard (quality + drift + evidence missingness)
8) Change log & approvals (governance)
9) Pause/resume/retire controls

## Permission matrix (summary)
- PI Ops: view all, manage queues, approve/pause
- Investigators: view queue/evidence, submit feedback, change case status
- Analytics: view all, propose changes, run eval and drift jobs
- Security/Privacy: view audit/access logs, approve access controls, restrict access
- Admin: manage users/roles

## Required UI fields
UI must align to `/core/ui/fields_dictionary.md`.

## Integration patterns
- Option A: Native UI + exports to case management
- Option B: Embedded widget into existing case tool
- Option C: API-only integration (case tool renders UI)

Minimum integration requirement:
- case_id linking to external case reference if used
- ability to write back investigator feedback

## Usability requirements
- Explanations must be concise and evidence-linked.
- Evidence bundle must load quickly and show completeness status.
- “What this does NOT mean” must be visible for high-sensitivity indicators.

## Accessibility and audit
- All key actions produce audit events (view evidence, submit feedback, approve changes, pause indicators).
