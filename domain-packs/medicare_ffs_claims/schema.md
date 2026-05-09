# Domain Pack Schema — Medicare FFS Claims (v0.1)
DomainPackId: medicareffsclaims
Version: 0.1.0

Purpose
- Provide a minimal, indicator-friendly entity/event schema for Medicare FFS claims (Hospice, Part B, DME) suitable for anomaly detection, peer outliers, time-series change detection, and (optional) graph/ring signals.

Design principles
- Stable surrogate IDs; avoid PII in analytics-facing IDs where possible.
- All evidence items must be source-pointered to reproducible records.
- Support time-windowed scoring (e.g., trailing 30/90/180 days) and peer groups.

## 1) Core entities (tables / logical objects)

### Beneficiary
- beneficiary_id (string; surrogate)
- segment_flags (object; e.g., dual_eligible, risk_segment if available)
- geography (object; state, county, CBSA; as allowed)
- enrollment_windows (optional)

### Provider (Rendering / Billing / Supplier)
- provider_id (string; typically NPI surrogate token)
- provider_type (enum; rendering, billing, supplier, hospice_org, other)
- specialty (string/enum; if available)
- organization_ids (object; TIN/CCN/etc. if available; may be restricted)
- geography (object; state, county, CBSA)
- status_flags (optional)

### Claim
- claim_id (string; surrogate)
- claim_type (enum; hospice, carrier_partb, dme, other)
- from_date (date)
- thru_date (date)
- total_allowed_amt (number; optional)
- total_paid_amt (number; optional)
- beneficiary_id (fk)
- billing_provider_id (fk)
- place_of_service (optional)
- submit/processing dates (optional)

### ClaimLine
- claimline_id (string; surrogate)
- claim_id (fk)
- line_num (int)
- service_date (date)
- hcpcs_cpt_code (string; if applicable)
- revenue_center_code (string; hospice/institutional)
- modifiers (array[string]; optional)
- units (number; optional)
- allowed_amt / paid_amt (number; optional)
- rendering_provider_id (fk; optional)
- ordering_provider_id (fk; optional)
- diagnosis_codes (array[string]; optional)

### Payment / Adjustment (optional)
- payment_event_id
- claim_id
- event_date
- event_type (enum; payment, adjustment, recoupment)
- amount

## 2) Relationship edges (for optional graph features)
Represent as edge table: (src_type, src_id, edge_type, dst_type, dst_id, start_dt, end_dt, strength, provenance)

Recommended edge types:
- beneficiary_received_service_from (beneficiary → provider; derived from claim lines)
- provider_billed_for_code (provider → hcpcs_cpt_code)
- provider_shared_beneficiary_with (provider ↔ provider; derived overlap)
- ordering_to_supplier (ordering_provider → supplier; if available)
- provider_performed_at_location (provider → location_id; if available)
- provider_shared_contact (provider ↔ provider; address/phone if available and permitted)
- provider_shared_financial (provider ↔ provider; bank/account if available and permitted)

## 3) Time windows
Required scoring windows supported by schema:
- window_30d, window_90d, window_180d, window_365d (configurable)
All aggregates should be materialized by (target_entity_id, window, as_of_date).

## 4) Minimum required fields for the accelerator contract
- Stable IDs: beneficiary_id, provider_id, claim_id, claimline_id
- Timestamps: service_date (claimline) or from/thru dates (claim)
- Monetary / utilization measures: units and/or allowed/paid amounts (as available)
- Code fields: hcpcs/cpt/revenue center (as available)

## 5) Data quality constraints (v0.1)
- Required: non-null beneficiary_id, provider_id (billing), service_date (or claim from/thru)
- Required: code present for Part B/DME lines (hcpcs/cpt) or revenue center for hospice
- Track missingness rates for join keys and service dates for drift/data-health dashboarding
