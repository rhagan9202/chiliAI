# Evidence Bundle Spec — Medicaid Dental/Vision Claims Integrity (v0.1)
DomainPackId: medicaiddentalvisionclaims
Version: 0.1.0

Purpose
- Standardize evidence for provider/clinic risk cases and ring/cluster cases in Medicaid dental/vision workflows.

## 1) Domain-level required evidence slices
- Claim/line sample slice (top contributing lines)
- Procedure distribution slice (provider vs peers)
- Beneficiary trajectory slice (repeat services / churn)
- Location slice (service locations and volumes)
- Optional ring/cluster slice (shared address/phone/bank if permitted)

## 2) Evidence views
A) Claim/line table
- service_dt, claim_id/line_id
- procedure_code (+ diagnosis if present)
- units, paid/allowed
- rendering/billing provider
- location_id

B) Peer comparison table
- metric_name
- provider_value
- peer_median / p90 / p99 (or IQR)
- peer group definition (specialty x geography x eligibility segment)

C) Procedure bundle/community view
- top co-occurring codes
- bundle frequency vs peers
- “rare bundle” flags (if used)

D) Timeline / trajectories
- beneficiary-level sequences (de-identified)
- repeat interval summaries

E) Optional network card (ring indicators)
- capped provider↔provider subgraph with edge semantics (shared contact/location/beneficiary overlap)

## 3) Completeness rules
Evidence completeness FALSE if:
- Procedure codes missing for flagged lines
- Peer group stats unavailable for peer-outlier indicators
- Ring indicator requires shared-link evidence but shared-link data is unavailable/permissioned off
