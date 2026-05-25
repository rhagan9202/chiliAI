# Evidence Bundle Spec — Medicare FFS Claims (v0.1)
DomainPackId: medicareffsclaims
Version: 0.1.0

Purpose
- Standardize what investigators see in the Evidence Bundle Viewer (timeline + tables + optional network card) for Medicare FFS indicators.

## 1) Evidence bundle envelope (required)
- evidencebundle_id (string)
- case_id (string)
- target_entity_type (provider | beneficiary | claim | claimline | supplier | other)
- target_entity_id (string)
- timewindow_start (date)
- timewindow_end (date)
- indicator_ids (array[string])
- evidence_completeness_flag (bool)
- evidence_completeness_notes (array[string])
- evidence_items (array[EvidenceItem])
- timeline_items (array[TimelineItem]; optional)
- network_subgraph (optional; capped)

## 2) EvidenceItem (required fields)
- evidence_item_id (string)
- evidence_type (event | transaction | claimline | profile | document | other)
- source_system (string; e.g., "CMS_LDS")
- source_table (string)
- source_record_id (string)
- event_datetime (datetime; optional)
- summary (string; human-readable, no PII)
- sensitive_flag (bool)
- attributes (object; safe subset shown in UI)
- pointers (object; how to retrieve full record in client environment)

## 3) Standard evidence views (UI tabs)

### A) Timeline (recommended for most indicators)
Timeline items should include:
- Service date milestones
- Change-point windows (if time-series indicator)
- Peer group baseline window vs comparison window boundaries

### B) Claim/line table (required when indicator is claims-based)
Minimum columns:
- service_date
- claim_id / claimline_id
- provider roles (billing/rendering/ordering if available)
- code (hcpcs/cpt/revenue center)
- units
- allowed/paid (if available)

### C) Peer comparison table (required for peer-outlier indicators)
Minimum columns:
- metric_name
- provider_value
- peer_median
- peer_p90 / p99 (or IQR)
- zscore / percentile
- peer_group_definition (text)

### D) Code-mix / distribution view (required for code-mix indicators)
- top codes by volume/amount
- code family distribution
- entropy / concentration metrics (if used)

### E) Optional network card (only if graph materially contributes)
- Capped subgraph (default max 25 nodes)
- Nodes: provider, beneficiary (surrogate), code family, location (if available)
- Edges: overlap/shared beneficiary, ordering_to_supplier, shared contact/financial (if permitted)

## 4) Completeness rules (v0.1 defaults)
Evidence completeness is FALSE if any apply:
- Missing service dates in the scoring window for the flagged records
- Missing code fields required to justify reason codes (e.g., hcpcs/cpt for Part B/DME)
- Peer group stats unavailable for a peer-outlier indicator
- Network explanation required by indicator but subgraph cannot be generated (only for indicators that declare network-required)

If completeness is FALSE:
- UI must force low confidence band and encourage "insufficient evidence" feedback option.

## 5) Indicator-specific required evidence (hook)
Each indicator definition in indicatorsv0.1.md must list:
- required_evidence_elements (array[string])
- insufficient_evidence_conditions (array[string])
These drive evidence completeness checks and reviewer prompts.

