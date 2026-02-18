# Reference Architecture — AWS (Core) v0.1

## Purpose
Provides a reusable AWS reference architecture pattern for deploying the accelerator into a client environment.

## High-level components
1) Data ingestion
- Secure landing zone for claims/enrollment/complaint/casework feeds.

2) Storage layers
- Raw, curated, and feature stores aligned to governance and lineage needs.

3) Compute
- Batch feature builds and scoring jobs.
- Optional graph build jobs.

4) Explainability + evidence bundling
- Evidence bundle generation writes structured pointers; supports reproducibility.

5) UI/workflow
- Web UI for triage and feedback, or integration to case management.

6) Monitoring and telemetry
- Central event log, dashboards, drift jobs, alerting.

7) Governance
- Versioned configs, approvals, change logs, and rollback.

## Security patterns (conceptual)
- Identity: IAM roles with least privilege.
- Network: VPC segmentation; private connectivity where feasible.
- Logging: centralized audit logs, retained per policy.

## Deployment modes
- Single-account deployment with strict separation (dev/test/prod)
- Multi-account pattern (shared services + workload accounts)

## Notes
This is a pattern document; service selections should align to client standards (commercial vs GovCloud).
