# /domain-packs/medicareffsclaims/README.md
DomainPackId: medicareffsclaims
Version: 0.1.0

# Purpose
- Medicare FFS claims (Hospice, Part B, DME) anomaly-to-indicator pack for triage support: peer outliers, time-series change points, and optional network/ring signals.
- Intended use is prioritization and investigation support; it is not designed for automated enforcement or final determinations.

# What’s in this pack
- schema.md: Logical entity/event schema and optional edge model.
- evidence_bundle_spec.md: Required evidence views and completeness rules for defensible review.
- feature_dictionary.md: Canonical feature names + windowing + drift monitoring set.
- indicators.v0.1.md: 10 v0.1 indicators with reason codes, evidence requirements, and next steps.
- eval_dataset_spec.md: How to build the labeled test set and compute pilot metrics.

# Minimum data requirements (v0.1)
- Stable IDs (beneficiary_id, provider_id, claim_id, claimline_id), service dates (line or claim), and code fields (HCPCS/CPT and/or revenue center) sufficient to show “why flagged” evidence.
- Amounts/units are strongly recommended for peer and temporal metrics; if missing, restrict indicators accordingly and force “insufficient evidence” pathways in UI.

# Operational workflow integration
- Output is a provider/supplier risk queue + evidence bundle viewer + structured investigator feedback (suspicious / not suspicious / insufficient evidence + reason tags + explanation usefulness).
- Weekly ops review governs tuning, pausing, or retiring indicators using monitored yield/precision-proxy, drift, and explanation usefulness.

# Quick start (implementation-neutral)
1) Implement 3–5 indicators end-to-end first (peer outlier, code-mix, temporal spike) and wire them to evidence bundles and feedback capture.
2) Run the eval dataset spec on a time-sliced, stratified sample and confirm Precision@K and explanation usefulness meet the pilot gate.
3) Turn on monitoring for score/feature drift, missing evidence rates, and queue aging, and require change control for any threshold/peer-group adjustments.
