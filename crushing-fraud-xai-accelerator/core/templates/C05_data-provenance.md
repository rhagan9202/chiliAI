# C05 — Data Provenance & Traceability (v0.1)

## 1) Scope
- Use-case:
- Domain pack:
- Environments: dev / test / prod
- Data steward:

## 2) Source systems and lineage
For each source, document:
- Source name:
- Owner:
- Ingestion method:
- Refresh cadence:
- Key fields used:
- Transformations applied:
- Quality checks:

## 3) Identifier strategy
- Primary entity IDs:
- Crosswalk keys (if any):
- De-identification/pseudonymization approach (if any):
- Linkage quality risks:

## 4) Evidence traceability (required)
Evidence must be traceable to source.
- Evidence bundle ID format:
- Required pointers:
  - Source table:
  - Primary key:
  - Event timestamp:
  - Extract timestamp:
- Reproducibility requirements:
  - Config snapshot ID:
  - Code/artifact version:
  - Feature build run ID:

## 5) Access controls
- Who can access raw vs curated vs evidence bundles?
- Row-level/column-level controls (if applicable):
- Break-glass process:

## 6) Retention and deletion
- Retention policy:
- Secure deletion process:
- Audit log retention:

## 7) Known gaps and remediation
- Gap:
- Risk:
- Mitigation plan:
- Target date:

## 8) Approvals
- Data steward:
- Security/Privacy:
- PI Ops:
- Date:
