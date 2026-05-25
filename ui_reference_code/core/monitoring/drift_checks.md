# Drift Checks Specification (v0.1)

## Purpose
Defines standard drift checks for indicators used in the Program Integrity XAI Accelerator, covering:
- Data drift (inputs)
- Output drift (scores, severity)
- Performance drift (where labels exist)
- Operational stability (Stability@K)

Applies to both ML and non-ML indicators (rules, peers, time-series, graph).

---

## 1. General principles

- Label-agnostic first:
  - Use input and output distributions to detect changes even when labels lag.
- Lag-aware performance checks:
  - When labels become available (e.g., after investigations or audits), compute performance metrics over rolling windows.
- Stability:
  - Track Stability@K as a proxy for the consistency of “top suspects” over time.
- Actionability:
  - Each drift check must map to a recommended response (observe, investigate, tune, or pause).

---

## 2. Data drift checks (inputs)

### 2.1 What to monitor
For each indicator’s feature set:
- Marginal distributions for key features:
  - Numerical: claim amounts, utilization counts, ratios.
  - Categorical: HCPCS codes, place-of-service, provider types, agent categories, benefit types.
- Derived aggregates:
  - Peer norms (e.g., z-scores against peers).
  - Temporal counts (e.g., claims per month).

### 2.2 Methods
- Statistical tests:
  - Kolmogorov–Smirnov for continuous features.
  - Population stability index (PSI) for numeric/ordinal features.
  - Chi-square or Jensen–Shannon divergence for categorical.
- Monitoring windows:
  - Reference window (e.g., last 3 months of baseline).
  - Current window (e.g., last 1–2 weeks).

### 2.3 Thresholds (illustrative starting points)
- PSI:
  - < 0.1: minor/expected.
  - 0.1–0.25: moderate → investigate if persistent.
  - > 0.25: significant → trigger investigation and potential pause/tune.
- KS statistic:
  - < 0.1: minor.
  - ≥ 0.1: flag for review, especially for critical features.

---

## 3. Output drift checks (scores & severity)

### 3.1 What to monitor
Per indicator, per period:
- Score distribution:
  - Mean, variance, quantiles (e.g., 10th, 50th, 90th).
- Severity distribution:
  - Counts per band (low/medium/high/critical).
- Queue impact:
  - Number and fraction of entities above triage threshold.

### 3.2 Methods
- Compare current window to baseline using:
  - PSI on score buckets.
  - KS test on raw scores.
  - Simple ratio checks for severity counts (e.g., >2x baseline for high severity).

### 3.3 Trigger examples
- High-severity items more than double baseline for ≥ 2 consecutive windows.
- Score distributions shift significantly (PSI > 0.25 or KS > 0.1).
- Sudden collapse in high severity (e.g., near-zero flags) not aligned with intentional threshold changes.

---

## 4. Performance drift checks (when labels available)

### 4.1 What to monitor
For each indicator where downstream outcomes or labels are available:
- Precision@K over rolling windows.
- Yield@K (e.g., proportion of investigated cases leading to actions).
- False positive rates (based on feedback_label or confirmed outcomes).

### 4.2 Methods
- Compare current period metrics against:
  - Launch baseline.
  - Rolling 3–6 month average.
- Statistical significance (where sample size allows):
  - Confidence intervals or simple control chart rules.

### 4.3 Trigger examples
- Precision@K drops by more than 30% relative to baseline and stays low for 2+ periods.
- Yield@K consistently below minimum acceptable threshold.
- Feedback shows growing false positive patterns for the same reason codes.

---

## 5. Stability@K checks

### 5.1 Definition
- Stability@K = size of intersection between top-K entities in consecutive runs / K.

### 5.2 What to monitor
- Compute Stability@K for key values of K (e.g., 100, 500, 1000) for each indicator.
- Track over time to detect unexplained volatility.

### 5.3 Trigger examples
- Stability@K drops sharply (e.g., from >0.8 to <0.4) without any configuration changes.
- Sustained low stability in a relatively stable environment.

---

## 6. Indicator-type specific notes

### 6.1 Rule-based indicators
- Focus:
  - Data drift on fields driving rules.
  - Output drift from policy or coding changes (e.g., new codes, new rules).
- Additional checks:
  - Newly frequent codes slipping outside rule logic (coverage holes).

### 6.2 Peer-based indicators
- Focus:
  - Changes in peer group composition.
  - Changes in global norms (e.g., pandemic effects, policy shifts).
- Additional checks:
  - Drift in peer group distribution vs overall population.

### 6.3 Time-series indicators
- Focus:
  - Level shifts, seasonal changes, or changes in volatility.
- Methods:
  - Forecast residual monitoring.
  - Control charts on key aggregates per entity.

### 6.4 Graph/network indicators
- Focus:
  - Changes in graph density, degree distributions, or motif frequencies.
- Methods:
  - Compare distributions of node degrees, edge types, and connected components.

---

## 7. Responses to drift

### 7.1 Triage levels
- Informational:
  - Mild drift; monitor and document.
- Investigate:
  - Moderate drift; perform root cause analysis and check for upstream changes.
- Tune:
  - Adjust thresholds or logic; update documentation and evaluation.
- Pause:
  - For severe drift affecting safety or usefulness, use pause controls and perform deeper evaluation.

### 7.2 Documentation
- All drift events above “informational” should be:
  - Logged as monitoring events.
  - Summarized in weekly ops review.
  - Linked to change requests or incident tickets when actions are taken.

---

## 8. Governance alignment
- Drift thresholds and responses must be defined per indicator in:
  - Indicator builder (C02) monitoring section.
  - Evaluation plan (C06).
- Drift alerts are a valid trigger for:
  - Change requests (C09).
  - Pause/resume actions.
