# Core UI Fields Dictionary (v0.1)

## Purpose
Defines the canonical field names, types, and semantics used across:
- UI screens (dashboards, triage queue, evidence viewer, feedback, governance)
- API payloads (read/write)
- Telemetry events (UI actions + workflow changes)
- Storage tables (case state, feedback, evidence bundle metadata)

This is the contract that keeps Core UI reusable across domain packs.

---

## Conventions

### Naming
- Use `snake_case` for all fields.
- IDs are strings unless explicitly numeric (to support composite keys and GUIDs).
- Timestamps are ISO-8601 UTC strings (e.g., `2026-02-17T22:05:11Z`).

### Data types
- `string`, `number`, `integer`, `boolean`, `timestamp`, `array<T>`, `object`

### Common enums
- `env`: `dev | test | prod`
- `severity_band`: `low | medium | high | critical`
- `case_status`: `new | in_review | needs_more_info | escalated | closed_no_action | closed_action_taken | duplicate | error`
- `indicator_status`: `draft | pilot | prod | paused | retired`
- `evidence_completeness`: `complete | partial | insufficient`
- `feedback_label`: `true_positive | false_positive | unclear | duplicate | not_applicable`
- `explanation_usefulness`: `1 | 2 | 3 | 4 | 5` (1=not useful, 5=very useful)
- `evidence_adequacy`: `1 | 2 | 3 | 4 | 5`
- `approval_decision`: `approved | rejected | needs_revision`
- `pii_classification`: `none | pii | phi | pii_phi`

### Version triplet (always present in persisted records)
- `core_version`: SemVer for Core Kit
- `domain_pack_version`: SemVer per domain pack
- `use_case_version`: SemVer per deployed use case instance (client-specific config)

---

## Global fields (present in most records)

### Tenant + deployment
- `tenant_id` (string): Client tenant / org identifier.
- `program_id` (string): Program identifier (e.g., Medicare FFS PI Ops, Marketplace integrity).
- `env` (string enum): `dev|test|prod`.

### Versioning
- `core_version` (string)
- `domain_pack_id` (string): Stable pack identifier (e.g., `medicare_ffs`).
- `domain_pack_version` (string)
- `use_case_id` (string): Stable identifier for a specific deployed use case.
- `use_case_version` (string)

### Audit metadata
- `created_at` (timestamp)
- `created_by` (string): User or service principal id.
- `updated_at` (timestamp)
- `updated_by` (string)

### Data classification
- `pii_classification` (string enum): `none|pii|phi|pii_phi`
- `access_policy_id` (string): Reference to access policy governing the record.

---

## Use-case canvas fields (C01)

- `use_case_name` (string)
- `use_case_description` (string)
- `primary_user_role` (string): e.g., investigator, queue_owner.
- `workflow_step_supported` (string): triage / evidence_prep / qa / monitoring.
- `primary_entity_type` (string): provider, beneficiary, agent, broker, claim, enrollment_event, etc.
- `secondary_entity_types` (array<string>)
- `target_outcome_definition` (string): what “positive” means for triage.
- `non_goals` (array<string>)

### Data sources
- `data_sources` (array<object>):
  - `source_name` (string)
  - `owner_team` (string)
  - `refresh_cadence` (string)
  - `known_issues` (array<string>)
- `freshness_requirement_hours` (number)
- `lookback_days` (integer)

### Risks + mitigations
- `risk_statements` (array<string>)
- `mitigations` (array<string>)
- `pause_authority_role` (string)

### Success metrics (targets)
- `target_precision_at_k` (number)
- `k_value` (integer)
- `target_time_to_evidence_seconds` (integer)
- `target_explanation_usefulness_avg` (number)
- `target_evidence_adequacy_avg` (number)

---

## Indicator definition fields (C02)

### Identity
- `indicator_id` (string): Stable ID (never reuse for different logic).
- `indicator_name` (string)
- `indicator_status` (string enum)
- `indicator_owner` (string): person/team
- `sme_reviewer` (string)

### Scope + unit
- `unit_of_scoring` (string): `entity | entity_month | claim | event`
- `entity_type` (string)
- `inclusion_criteria_text` (string)
- `exclusion_criteria_text` (string)

### Logic/model
- `indicator_type` (string): `rule | peer | time_series | graph | ml | composite`
- `feature_inputs` (array<object>):
  - `feature_name` (string)
  - `feature_definition` (string)
  - `window_days` (integer, optional)
- `missingness_handling` (string)
- `threshold_definition` (string)
- `score_range_min` (number)
- `score_range_max` (number)

### Reason codes (catalog)
- `reason_code_catalog` (array<object>):
  - `reason_code` (string): e.g., `RC001`
  - `title` (string)
  - `description` (string)
  - `trigger_logic_text` (string)
  - `user_facing_copy` (string)

### UX guardrails copy
- `one_sentence_explanation` (string)
- `what_this_does_not_mean` (array<string>)
- `prohibited_language` (array<string>)

