# /domain-packs/medicareffsclaims/eval_dataset_spec.md
DomainPackId: medicareffsclaims
Version: 0.1.0

# Goal
- Validate that top-K queues are useful to investigators and that explanations/evidence bundles are actionable before go-live and during weekly ops.

# Unit of review (labeling grain)
- Primary: provider_id (optionally provider_id × claim_type) for provider-risk queues.
- Secondary (optional): claimline clusters for duplicate/near-duplicate indicators.

# Leakage controls (required)
- Time-based split: define a scoring period (e.g., last 4–8 weeks) and ensure any derived labels/outcomes are from after the scored window or are investigator judgments captured in the review UI.
- Do not sample using downstream enforcement outcomes if those outcomes depend on the same queue being evaluated (self-fulfilling selection bias).

# Sampling design (v0.1)
- Stratify by: indicator_id, severity/priority band, and (optionally) geography/specialty peer group to ensure coverage of different failure modes.
- Include three strata: (A) high-risk top-K, (B) mid-risk band, (C) random baseline controls, sized to investigator capacity.

# Labeling protocol (investigator/SME)
- Outcome label (required): suspicious | not_suspicious | insufficient_evidence.
- Reason tags (required): expected_behavior | data_quality_issue | policy_program_change | model_issue | explanation_issue | needs_more_info | other.
- Explanation usefulness (required): actionable | unclear | not_actionable, using the core explanation rubric.
- Evidence adequacy (required): enough | missing | contradictory, aligned to evidence completeness rules.

# Primary metrics (queue-centric)
- Precision@K (proxy): proportion of top-K labeled “suspicious” among reviewed items, reported overall and by indicator.
- Explanation actionable rate: share of reviewed items rated “actionable,” overall and by indicator.
- Insufficient evidence rate / missing critical evidence rate: used as a safety/trust gate and a data-readiness signal.

# Secondary metrics (ops + stability)
- Time-to-triage / queue aging (p50/p90) and investigator throughput, to ensure the queue improves workflow rather than creating backlog.
- Drift/stability: score distribution drift and top-feature drift for each indicator’s referenced features, reviewed weekly.

# Acceptance (pilot gate)
- Thresholds are set by PI Ops/investigator leads (capacity-dependent) and recorded in the core evaluation plan; indicators failing explanation/evidence thresholds remain in pilot or are paused.

# Deliverables
- A versioned CSV (or table) of reviewed cases with: entity id, indicator ids, score/priority, evidence completeness flag, investigator labels, and timestamps.
- A short evaluation report (core template) summarizing Precision@K, explanation usefulness, top false-positive themes, and recommended tuning/pause actions.
