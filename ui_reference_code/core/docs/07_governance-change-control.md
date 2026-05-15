# Governance & Change Control (Core) — v0.1

## Purpose
Defines how changes are proposed, validated, approved, deployed, monitored, and rolled back.

## What is governed
We govern AI-reliant functionality:
- indicators, thresholds, peer groups
- evidence bundles and explanation logic
- features and data pipelines used for scoring
- models behind indicators
- monitoring thresholds and drift checks
- access controls and audit logging for evidence

## Change taxonomy
- Low-risk: docs/copy; non-functional display
- Medium-risk: threshold/peer/evidence adjustments → mini-eval required
- High-risk: new approved indicator, model changes, scope expansion → full evaluation + possible independent review

## Standard workflow
1) Propose (C09)
2) Validate (mini-eval or full eval)
3) Approve (PI Ops + INV + SP + PAO per risk)
4) Implement (versioned; record effective_at; rollback plan)
5) Monitor (stabilization window)
6) Rollback/pause if thresholds breached

## Non-negotiable gates
No indicator may be `approved` unless:
- C02, C05, C06, C07 complete
- monitoring metrics computable
- weekly ops review scheduled
- change control enforced

## Emergency changes
Allowed only for SEV0/SEV1 incidents; must be logged via C09 within 24 hours with retrospective approvals.
