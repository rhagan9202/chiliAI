# Story E10-S15: Security audit checklist and dependency scanning

## Story
As a platform operator, I want automated dependency vulnerability scanning and a documented security audit checklist, so that known vulnerabilities are detected early and security posture is reviewable.

## Acceptance Criteria
1. GitHub Actions CI includes a `pip-audit` step for Python dependencies and `npm audit` for frontend dependencies.
2. The workflow fails on HIGH or CRITICAL severity vulnerabilities.
3. `docs/security_checklist.md` documents: OWASP Top 10 mitigations, auth configuration, input validation rules, secret management practices, TLS requirements, logging hygiene (no PII in logs).
4. A quarterly review cadence is documented.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E10-S01      |

## Target Files
- `.github/workflows/ci.yml` — add `pip-audit` and `npm audit` steps
- `docs/security_checklist.md` — new security audit checklist document

## Reference Files to Read First
- `.github/workflows/ci.yml` — CI workflow from E10-S01
- `backend/pyproject.toml` — Python dependencies to audit
- `chili_app/package.json` — frontend dependencies to audit
- `docs/architecture.md` — architectural security decisions

## Architectural Constraints
- `pip-audit` must run against the locked/resolved dependencies, not just `pyproject.toml` declarations
- `npm audit` must use `--audit-level=high` to fail only on HIGH or CRITICAL
- The security checklist must reference specific chiliAI features and configurations, not be generic boilerplate
- The checklist must map OWASP Top 10 items to specific mitigation implementations in the codebase

## What NOT To Do
- Do NOT suppress or ignore vulnerability findings without documented justification
- Do NOT install `pip-audit` or audit tools as project dependencies — install them in the CI workflow only
- Do NOT write a generic security checklist — make it specific to chiliAI's architecture and implementation
- Do NOT add SAST (static analysis security testing) tools in this story — focus on dependency scanning only
- Do NOT block CI on LOW or MODERATE vulnerabilities — only HIGH and CRITICAL
- Do NOT include specific vulnerability examples or exploit techniques in the checklist

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `pip-audit` step added to CI workflow
- [ ] `npm audit` step added to CI workflow
- [ ] CI fails on HIGH/CRITICAL vulnerabilities
- [ ] `docs/security_checklist.md` covers all OWASP Top 10 items
- [ ] Quarterly review cadence documented
- [ ] CI workflow YAML is valid
