# C01 — Use-case Canvas (v0.1)

## 1) Use-case identification
- Use-case name:
- Domain pack (e.g., medicare-ffs, marketplace-enrollment, medicaid-dental-vision):
- Use-case version:
- Owner (PI Ops):
- SME lead:
- Security/Privacy POC:
- Date:

## 2) Problem statement
- What PI problem are we trying to solve (1–3 sentences)?
- Who is the primary user (investigator, queue owner, etc.)?
- What decision/workflow step will this support (triage, prioritization, evidence prep, QA)?

## 3) Entities and outcomes
- Primary entity (provider, beneficiary, claim, agent/broker, plan, location, etc.):
- Secondary entities (optional):
- Target outcome (what is “positive” for review/triage purposes)?
- Non-goals (explicitly list what the system will not do):

## 4) Data sources (minimum viable)
List the specific datasets/tables/feeds and owners.
- Source 1:
- Source 2:
- Source 3:

Constraints:
- Latency/freshness requirement:
- Lookback window:
- Known data quality issues:

## 5) Indicator approach
- Indicator type(s): rule-based / statistical peer / time-series / graph / ML / composite
- Why this approach is appropriate (2–4 bullets):
- Expected reason codes (initial draft list):

## 6) Evidence and explainability needs
- Minimum evidence artifacts required for an investigator to act:
- Evidence bundle must include:
  - Time window:
  - Related entities/relationships (if any):
  - Source-record pointers:

Guardrails:
- “What this does NOT mean” statements (draft 3–5 bullets):
- Conditions that force “INSUFFICIENT_EVIDENCE”:

## 7) Workflow and integration
- Triage queue owner:
- Case management integration: none / export / write-back / embedded UI
- Investigator action states (draft):
- Feedback to capture (labels, reason tags, usefulness, evidence adequacy):

## 8) Risks, harms, and mitigations
Risks to consider:
- False positives driving wasted effort:
- Bias/fairness concerns:
- Privacy/security concerns:
- Misuse/over-reliance risk:

Mitigations:
- Human-in-the-loop control points:
- Training/UX guardrails:
- Monitoring triggers:
- Pause/discontinue authority:

## 9) Success metrics and targets
Operational:
- Throughput impact (cases/day, hours saved/week):
- Precision@K / yield@K target:
- Time-to-evidence target:

Quality:
- Explanation usefulness target:
- Evidence adequacy target:
- Drift/instability tolerance:

## 10) Launch plan (v0.1)
- MVP scope (what ships in v0.1):
- What is deferred (v0.2+):
- Pilot cohort (which region/program/team):
- Labeling plan (who labels, how many, by when):
- Go-live decision date:

## 11) Approvals
- PI Ops Lead:
- SME Lead:
- Security/Privacy:
- Analytics/ML Lead:
- Date approved:
