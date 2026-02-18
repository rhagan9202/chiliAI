# /domain-packs/medicaiddentalvisionclaims/README.md
DomainPackId: medicaiddentalvisionclaims [file:1]
Version: 0.1.0 [file:1]

# Purpose
- Medicaid dental/vision claims integrity pack focused on provider/clinic triage, suspicious ring clusters, and code-pattern anomalies with investigator-ready evidence bundles. [file:1]
- Designed to support actions like SIU case creation, state PI referrals, or provider education/edit recommendations, with humans in the loop. [file:1]

# What’s in this pack
- schema.md: Beneficiary, provider (billing/rendering), claim/claimline, optional clinic group/location/prior auth, plus graph-ready edges. [file:1]
- evidence_bundle_spec.md: Claimline samples, peer comparisons, procedure mix/bundles, trajectories, and optional ring subgraphs with completeness rules. [file:1]
- feature_dictionary.md: Provider-window features (utilization, mix, repeats), peer stats, and optional ring/graph features. [file:1]
- indicators.v0.1.md: 10 indicators (rings, bundle outliers, spikes, repeats, churn, complexity mix, location/time, PA mismatch, composite). [file:1]
- eval_dataset_spec.md: Sampling + labeling protocol consistent with the accelerator feedback taxonomy and weekly ops governance. [file:1]

# Minimum data requirements (v0.1)
- Claimline-level procedure codes (CDT for dental; CPT/HCPCS for vision), service dates, provider IDs, and beneficiary IDs (surrogate) sufficient to show evidence. [file:1]
- Paid/allowed and units are recommended for severity ranking and peer comparisons; if missing, constrain indicators and enforce “insufficient evidence” confidence downgrade. [file:1]

# Operational workflow integration
- Outputs: provider/clinic risk queue + (optional) ring cluster queue + evidence bundle viewer + structured feedback capture used for precision-proxy and tuning. [file:1]
- Weekly ops review governs threshold tuning, peer-group redefinitions, and pause/retire decisions with logged change control. [file:1]

# Quick start
1) Implement 3–5 indicators end-to-end first (utilization spike, code-mix/high complexity outlier, repeat-service intervals, basic shared-location ring). [file:1]
2) Run eval on a time-sliced, stratified sample by specialty/geography peer groups to prevent high-volume clinics from dominating the pilot set. [file:1]
3) Add stronger ring features (shared attributes/financial) only when permitted and when evidence bundles can display the linkage defensibly. [file:1]
