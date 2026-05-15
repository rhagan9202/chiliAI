# Monitoring & Operations (Core) — v0.1

## Purpose
Defines how to operate the accelerator after go-live, including dashboards, drift detection, incident response, and pause/discontinue procedures.

## Operating cadence
### Daily (optional)
- Data freshness and ingestion health
- Queue backlog/aging checks

### Weekly (required)
- C08 Weekly ops review:
  - throughput (flagged, reviewed, SLA)
  - quality (precision proxy, false-positive themes)
  - trust (actionable explanation rate, evidence adequacy)
  - drift and data health
  - decisions (tune/pause/resume/retire)

### Monthly (recommended)
- Security/privacy access review
- Domain SME review of confounders/policy windows

## Dashboards (minimum)
- Operations & throughput
- Indicator quality
- Drift & data health
- Explainability & evidence quality
- Governance & change control
- Access & audit (where required)

## Alerts and responses
- Data freshness breach → contain (pause/downgrade confidence), fix pipeline, re-score
- Performance drop → tune or pause, mini-eval, resume with monitoring
- Drift alert → investigate data vs real-world change, decide rebaseline/tune/pause
- Explainability failure → fix evidence mapping, cap subgraph size, update reason codes
- Security anomaly → lock down access, preserve logs, follow client incident policy

## Pause/discontinue policy (summary)
Pause an indicator when:
- precision proxy drops below threshold for N consecutive periods
- evidence missingness exceeds threshold
- actionable explanation rate drops below threshold
- drift is severe and unexplained
- data freshness/quality makes output unsafe

Resume requires:
- remediation completed
- mini-eval or spot-check validation
- approvals per governance policy

## Required telemetry
All deployments must emit minimum telemetry events defined in `core/monitoring/telemetry_contract.md`.
