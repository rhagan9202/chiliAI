# Release & Versioning (Core) — v0.1

## Purpose
Defines how to version and release the Core Kit, domain packs, and client-specific configurations.

## Three-layer versioning model
- core_version (Core Kit)
- domain_pack_version (per domain)
- use_case_version (client instance)

## SemVer rules
Core Kit:
- MAJOR: breaking contract changes
- MINOR: backward-compatible features
- PATCH: fixes/clarifications

Domain packs:
- MAJOR: schema-breaking change requiring migration
- MINOR: add indicators/features
- PATCH: non-breaking fixes

## Release gates
Core release requires:
- templates consistent
- indicator contract stable
- evaluation and monitoring specs aligned
- changelog updated

Domain pack release requires:
- schema and evidence spec updated
- indicator catalog updated
- eval dataset spec updated
- changelog updated

## Deployment promotion
- dev → test → prod
- prod promotion requires signed C06 + C07 and monitoring readiness

## Rollback
- keep last known-good config snapshot
- log rollback via C09
- run mini-eval post rollback
