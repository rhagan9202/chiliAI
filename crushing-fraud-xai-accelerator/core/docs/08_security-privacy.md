# Security & Privacy (Core) — v0.1

## Purpose
Defines minimum security and privacy requirements for deploying and operating the accelerator in client environments.

## Principles
- Least privilege and role-based access control (RBAC)
- Data minimization: only collect and retain what is required
- Auditability: evidence access and configuration changes must be logged
- Segmentation: separate dev/test/prod; restrict production access
- No PII/PHI in repo artifacts or telemetry by default

## Data handling
- Store sensitive data in client-controlled systems.
- Prefer surrogate IDs in UI and telemetry; show PII/PHI only in evidence viewer with appropriate permissions.
- Document data provenance, retention, and restrictions in C05.

## Access controls
- Roles: pi_ops, investigator, analytics, security_privacy, admin, viewer
- Sensitive evidence requires explicit authorization and audit logging.

## Telemetry privacy
- Telemetry is append-only and access-controlled.
- Do not log raw free-text with PII/PHI; store structured flags and reference IDs.

## Model/AI constraints
- The accelerator supports triage; do not automate enforcement.
- Any scope expansion toward consequential decisions must complete risk screening (C03) and apply stronger controls.

## Security operations
- Monitor unusual access patterns.
- Follow the incident runbook for containment and escalation.
