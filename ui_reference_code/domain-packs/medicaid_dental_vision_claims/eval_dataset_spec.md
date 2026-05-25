# /domain-packs/medicaiddentalvisionclaims/eval_dataset_spec.md
DomainPackId: medicaiddentalvisionclaims
Version: 0.1.0

# Goal
- Confirm that provider/clinic queues surface actionable anomalies with sufficient evidence, and that ring/bundle indicators don’t overwhelm investigators with unusable network output.

# Units of review
- Provider-level: provider_id (rendering and/or billing; configurable).
- Clinicgroup-level (optional): clinicgroup_id for multi-provider ring/organization signals.

# Leakage controls
- Time-based evaluation windows: score on period T; label via investigator review after scoring (and do not backfill labels from actions caused by the same queue without noting selection bias).
- If prior auth is used, ensure the evaluation distinguishes “auth lag/data gap” from true mismatch to avoid false positives.

# Sampling design (v0.1)
- Stratify by: indicator_id, specialty (dental vs vision subtypes if available), geography, and severity band.
- Include (A) top-K per indicator (or per queue), (B) mid-band, and (C) random baseline controls to measure lift.
- For ring indicators, sample both: (i) high-density clusters and (ii) “near miss” clusters to test specificity and evidence completeness.

# Labeling protocol
- Outcome: suspicious | not_suspicious | insufficient_evidence.
- Reason tags: expected_behavior | data_quality_issue | policy_program_change | model_issue | explanation_issue | needs_more_info | other.
- Explanation usefulness: actionable | unclear | not_actionable, with evidence adequacy: enough | missing | contradictory.

# Primary metrics
- Precision@K (proxy) overall and by indicator using investigator outcomes.
- Actionable explanation rate and missing critical evidence rate (hard gate for approving ring indicators).

# Secondary metrics
- Queue aging/throughput, to confirm the accelerator integrates into real casework rather than creating a parallel process.
- Drift: procedure mix drift, utilization drift, peer-group composition drift, and (for ring indicators) node/edge count drift and subgraph size drift.

# Acceptance and gating
- Pilot thresholds are set by PI Ops/investigator leads and documented in the core evaluation plan; indicators failing evidence/explanation thresholds must be paused or kept in pilot.
- Any material threshold/peer-group change requires a logged change request and a mini-eval on a fresh stratified sample.
