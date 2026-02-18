# C02 — Indicator Builder Template (v0.1)

## 1) Indicator identity
- Indicator name:
- Indicator ID (stable):
- Domain pack:
- Use-case version:
- Owner (Analytics/ML):
- SME reviewer:
- Created date:
- Status: draft / pilot / prod / paused / retired

## 2) Business rationale
- What fraud/waste/abuse behavior or risk pattern does this represent?
- Why does it matter operationally (cost, harm, compliance, workload)?

## 3) Entity and scope
- Primary entity type:
- Unit of scoring: entity / entity-month / claim / episode / enrollment event
- Inclusion criteria:
- Exclusion criteria:

## 4) Logic / model definition
Select one (or hybrid):
- Rule logic:
- Statistical / peer logic:
- Time-series logic:
- Graph/network logic:
- ML model logic:

Implementation notes:
- Feature inputs (list with definitions + windows):
- Handling missingness:
- Thresholding / calibration approach:
- Score range and interpretation:

## 5) Output contract (required)
- score:
- severity (low/med/high or numeric band):
- reason_codes (top N):
- evidence_bundle_id (or pointer):
- recommended_next_steps (1–3):
- confidence / evidence_completeness:

## 6) Reason codes (draft catalog)
Provide reason codes that are stable and user-facing.
- RC001:
- RC002:
- RC003:

Mapping:
- Which features/conditions produce each reason code?

## 7) Evidence bundle requirements
Minimum evidence required to show:
- Time window and timeline events:
- Source record pointers (table + key + date):
- Comparators/benchmarks shown:
- Related entities shown (optional network slice):

Evidence completeness rules:
- Required evidence fields:
- If missing, set confidence to:
- If missing critical evidence, force reason code:
- SLA for evidence generation:

## 8) UX copy (required)
- One-sentence explanation for investigators:
- “What this does NOT mean” (3–5 bullets):
- Avoided language (e.g., “fraud confirmed”):

## 9) Evaluation plan (indicator-level)
- Test set definition:
- Labeling guidance:
- Primary metric(s): P@K, yield@K, explanation usefulness, evidence adequacy
- Acceptance threshold(s):
- Known failure modes to test:

## 10) Monitoring plan (indicator-level)
Data health:
- Freshness check:
- Missingness check:
- Volume/outlier checks:

Model/logic health:
- Stability@K:
- Drift thresholds:
- Alert routing:

Ops actions:
- When to tune thresholds:
- When to pause:
- When to retire:

## 11) Dependencies & owners
- Upstream data dependencies:
- Downstream consumers:
- On-call / escalation:
- Privacy/security review needed? yes/no

## 12) Approvals
- SME approval:
- PI Ops approval:
- Security/Privacy approval (if required):
- Go-live date:
