# Indicator Contract (Core Output Schema) — v0.1

## Purpose
Standardize what every indicator produces so:
- UI/workflows can be reused across domain packs
- evaluations and monitoring are consistent
- change control and auditability are enforceable

## Contract boundaries
- An **indicator** is the unit of deployment and monitoring.
- Indicators can be rule-based, statistical, time-series, graph-based, or hybrid.
- A model (e.g., GNN) may exist behind an indicator, but the output contract remains stable.

## Required output fields (per scored item)
### Identity and versioning
- tenant_id
- domain_pack_id
- use_case_id, use_case_version
- indicator_id, indicator_version
- scoring_run_id
- as_of_date (data freshness timestamp)

### Target
- target_entity_type (provider | broker | beneficiary | clinic_group | claim | enrollment_event | other)
- target_entity_id
- target_event_id (optional)

### Scoring and prioritization
- score (0–100)
- confidence_band (low | medium | high)
- priority_band (P0 | P1 | P2 | P3)
- queue_name (routing target)
- due_at (optional SLA deadline)

### Explainability and evidence
- reason_codes[] (stable tokens)
- explanations.local (required)
- explanations.temporal (required when windowing exists)
- explanations.network (required when graph contributes materially)
- evidence_bundle_id
- evidence_completeness_flag (true/false)

### Recommended actions
- recommended_next_steps[]
- stop_conditions[] (optional)

### Monitoring hooks
- monitoring_metrics[] (volume, precision proxy, drift, explanation usefulness, evidence missingness, queue aging)

## Evidence bundle requirements (high level)
Every scored item must link to an evidence bundle sufficient for an investigator to:
- reproduce “why flagged”
- see key raw events and linkages
- identify missing or conflicting evidence

Evidence bundle specs are defined per domain pack.

## Status lifecycle
Indicators move through:
- draft → pilot → approved → (paused | retired)

Promotion to `approved` requires successful evaluation and governance sign-off.

## Backward compatibility
Core UI and monitoring assume these fields exist; any contract changes require a core_version bump and migration guidance.