### Evidence requirements
- `required_evidence_items` (array<string>)
- `evidence_time_window_days` (integer)
- `insufficient_evidence_conditions` (array<string>)

---

## Scoring output record (entity-level)

This is what powers the risk dashboard and triage queue.

### Identifiers
- `scoring_run_id` (string): Batch run identifier.
- `scored_at` (timestamp)
- `indicator_id` (string)
- `indicator_version` (string): internal/version tag for the indicator definition used.
- `entity_id` (string)
- `entity_type` (string)
- `entity_display_name` (string, optional)
- `time_bucket_start` (timestamp, optional): for entity-month scoring.
- `time_bucket_end` (timestamp, optional)

### Core outputs
- `score` (number)
- `severity_band` (string enum)
- `confidence` (number, optional): 0–1 if used.
- `evidence_completeness` (string enum)

### Explanations (structured)
- `reason_codes` (array<object>):
  - `reason_code` (string)
  - `rank` (integer)
  - `contribution` (number, optional): relative importance.
  - `short_explanation` (string)

### Evidence bundle link
- `evidence_bundle_id` (string)
- `evidence_bundle_uri` (string, optional): pointer to stored artifact.
- `recommended_next_steps` (array<string>)

### Comparators/benchmarks (optional but recommended)
- `peer_group_id` (string, optional)
- `peer_percentile` (number, optional)
- `baseline_rate` (number, optional)

---

## Triage queue fields

### Queue row
- `queue_id` (string)
- `queue_name` (string)
- `queue_owner` (string)
- `queue_rank` (integer): ordering position.
- `queue_score` (number): usually same as `score`.
- `queue_bucket` (string, optional): e.g., high priority, watchlist.
- `assigned_to` (string, optional)
- `assignment_updated_at` (timestamp, optional)

### Filters (UI state)
- `filter_severity_bands` (array<string>)
- `filter_indicator_ids` (array<string>)
- `filter_entity_types` (array<string>)
- `filter_time_range_start` (timestamp, optional)
- `filter_time_range_end` (timestamp, optional)
- `filter_program_tags` (array<string>, optional)

### Work tracking
- `first_viewed_at` (timestamp, optional)
- `last_viewed_at` (timestamp, optional)
- `investigator_notes` (string, optional)

---

## Case record (workflow state)

A case links one or more queue items/evidence bundles to a review workflow.

### Identity
- `case_id` (string)
- `external_case_id` (string, optional): if integrated with a case management tool.
- `case_status` (string enum)
- `opened_at` (timestamp)
- `closed_at` (timestamp, optional)

### Relationships
- `primary_entity_id` (string)
- `primary_entity_type` (string)
- `linked_queue_items` (array<object>):
  - `indicator_id` (string)
  - `scoring_run_id` (string)
  - `evidence_bundle_id` (string)

### Actions + outcomes
- `action_taken` (string, optional): free text or controlled vocabulary by client.
- `action_taken_date` (timestamp, optional)
- `disposition_summary` (string, optional)
- `sme_escalation_required` (boolean, optional)
- `escalated_to` (string, optional)

---

## Evidence bundle fields (viewer payload)

### Evidence bundle metadata
- `evidence_bundle_id` (string)
- `generated_at` (timestamp)
- `generated_by` (string): service id
- `evidence_time_window_start` (timestamp)
- `evidence_time_window_end` (timestamp)
- `evidence_completeness` (string enum)
- `missing_evidence_items` (array<string>)
- `limitations_text` (array<string>)  : short disclaimers

### Summary block (top of viewer)
- `summary_title` (string)
- `summary_bullets` (array<string>)
- `primary_reason_codes` (array<string>)
- `what_this_does_not_mean` (array<string>)

### Timeline events
- `timeline_events` (array<object>):
  - `event_id` (string)
  - `event_timestamp` (timestamp)
  - `event_type` (string)
  - `event_title` (string)
  - `event_description` (string, optional)
  - `amount` (number, optional)
  - `units` (number, optional)
  - `code` (string, optional): procedure/drug/etc.
  - `source_pointer` (object): see Source pointers

### Tables (optional UI tabs)
- `evidence_tables` (array<object>):
  - `table_title` (string)
  - `rows` (array<object>): free-form row dicts, but each row should carry `source_pointer`

### Network slice (optional)
- `network` (object, optional):
  - `nodes` (array<object>):
    - `node_id` (string)
    - `node_type` (string)
    - `label` (string, optional)
  - `edges` (array<object>):
    - `edge_id` (string)
    - `source_node_id` (string)
    - `target_node_id` (string)
    - `edge_type` (string)
    - `evidence_strength` (number, optional)
    - `source_pointer` (object, optional)

### Source pointers (required structure)
- `source_pointer` (object):
  - `source_system` (string)
  - `source_table` (string)
  - `primary_key` (string)
  - `record_timestamp` (timestamp, optional)
  - `extract_timestamp` (timestamp, optional)

