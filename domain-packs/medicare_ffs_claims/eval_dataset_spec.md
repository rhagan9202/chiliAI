# /domain-packs/medicareffsclaims/eval_dataset_spec.md
DomainPackId: medicareffsclaims [file:1]
Version: 0.1.0 [file:1]

# Goal
- Validate that top-K queues are useful to investigators and that explanations/evidence bundles are actionable before go-live and during weekly ops. [file:1]

# Unit of review (labeling grain)
- Primary: provider_id (optionally provider_id × claim_type) for provider-risk queues. [file:1]
- Secondary (optional): claimline clusters for duplicate/near-duplicate indicators. [file:1]

# Leakage controls (required)
- Time-based split: define a scoring period (e.g., last 4–8 weeks) and ensure any derived labels/outcomes are from after the scored window or are investigator judgments captured in the review UI. [file:1]
- Do not sample using downstream enforcement outcomes if those outcomes depend on the same queue being evaluated (self-fulfilling selection bias). [file:1]

# Sampling design (v0.1)
- Stratify by: indicator_id, severity/priority band, and (optionally) geography/specialty peer group to ensure coverage of different failure modes. [file:1]
- Include three strata: (A) high-risk top-K, (B) mid-risk band, (C) random baseline controls, sized to investigator capacity. [file:1]

# Labeling protocol (investigator/SME)
- Outcome label (required): suspicious | not_suspicious | insufficient_evidence. [file:1]
- Reason tags (required): expected_behavior | data_quality_issue | policy_program_change | model_issue | explanation_issue | needs_more_info | other. [file:1]
- Explanation usefulness (required): actionable | unclear | not_actionable, using the core explanation rubric. [file:1]
- Evidence adequacy (required): enough | missing | contradictory, aligned to evidence completeness rules. [file:1]

# Primary metrics (queue-centric)
- Precision@K (proxy): proportion of top-K labeled “suspicious” among reviewed items, reported overall and by indicator. [file:1]
- Explanation actionable rate: share of reviewed items rated “actionable,” overall and by indicator. [file:1]
- Insufficient evidence rate / missing critical evidence rate: used as a safety/trust gate and a data-readiness signal. [file:1]

# Secondary metrics (ops + stability)
- Time-to-triage / queue aging (p50/p90) and investigator throughput, to ensure the queue improves workflow rather than creating backlog. [file:1]
- Drift/stability: score distribution drift and top-feature drift for each indicator’s referenced features, reviewed weekly. [file:1]

# Acceptance (pilot gate)
- Thresholds are set by PI Ops/investigator leads (capacity-dependent) and recorded in the core evaluation plan; indicators failing explanation/evidence thresholds remain in pilot or are paused. [file:1]

# Deliverables
- A versioned CSV (or table) of reviewed cases with: entity id, indicator ids, score/priority, evidence completeness flag, investigator labels, and timestamps. [file:1]
- A short evaluation report (core template) summarizing Precision@K, explanation usefulness, top false-positive themes, and recommended tuning/pause actions. [file:1]
