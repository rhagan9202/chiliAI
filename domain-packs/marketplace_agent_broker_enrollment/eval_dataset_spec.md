# /domain-packs/marketplaceagentbrokerenrollment/eval_dataset_spec.md
DomainPackId: marketplaceagentbrokerenrollment
Version: 0.1.0

# Goal
- Validate broker/event queues for investigator usefulness and safe operation (evidence completeness + actionable explanations) before approval.

# Units of review
- Broker-level: broker_npn for broker oversight queue.
- Event-level: enrollment_change_event_id for suspected unauthorized change queue.

# Leakage controls (required)
- Time-based evaluation: score on period T, label using investigator review captured after scoring (or complaint outcomes that occur after the scored window if used).
- Keep complaint “future resolution” fields out of features unless the evaluation explicitly models that lag and the UI explains it as post-event evidence.

# Sampling design (v0.1)
- Stratify by: indicator_id, queue type (broker vs event), severity band, and complaint-linked vs not complaint-linked.
- Include: (A) top-K broker queue, (B) top-K event queue, (C) mid-score samples, and (D) random baseline, sized to investigator capacity.
- Ensure representation of association-mismatch cases and non-mismatch cases to test specificity and evidence completeness.

# Labeling protocol (required fields)
- Outcome: suspicious | not_suspicious | insufficient_evidence.
- Reason tags: expected_behavior | data_quality_issue | policy_program_change | model_issue | explanation_issue | needs_more_info | other.
- Explanation usefulness: actionable | unclear | not_actionable.
- Evidence adequacy: enough | missing | contradictory, with “missing evidence notes” captured when applicable.

# Primary metrics
- Precision@K (proxy) separately for broker and event queues, using investigator outcomes.
- Actionable explanation rate and missing evidence rate by indicator, since explanation/evidence quality is a go/no-go gate.

# Secondary metrics
- Queue aging and investigator throughput, to confirm workflow fit (no parallel-system burden).
- Drift: switch-rate distribution drift, complaint-rate drift (including complaint lag), and association linkage missingness drift.

# Acceptance and gating
- PI Ops sets K and minimum Precision@K targets; investigators set minimum actionable explanation targets; any indicator that fails must remain pilot or be paused.
- Any scope expansion beyond triage/prioritization requires refreshed risk screening and stricter governance controls.