### Reproducibility
- `config_snapshot_id` (string)
- `feature_build_run_id` (string, optional)
- `code_artifact_version` (string, optional)

---

## Feedback capture fields

Feedback is the core learning loop; keep it structured.

### Identity
- `feedback_id` (string)
- `case_id` (string)
- `submitted_at` (timestamp)
- `submitted_by` (string)

### Labels and rationale
- `feedback_label` (string enum)
- `reason_tags` (array<string>): controlled vocabulary (client-configured).
- `free_text_notes` (string, optional)

### Explanation and evidence quality
- `explanation_usefulness` (integer 1–5)
- `evidence_adequacy` (integer 1–5)
- `missing_evidence_reported` (array<string>, optional)
- `confusing_reason_codes` (array<string>, optional)

### Effort proxy (optional)
- `time_spent_minutes` (number, optional)
- `clicked_artifacts` (array<string>, optional): e.g., “timeline”, “network”, “raw_records”.

### Outcome linkage (optional)
- `confirmed_outcome` (string, optional): audit-confirmed outcome if later available.
- `confirmed_outcome_date` (timestamp, optional)

---

## Indicator health dashboard fields

### Aggregates (per indicator per period)
- `period_start` (timestamp)
- `period_end` (timestamp)
- `indicator_id` (string)
- `items_scored` (integer)
- `items_queued` (integer)
- `avg_score` (number)
- `severity_distribution` (object): e.g., `{low: 120, medium: 45, high: 10}`
- `feedback_count` (integer)

### Quality
- `precision_at_k` (number, optional)
- `yield_at_k` (number, optional)
- `explanation_usefulness_avg` (number, optional)
- `evidence_adequacy_avg` (number, optional)
- `missing_critical_evidence_rate` (number, optional)

### Drift/stability
- `stability_at_k` (number, optional)
- `drift_flags` (array<string>, optional)
- `data_freshness_hours` (number, optional)
- `missingness_rate` (number, optional)

---

## Governance + change control fields

### Change request
- `change_request_id` (string)
- `change_title` (string)
- `change_type` (array<string>)
- `requested_by` (string)
- `requested_at` (timestamp)
- `motivation_text` (string)
- `risk_assessment_text` (string)

### Proposed change payload (structured pointers)
- `affected_indicator_ids` (array<string>)
- `proposed_thresholds` (object, optional)
- `proposed_reason_code_changes` (object, optional)
- `proposed_evidence_bundle_changes` (object, optional)
- `proposed_monitoring_changes` (object, optional)

### Validation + approvals
- `validation_plan_uri` (string, optional)
- `validation_results_uri` (string, optional)
- `approval_records` (array<object>):
  - `approver_role` (string)
  - `approver_id` (string)
  - `decision` (string enum)
  - `decision_at` (timestamp)
  - `comments` (string, optional)

### Rollback
- `last_known_good_snapshot_id` (string, optional)
- `rollback_executed` (boolean, optional)
- `rollback_at` (timestamp, optional)
- `rollback_by` (string, optional)

---

## Pause / discontinue controls (ops safety)

- `control_action_id` (string)
- `action_type` (string): `pause_indicator | resume_indicator | retire_indicator | pause_use_case | resume_use_case`
- `target_type` (string): `indicator | use_case`
- `target_id` (string)
- `action_reason` (string)
- `effective_at` (timestamp)
- `expires_at` (timestamp, optional)
- `issued_by` (string)
- `notified_roles` (array<string>, optional)

---

## UI audit event fields (viewer and workflow actions)

These fields should be emitted for audit and governance monitoring.

- `audit_event_id` (string)
- `event_timestamp` (timestamp)
- `event_type` (string):
  - `view_queue`
  - `view_entity_dashboard`
  - `open_case`
  - `view_evidence_bundle`
  - `export_evidence`
  - `submit_feedback`
  - `approve_change`
  - `pause_indicator`
  - `resume_indicator`
- `actor_id` (string)
- `actor_role` (string)
- `ip_address` (string, optional)
- `user_agent` (string, optional)

Object references:
- `object_type` (string): `case | evidence_bundle | indicator | use_case | export`
- `object_id` (string)
- `related_ids` (object, optional): `{case_id, evidence_bundle_id, indicator_id, entity_id}`

Outcome:
- `result` (string): `success | denied | error`
- `error_code` (string, optional)
- `error_message` (string, optional)

---

## Client-configured vocabularies (recommended)
These should be versioned per use case.

- `reason_tags_vocab` (array<object>): `{tag, description}`
- `action_taken_vocab` (array<object>): `{action, description}`
- `entity_type_vocab` (array<object>): `{entity_type, description}`
- `event_type_vocab` (array<object>): `{event_type, description}`

---

## Notes
- Domain packs may extend this dictionary with domain-specific fields, but Core screens must not require them to function.
- Any additional fields must preserve traceability (source pointers) and version triplet.
