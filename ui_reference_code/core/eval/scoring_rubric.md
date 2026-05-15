# Evaluation Scoring Rubric (v0.1)

## Purpose
Defines how to evaluate Program Integrity XAI indicators and use cases for v0.1, with emphasis on:
- Operational effectiveness (Precision@K, Yield@K)
- Efficiency (investigator effort)
- Explanation and evidence quality
- Stability and safety

This rubric is applied in the C06 Evaluation Plan and summarized in the evaluation report.

---

## 1. Scope

- Level:
  - Indicator-level evaluation
  - Use-case-level evaluation (aggregate across indicators)
- Data:
  - Test set defined in `testset_format.csv` for each domain pack/use case.
- Label sources:
  - Investigator feedback (short-lag).
  - Audit or case outcomes (longer-lag, when available).

---

## 2. Metrics

### 2.1 Effectiveness

1) Precision@K (P@K)
- Definition:
  - Sort entities by descending indicator score.
  - Take top K and compute fraction with positive label (e.g., true positives).
- Purpose:
  - Measures how many of the top-K items are “worth investigator time” in a heavily imbalanced fraud scenario.
- Example:
  - If top 100 items contain 30 true positives, Precision@100 = 0.30.

2) Yield@K
- Definition:
  - Among top-K entities investigated, proportion that led to meaningful outcomes (e.g., audit referrals, payment adjustments, corrective actions).
- Purpose:
  - Captures operational value, not just label alignment.

3) Relative lift vs baseline
- Definition:
  - Compare Precision@K (or Yield@K) vs baseline queueing or targeting.
- Purpose:
  - Quantifies improvement over current practice.

### 2.2 Efficiency

4) Time-to-evidence
- Metric:
  - Median and distribution of time (seconds) to load evidence bundle for a case.
- Target:
  - v0.1: e.g., median ≤ 3 seconds for typical cases (client-specific).

5) Investigator effort proxy
- Metric:
  - Median minutes spent per case (from first_viewed_at to case closed), optionally segmented by severity and indicator.
- Interpretation:
  - Supports capacity planning and trade-offs between P@K and workload.

### 2.3 Explanation and evidence quality

6) Explanation usefulness rate
- Metric:
  - Average `explanation_usefulness` score (1–5) per indicator.
  - Percentage of feedback with usefulness ≥ 4.
- Interpretation:
  - Higher is better; 4–5 indicates explanations are actionable.

7) Evidence adequacy rate
- Metric:
  - Average `evidence_adequacy` score (1–5).
  - Percentage of feedback with adequacy ≥ 4.
- Complement:
  - `missing_critical_evidence_rate` from system-level checks.

### 2.4 Stability and safety

8) Stability@K
- Definition:
  - Intersection of entities between consecutive top-K lists / K.
- Purpose:
  - Detects unexplained volatility in triage targets over time.

9) Drift alert compliance
- Metric:
  - Number of drift alerts by severity and response time.
- Purpose:
  - Ensures alerts are acted on within defined SLAs.

---

## 3. Rubric bands (example thresholds)

These bands are reference values; actual thresholds are defined in C06 per use case.

### 3.1 Effectiveness bands

- Precision@K:
  - Green: ≥ target (e.g., ≥ 0.30) and lift > baseline.
  - Amber: within 10–20% of target; remediation plan required.
  - Red: < 80% of target or below baseline.

- Yield@K:
  - Green: meets or exceeds target.
  - Amber: near target but inconsistent.
  - Red: consistently below target.

### 3.2 Explanation/evidence bands

- Explanation usefulness avg:
  - Green: ≥ 4.0
  - Amber: 3.0–3.9
  - Red: < 3.0

- Evidence adequacy avg:
  - Green: ≥ 4.0 and missing_critical_evidence_rate low.
  - Amber: 3.0–3.9 or occasional spikes in missing evidence.
  - Red: < 3.0 or persistent missing_critical_evidence_rate above threshold.

### 3.3 Stability and safety bands

- Stability@K:
  - Green: ≥ 0.8 (with no major policy or configuration changes).
  - Amber: 0.5–0.79, investigation needed.
  - Red: < 0.5 without clear explanation.

- Drift handling:
  - Green: Drift alerts occur and trigger timely, documented responses.
  - Red: Severe drift alerts ignored or unresolved within SLA.

---

## 4. Accept/conditional/no-go decisions

Use this rubric to support:

- Go:
  - Meets or exceeds key thresholds.
  - Explanation and evidence quality in Green or high Amber.
  - Monitoring and pause controls in place.

- Conditional Go:
  - Some metrics in Amber; remediation items and timelines documented.
  - Clear guardrails to mitigate risk (e.g., limited pilot cohort).

- No-Go:
  - One or more critical metrics in Red without acceptable mitigation.
  - Known safety or compliance concerns unaddressed.

---

## 5. Documentation and traceability

- Each evaluation run must:
  - Reference testset version.
  - Record config snapshot and code versions.
  - Store metrics and decision in a structured report (see `eval_report_template.md`).
- Rubric updates:
  - Changes to thresholds or bands must go through change control (C09).
