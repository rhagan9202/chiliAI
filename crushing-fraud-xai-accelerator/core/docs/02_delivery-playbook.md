# Delivery Playbook (Core) — v0.1
Duration: 2 weeks (10 business days)

## Objective
Stand up a productionizable pilot for one domain pack that:
- Generates a prioritized queue from 3–5 indicators
- Shows evidence bundles + explanations
- Captures investigator feedback
- Meets evaluation acceptance criteria
- Operates with monitoring, weekly ops review, and change control

## Non-goals (v0.1)
- Automated enforcement / automated consequential decisions
- Full-scale platform build

## Definition of Done
A use case is “live” only when:
- C01, C02 (for each indicator), C05, C06, C07 completed and signed
- Monitoring metrics computable and weekly ops review scheduled (C08)
- Change control active (C09)

## Team roles (minimum)
- PAO, PI Ops Lead, Investigator Lead, AML Lead, DE Lead (part-time OK), SP Lead (light-touch), UI/workflow engineer

## Day-by-day plan
Day 1: SME framing workshop → C01 + draft C02 entries
Day 2: Data readiness + provenance → C05 draft + data quality checks
Day 3: Finalize v0.1 indicators (3–5) → C02 complete (reason codes, evidence, next steps)
Day 4: Implement workflow UI thin slice (queue/evidence/feedback)
Day 5: Implement scoring + explanation payload baseline
Day 6: Build eval test set + C06 plan (K, sampling, labels)
Day 7: Investigator labeling sprint (human validation)
Day 8: Tune thresholds/peer groups → C09 change requests + update C04
Day 9: Monitoring + drift checks + pause/discontinue test; C07 draft
Day 10: Go/No-go review; schedule first C08 weekly ops review

## Post go-live cadence (v0.1)
Weekly:
- C08 ops review (throughput, quality, drift, explanation usefulness)
- C09 for any changes

## Risks & mitigations
- Low investigator time → cap indicators, label top-K only
- Data gaps → enforce evidence completeness rules; tag data_quality_issue
- Drift/policy changes → SME review + drift checks; pause if needed
