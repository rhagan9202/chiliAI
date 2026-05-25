# Reference Architecture — Azure (Core) v0.1

## Purpose
Provides a reusable Azure reference architecture pattern for deploying the accelerator into a client environment.

## High-level components
1) Data ingestion
- Claims/enrollment/complaint/casework feeds into a secure landing zone.

2) Storage layers
- Raw (immutable), curated (standardized), features (analytics-ready).

3) Compute
- Batch feature builds and scoring jobs.
- Optional graph build jobs.

4) Explainability + evidence bundling
- Evidence bundle generation service writes structured pointers to source records.

5) UI/workflow
- Web UI (triage queue, evidence viewer, feedback capture) or integration to existing case management.

6) Monitoring and telemetry
- Telemetry event sink + dashboards + drift jobs.

7) Governance
- Change control store; config snapshots; approvals.

## Security patterns (conceptual)
- Identity: workload identity/managed identity preferred.
- Network: private endpoints and restricted egress where feasible.
- Logging: centralize audit logs for evidence access and config changes.

## Deployment modes
- “In-place” in client tenant (preferred)
- Isolated analytics subscription/VNet with approved data access

## Notes
This is a pattern document; specific services are selected per client constraints (commercial vs gov cloud, existing standards).
