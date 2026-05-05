# Story E10-S01: GitHub Actions CI pipeline — lint, typecheck, test, build

## Story
As a platform developer, I want a GitHub Actions workflow that lints, typechecks, tests, and builds both backend and frontend on every PR, so that quality regressions are caught before merge.

## Acceptance Criteria
1. `.github/workflows/ci.yml` defines a workflow triggered on push to `main` and all PRs.
2. Backend jobs: `ruff check`, `pyright --strict`, `pytest --cov` with coverage threshold enforcement (fail if any package < 85%).
3. Frontend jobs: `npm run lint`, `npm run build` (includes `tsc -b`).
4. Jobs run in parallel (backend and frontend are independent).
5. Coverage reports are uploaded as artifacts.
6. Workflow uses caching for `pip` and `npm` dependencies.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | M    | None         |

## Target Files
- `.github/workflows/ci.yml` — CI workflow definition
- `Makefile` — update with CI-compatible targets if needed
- `.python-version` — repo-root Python version file (if not already present)

## Reference Files to Read First
- `backend/pyproject.toml` — Python dependencies, test config, ruff/pyright settings
- `chili_app/package.json` — frontend scripts and dependencies
- `Makefile` — existing local build/test commands
- `backend/.python-version` — Python version declaration

## Architectural Constraints
- Use `ubuntu-latest` runner, Python 3.12, Node 22.
- Backend and frontend jobs must be independent (parallel execution).
- Coverage enforcement must fail the build if any backend package drops below 85%.
- Use GitHub Actions cache action for `pip` and `npm` dependency caching.
- No secrets required for CI — all tests use in-memory adapters.

## What NOT To Do
- Do NOT hardcode Python or Node versions in multiple places — use `.python-version` and `.nvmrc` or matrix strategy.
- Do NOT install frontend dependencies in the backend job or vice versa.
- Do NOT use `continue-on-error: true` on lint/typecheck/test steps — failures must block merge.
- Do NOT upload coverage reports containing source code — only summary reports.
- Do NOT add deployment steps to this workflow — CI only, not CD.

## Done Checklist
- [ ] All acceptance criteria met
- [ ] `.github/workflows/ci.yml` created and valid YAML
- [ ] Backend lint, typecheck, and test jobs pass
- [ ] Frontend lint and build jobs pass
- [ ] Jobs run in parallel
- [ ] Dependency caching is configured
- [ ] Coverage reports uploaded as artifacts
- [ ] No lint errors (`ruff check`)
