# Evaluation Report Template (v0.1)

> This template summarizes evaluation results for a Program Integrity XAI use case or indicator set.
> Keep the narrative concise (2–3 pages plus appendices as needed).

---

## 1. Overview

- Use-case name:
- Domain pack:
- core_version:
- domain_pack_version:
- use_case_version:
- Evaluation owner:
- Date of report:
- Data period evaluated:
- Indicators in scope:

---

## 2. Key questions

- What operational problem is this use case addressing?
- What constitutes a “successful” v0.1 (in terms of metrics and guardrails)?
- What are the key risks and mitigations?

---

## 3. Data and test set

- Test set description:
  - Population and time window.
  - Sampling strategy.
  - Label sources (feedback, audits, proxy outcomes).
- Data quality notes:
  - Any notable limitations (e.g., partial labels, missing fields).
- Link to testset artifact:
  - Path or URI to `testset_format.csv` instance.

---

## 4. Results summary (RAG view)

Use a simple table to communicate banded results.

| Metric                            | Value      | Target/Threshold | Band (G/A/R) | Notes |
|-----------------------------------|------------|------------------|--------------|-------|
| Precision@K (K = ...)             |            |                  |              |       |
| Yield@K                           |            |                  |              |       |
| Time-to-evidence (median, sec)    |            |                  |              |       |
| Explanation usefulness (avg)      |            |                  |              |       |
| Evidence adequacy (avg)           |            |                  |              |       |
| Missing critical evidence rate    |            |                  |              |       |
| Stability@K                       |            |                  |              |       |
| Drift alerts handled within SLA   |            |                  |              |       |

---

## 5. Detailed findings

### 5.1 Effectiveness

- Precision@K:
  - Overall value and confidence interval (where applicable).
  - Comparison to baseline targeting.
- Yield@K:
  - Breakdown by indicator and severity.
- Observations:
  - Which patterns are working well?
  - Where are we seeing false positives?

### 5.2 Efficiency

- Queue and workflow:
  - Time-to-first-view and time-to-close.
  - Workload distribution across investigators.
- Observations:
  - Any bottlenecks or imbalances?
  - Impact on investigator workload.

### 5.3 Explanation and evidence

- Explanation usefulness:
  - Average scores and distribution by indicator.
- Evidence adequacy:
  - Average scores and missing evidence patterns.
- Common themes from qualitative feedback.

### 5.4 Stability and drift

- Stability@K:
  - Values over the evaluation period.
- Drift checks:
  - Notable input/output drift detections.
- Actions taken (if any) during the evaluation.

---

## 6. Risks and limitations

- Data limitations:
  - Missing labels, short time horizon, known biases.
- Model/indicator limitations:
  - Known blind spots, expected failure modes.
- Operational risks:
  - Potential for misinterpretation or misuse.

---

## 7. Recommendations

### 7.1 Go/Conditional/No-Go decision

- Recommended decision (Go / Conditional Go / No-Go).
- Rationale:
  - Reference rubric bands and key findings.

### 7.2 Required follow-ups

- For Conditional Go or Go with caveats:
  - List remediation items (e.g., UX improvements, rule tweaks, additional drift checks).
  - Owners and timelines.

### 7.3 Future enhancements

- Potential v0.2+ improvements:
  - New indicators.
  - Enhanced features or evidence bundling.
  - Additional monitoring or fairness evaluations.

---

## 8. Approvals

- PI Ops Lead:
- SME Lead:
- Analytics/ML Lead:
- Security/Privacy (if applicable):
- Date of approval:

---

## 9. Appendices (optional)

- A. Metric computation details.
- B. Additional charts/tables.
- C. Sample explanations and evidence bundles.
- D. Drift analysis details.
