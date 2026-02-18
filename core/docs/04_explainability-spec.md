# Explainability Specification (Core) — v0.1

## Purpose
Defines minimum explainability requirements so investigators can act safely and consistently.

Explainability is evaluated pre-go-live and monitored post-go-live; degraded explanation usefulness is a trigger for tuning or pause.

## Explainability principles
- Actionable: tells investigators what to do next
- Evidence-linked: ties to reproducible evidence bundle
- Multi-layered: local + temporal + network (when applicable)
- Stable reason codes: versioned library
- Guardrail-ready: includes “what this does NOT mean” and confounders

## Explanation payload (required fields)
Every scored item must provide:
- local explanation: summary + top features/rules + reason codes + not-meaning list
- temporal explanation: baseline/comparison windows + what changed
- network explanation: small subgraph + why edges matter (when graph contributes)

## Evidence bundle completeness rule
If required evidence elements are missing:
- evidence_completeness_flag=false
- confidence_band=low
- reason code includes INSUFFICIENT_EVIDENCE

## Evaluation and monitoring of explanations
- Pre-go-live: label explanation usefulness (actionable/unclear/not actionable)
- Post-go-live: track actionable rate trends and explanation failure reasons

## Change control
Any change affecting explanations requires C09 and a version bump:
- reason code library
- evidence bundle requirements
- feature logic impacting narratives
- graph schema or edge semantics
