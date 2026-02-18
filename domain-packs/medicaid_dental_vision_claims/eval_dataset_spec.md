# /domain-packs/medicaiddentalvisionclaims/eval_dataset_spec.md
DomainPackId: medicaiddentalvisionclaims [file:1]
Version: 0.1.0 [file:1]

# Goal
- Confirm that provider/clinic queues surface actionable anomalies with sufficient evidence, and that ring/bundle indicators don’t overwhelm investigators with unusable network output. [file:1]

# Units of review
- Provider-level: provider_id (rendering and/or billing; configurable). [file:1]
- Clinicgroup-level (optional): clinicgroup_id for multi-provider ring/organization signals. [file:1]

# Leakage controls
- Time-based evaluation windows: score on period T; label via investigator review after scoring (and do not backfill labels from actions caused by the same queue without noting selection bias). [file:1]
- If prior auth is used, ensure the evaluation distinguishes “auth lag/data gap” from true mismatch to avoid false positives. [file:1]

# Sampling design (v0.1)
- Stratify by: indicator_id, specialty (dental vs vision subtypes if available), geography, and severity band. [file:1]
- Include (A) top-K per indicator (or per queue), (B) mid-band, and (C) random baseline controls to measure lift. [file:1]
- For ring indicators, sample both: (i) high-density clusters and (ii) “near miss” clusters to test specificity and evidence completeness. [file:1]

# Labeling protocol
- Outcome: suspicious | not_suspicious | insufficient_evidence. [file:1]
- Reason tags: expected_behavior | data_quality_issue | policy_program_change | model_issue | explanation_issue | needs_more_info | other. [file:1]
- Explanation usefulness: actionable | unclear | not_actionable, with evidence adequacy: enough | missing | contradictory. [file:1]

# Primary metrics
- Precision@K (proxy) overall and by indicator using investigator outcomes. [file:1]
- Actionable explanation rate and missing critical evidence rate (hard gate for approving ring indicators). [file:1]

# Secondary metrics
- Queue aging/throughput, to confirm the accelerator integrates into real casework rather than creating a parallel process. [file:1]
- Drift: procedure mix drift, utilization drift, peer-group composition drift, and (for ring indicators) node/edge count drift and subgraph size drift. [file:1]

# Acceptance and gating
- Pilot thresholds are set by PI Ops/investigator leads and documented in the core evaluation plan; indicators failing evidence/explanation thresholds must be paused or kept in pilot. [file:1]
- Any material threshold/peer-group change requires a logged change request and a mini-eval on a fresh stratified sample. [file:1]
