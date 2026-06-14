# Demoable Workflow Increments Design

> Status: Approved story set (2026-06-14). This spec decomposes the current routed analyst workflow into four demoable development increments.

## Goal

Make each sprint end with a visible workflow improvement that can be demonstrated without presenter-only explanations. The sequence is intentionally cumulative:

1. Ingestion to investigation handoff.
2. Alert to case loop.
3. Evidence and contextual RAG.
4. Operational dashboard and demo polish.

## Current State

The UI currently exposes concrete routes for dashboard, alert feed, investigation, cases, knowledge bases/ingestion, policy, RAG chat, and configuration. Ingestion is the strongest visible flow: users can create or select a knowledge base, submit documents or records, validate input, and inspect run history. Downstream work is present but less connected: investigation, alert triage, case management, and RAG chat are separate screens with limited explicit handoff.

Known future-development areas stay outside these increments unless a sprint explicitly pulls one into the demo path:

- Side-panel AI assistant composer.
- Collection analytics views.
- Global graph entity detail drawer.
- WebSocket-specific alert/pipeline UI.
- Configuration mutation/reload endpoints.

## Sprint 1: Ingestion To Investigation Handoff

**Demo goal:** Create or select a knowledge base, submit data, watch run progress, then move directly into investigation with the same knowledge base context.

**Stories:**

1. As an analyst, I can see clear next actions after document or record submission so I know whether to watch runs, investigate entities, or review alerts.
2. As an analyst, I can move from Ingestion Studio to Investigation with the selected KB preserved.
3. As an analyst, I can understand run state in plain language: accepted, queued, running, completed, failed, cancelled.
4. As a PM, I can demo a full ingest-to-investigate path without manually explaining URL state or backend concepts.

**Acceptance criteria:**

- Post-submit actions link to `/investigation?kb=...`, `/alerts?kb=...`, and `/rag-chat?kb=...` where useful.
- Run timeline distinguishes local receipt status from backend workflow status.
- The demo script starts at Knowledge Bases and ends on Investigation scoped to the same KB.

## Sprint 2: Alert To Case Loop

**Demo goal:** Triage a specific alert, inspect evidence, promote that exact alert to a case, update case state, and record durable analyst feedback.

**Stories:**

1. As an analyst, I can act on a specific alert from the alert feed: acknowledge, inspect evidence, investigate entity, or promote to case.
2. As an analyst, I can promote the exact selected alert to a case instead of relying on the first unpromoted alert.
3. As an analyst, I can submit meaningful feedback with selectable label and evidence adequacy, not only a fixed suspicious finding.
4. As a PM, I can refresh the app and show that case status and feedback survived.

**Acceptance criteria:**

- Alert rows expose investigation and case actions for the selected alert.
- Case promotion reflects the selected alert ID.
- Analyst feedback is durable rather than per-process in-memory.
- The demo script starts at Alert Feed and ends with a persisted case containing feedback.

## Sprint 3: Evidence And Contextual RAG

**Demo goal:** From an alert, entity, or case, ask a context-aware RAG question and receive a cited answer that remains connected to the workflow.

**Stories:**

1. As an analyst, I can launch RAG chat from an alert, entity, or case with KB and context preselected.
2. As an analyst, I can ask "why is this high risk?" and get an answer with citations tied to evidence or retrieved content.
3. As an analyst, I can navigate from citations back to evidence, case, or investigation context where possible.
4. As a PM, I can demo the AI assistant as part of the workflow rather than as a disconnected chat page.

**Acceptance criteria:**

- RAG chat accepts contextual launch parameters.
- Chat thread title and seeded prompt context reflect the originating alert, entity, or case.
- The side assistant is either wired to real chat context or visually non-interactive until future development.
- The demo script starts from a case or alert and ends with a cited assistant answer.

## Sprint 4: Operational Dashboard And Demo Polish

**Demo goal:** The dashboard becomes the entry point for a full analyst walkthrough: dashboard to ingest/run, alert, case, and RAG explanation.

**Stories:**

1. As an analyst, I can click dashboard KPIs to open the relevant queue: alerts, cases, workflows, or investigation.
2. As a PM, I can show queue health and unresolved work from the dashboard before drilling into action screens.
3. As an analyst, I can see useful analytics summaries beyond one-off entity views where they support prioritization.
4. As a PM, I can run an end-to-end demo from dashboard to ingest/run to alert to case to RAG explanation.

**Acceptance criteria:**

- Dashboard cards link to real filtered routes.
- Workflow, alert, and case counts match backend data and route targets.
- Future-development areas stay out of the demo path unless implemented by this sprint.
- The demo script starts at Dashboard and completes a full analyst workflow.

## Planning Boundaries

- Each sprint plan must be executable independently after the prior sprint lands.
- Each plan must include focused tests and a demo script.
- Generated OpenAPI and TypeScript contracts must be regenerated after any frontend-consumed Pydantic contract change.
- Full-stack e2e verification must use the real stack, not route mocks, when the workflow itself is the subject under test.
