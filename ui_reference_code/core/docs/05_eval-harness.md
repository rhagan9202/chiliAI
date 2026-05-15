# Evaluation Harness (Core) — v0.1

## Purpose
Defines the standard evaluation harness for indicators and queues across domain packs.

## What we evaluate
1) Utility: top-K yield for limited investigator capacity
2) Trust: explanation and evidence usability
3) Stability/safety: performance over time, drift detection, and safe operations

## Pre-go-live evaluation gates
Gate 1: Data readiness (C05 completed; data quality checks)
Gate 2: Test set creation (time-aware split; stratified sampling)
Gate 3: Human labeling plan (investigator labels + reason tags)
Gate 4: Metrics and acceptance (P@K, actionable explanation rate, evidence adequacy)
Gate 5: Risk screening refresh (C03) if scope changes

## Metrics (minimum)
Primary:
- Precision@K (P@K) for queue(s)
- Yield per hour (or proxy)
Secondary:
- Explanation actionable rate
- Evidence adequacy rate
- Missing evidence rate
- Stability (STAB@K) across periods

## Post-go-live continuous evaluation
Weekly:
- compute precision proxy from labels
- track explanation usability and evidence adequacy
- run drift checks
- trigger tuning or pause/discontinue as needed

## Leakage/overfitting controls
- time-based splits
- holdout window for promotion decisions
- document any tuning in C09
