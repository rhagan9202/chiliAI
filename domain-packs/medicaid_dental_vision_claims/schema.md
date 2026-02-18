# Domain Pack Schema — Medicaid Dental/Vision Claims Integrity (v0.1)
DomainPackId: medicaiddentalvisionclaims
Version: 0.1.0

Purpose
- Provide a minimal, reusable schema for Medicaid dental/vision PI workflows: provider/clinic risk triage, ring detection, procedure-pattern anomalies, and case generation.

## 1) Entities

### Beneficiary
- beneficiary_id (surrogate)
- eligibility_segment (optional)
- geography (optional)

### Provider
- provider_id (surrogate; NPI token)
- provider_role (enum: rendering, billing, both)
- specialty (dental/vision subtype; optional)
- org_group_id (optional)
- geography (optional)

### ClinicGroup (optional but recommended)
- clinicgroup_id (surrogate)
- group_name (optional)
- linked_provider_ids (array)

### Location
- location_id (surrogate)
- address_hash (optional)
- geography (state/county; optional)

### Claim
- claim_id (surrogate)
- mco_id (optional)
- state_program_id (optional)
- service_from_dt, service_thru_dt
- beneficiary_id (fk)
- billing_provider_id (fk)

### ClaimLine
- claimline_id (surrogate)
- claim_id (fk)
- service_dt
- procedure_code (string; CDT for dental; CPT/HCPCS for vision; configurable)
- diagnosis_code (optional)
- units (optional)
- paid_amt/allowed_amt (optional)
- rendering_provider_id (optional)
- location_id (optional)

### PriorAuth (optional)
- priorauth_id
- beneficiary_id
- provider_id
- procedure_code
- auth_dt
- status

## 2) Edges (graph-ready)
- beneficiary_received_service_from (beneficiary → provider)
- provider_performed_at_location (provider → location)
- provider_shared_contact_or_financial (provider ↔ provider; optional/permissioned)
- procedure_cooccurs_with (procedure ↔ procedure within episode/window)
- temporal_sequence (claimline → claimline for beneficiary trajectories)
