## File: docs/backlog/_cicd.md

**Scope:** CI/CD pipeline — quality gates, container delivery, environment promotion, release automation.

> **Cross-cutting concern:** CI/CD pipeline — quality gates, container delivery, environment promotion, release automation.
> **Source spec:** [`docs/superpowers/specs/2026-05-24-complete-backlog-design.md`](../../superpowers/specs/2026-05-24-complete-backlog-design.md)
> **Architecture refs:** §10 (Deployment), §14.2 row "CI/CD pipeline" — "Baseline lint, type-check, test, build, and dependency audits run in GitHub Actions. Add deploy/promotion jobs once environments are finalized."
> **Status of artifacts read:** `.github/workflows/ci.yml` (single workflow), `Makefile`, `scripts/{demo_ingest_tn_subset.sh,smoke_graph_workflow.sh}`, `infra/{k8s,helm}`, `backend/pyproject.toml` (version=0.1.0), `chili_app/package.json` (version=0.0.0). No `.github/dependabot.yml`, no `renovate.json`, no `.pre-commit-config.yaml`, no CHANGELOG, no release workflow, no deploy workflow, no Playwright job, no container build, no preview-env workflow.

---

## Current CI state (one workflow: `ci.yml`)

- **Triggers:** push to `main`, all pull_request events. Concurrency-cancels stale runs per ref.
- **`backend` job:** ruff → pyright (honors `tool.pyright.include` scope) → pytest with `--cov-fail-under=85` → upload `coverage.xml` artifact → pip-audit (skip-editable, soft-fail on non-vuln errors).
- **`frontend` job:** eslint → `tsc --noEmit` → `vitest run` → `vite build` → upload `dist/` → `npm audit --audit-level=high`.
- **Caching:** pip wheels keyed on `backend/pyproject.toml`; npm keyed on `chili_app/package.json`.

## What's missing (drives the epic list below)

- No container build / image push.
- No deploy or promotion workflow (architecture §10.3 K8s topology exists in `infra/`, but nothing in CI deploys it).
- No release tagging, version bump, or changelog automation. Both `pyproject.toml` and `package.json` are stuck at placeholder versions (`0.1.0` / `0.0.0`).
- No per-PR preview environment.
- No Dependabot/Renovate config; no container image vulnerability scanning (only pip-audit + npm audit run against source-level deps).
- No backlog consistency check (the script being built in Wave 3 needs a CI hook — see spec §8 ending block).
- No Alembic migration dry-run / drift check in CI even though migrations are runtime-required (`make migrate`).
- No E2E Playwright job (config exists at `chili_app/playwright.config.ts`, scripts exist at `chili_app/package.json` `test:e2e`, but CI never invokes them).
- No frontend coverage gate (vitest runs but `--coverage` is not enforced; `@vitest/coverage-v8` is installed but unused in CI).
- No performance regression gate.
- No rollback automation / runbook hook.
- No secret-scanning or pre-commit hooks (no `.pre-commit-config.yaml`, no gitleaks/trufflehog action).
- No documentation deploy / live-link check for `docs/`.

---

## Epics

### _cicd.01 — Enforce frontend coverage gate at ≥85% parity with backend
- **Gap:** `ci.yml` runs `npm run test:run` but never invokes vitest `--coverage`, even though `@vitest/coverage-v8` is in devDependencies. No threshold enforced; frontend has no coverage floor while backend gates at 85%.
- **Edges (provisional):** none.

### _cicd.02 — Tighten pyright strict scope and fail CI on scope regressions
- **Gap:** `ci.yml` calls `pyright` without arguments by design (relies on `tool.pyright.include`); there is no audit step that flags new modules added to the tree but not added to `include`, so untyped code silently bypasses the gate.
- **Edges (provisional):** none.

### _cicd.03 — Promote pip-audit and npm audit from soft to hard fail with allow-list
- **Gap:** `ci.yml` pip-audit step uses `… || pip-audit --skip-editable` (a retry that masks real failures); `--ignore-vuln GHSA-0000-0000-0000` is a placeholder. No vulnerability allow-list governance file. npm audit runs but has no allow-list either.
- **Edges (provisional):** none.

### _cicd.04 — Add Dependabot (or Renovate) for backend, frontend, GitHub Actions, and Docker base images
- **Gap:** No `.github/dependabot.yml`, no `renovate.json`. Dependency drift detection relies entirely on manual review; no scheduled PRs for `pyproject.toml`, `package.json`, GHA action pins, or `python:3.12-slim` / `nginx:alpine` base images.
- **Edges (provisional):** none.

### _cicd.05 — Build and push versioned container images on merge to main and on tags
- **Gap:** No workflow builds or pushes `chili-api`, `chili-worker`, `chili-app` images. `backend/Dockerfile` and `chili_app/Dockerfile` exist and are used by `make prod` locally, but CI never produces an artifact a deployer can consume.
- **Edges (provisional):** unblocks _cicd.06, _cicd.07, _cicd.08, _cicd.10.

### _cicd.06 — Scan container images for vulnerabilities before promotion
- **Gap:** No image scanner (Trivy, Grype, Snyk) wired to the build pipeline. Only source-level audits run; built images and their OS layers are unscanned.
- **Edges (provisional):** prereq _cicd.05.

### _cicd.07 — Deliver a deploy workflow for the dev environment off `main` merges
- **Gap:** `infra/k8s/` manifests and `infra/helm/chili/` chart exist, but no workflow applies them. Spec §10.5 envisions hybrid deploy; no automation lives in `.github/workflows/`.
- **Edges (provisional):** prereq _cicd.05.

### _cicd.08 — Add staging→prod promotion workflow with manual approval gate
- **Gap:** No promotion job, no environment definitions in GitHub (no `environment:` blocks anywhere in `ci.yml`), no required reviewers. Architecture §14.2 explicitly defers "deploy/promotion jobs once environments are finalized" — this epic lands them.
- **Edges (provisional):** prereq _cicd.05, _cicd.07.

### _cicd.09 — Automate release tagging, semantic version bump, and CHANGELOG
- **Gap:** `backend/pyproject.toml` is at `0.1.0`, `chili_app/package.json` at `0.0.0`; no CHANGELOG file at repo root (`docs/wiki/CHANGELOG.md` exists but is unrelated wiki content). No release workflow, no `release-please` / `changesets` / `semantic-release` configuration.
- **Edges (provisional):** unblocks _cicd.10.

### _cicd.10 — Stand up per-PR preview environments (K8s ephemeral namespace or compose-on-runner)
- **Gap:** No preview environment workflow. Reviewers must check out branches and `make dev` locally to see frontend changes. Spec §10 lists hybrid deploy targets but no automation provisions a per-PR preview.
- **Edges (provisional):** prereq _cicd.05.

### _cicd.11 — Add backlog consistency check CI hook
- **Gap:** Spec §8 CI hook block mandates a `python scripts/backlog_consistency.py --check` step on PRs that touch `docs/backlog/`. The script itself is being built in Wave 3; the workflow change to invoke it does not exist yet.
- **Edges (provisional):** prereq _cicd.12 (script must exist), prereq the script-delivery epic in Wave 3 plan.
- **Cross-edge:** explicitly depends on the consistency-pass script delivery (spec §8). When that script lands as a story (likely under a `scripts` or `meta` namespace in Wave 2), wire this epic's prereqs to it.

### _cicd.12 — Add Alembic migration dry-run / drift gate
- **Gap:** Migrations live at `backend/database/migrations/versions/` and are runtime-applied via `make migrate`; CI never invokes `alembic upgrade head --sql` or `alembic check`. A PR can ship a model change without a matching revision and CI will pass.
- **Edges (provisional):** none.

### _cicd.13 — Run Playwright E2E suite in CI against the docker-compose stack
- **Gap:** `chili_app/playwright.config.ts` and `npm run test:e2e` exist; `CLAUDE.md` mandates Playwright for workflow verification. Nothing in `ci.yml` boots the dev stack or runs Playwright. `scripts/smoke_graph_workflow.sh` is a manual smoke harness, not a CI step.
- **Edges (provisional):** prereq _cicd.05 (preferable to run against the same images that will deploy).

### _cicd.14 — Add a performance regression tracking job
- **Gap:** No perf gate. Architecture §11.2 lists Prometheus metrics for latency, but CI never measures or compares. No Lighthouse/Web Vitals job for the SPA, no API benchmark step, no historical comparison store.
- **Edges (provisional):** none.

### _cicd.15 — Provide rollback automation for failed promotions
- **Gap:** No `workflow_dispatch` rollback workflow; no documented Helm rollback / image-tag pin procedure tied to CI. Architecture §10 describes deployment targets but offers no rollback story.
- **Edges (provisional):** prereq _cicd.07, _cicd.08.

### _cicd.16 — Add secret scanning and pre-commit hook scaffolding
- **Gap:** No `.pre-commit-config.yaml`, no gitleaks/trufflehog GitHub Action, no GitHub Advanced Security secret-scanning configuration committed. Secrets accidentally committed will not be flagged until manual review.
- **Edges (provisional):** none.

### _cicd.17 — Pin all GitHub Actions versions to commit SHAs and add a renewal cadence
- **Gap:** `ci.yml` pins to floating major tags (`actions/checkout@v4`, `actions/setup-python@v5`, etc.). Supply-chain best practice is SHA pinning with Dependabot bumps; not in place.
- **Edges (provisional):** soft prereq _cicd.04 (Dependabot must exist to keep SHAs current).

---

## Provisional cross-cutting edges out of `_cicd`

- **`_cicd.07` / `_cicd.08` ↔ `_infra.*`** — deploy/promotion workflows depend on `_infra` epics that harden Helm charts, K8s manifests, and IaC (Terraform/Pulumi). Resolve in Wave 1 review.
- **`_cicd.06` ↔ `_security.*`** — image scanning policy (severity thresholds, allow-list governance) belongs to security; CI executes it.
- **`_cicd.11` ↔ scripts/meta backlog (Wave 2)** — `scripts/backlog_consistency.py` is delivered outside `_cicd`; this epic only adds the workflow step.
- **`_cicd.13` ↔ `frontend.*` / `api.*`** — Playwright job depends on a stable seeded fixture set the SPA and API can boot against; coordinate fixture story placement.
- **`_cicd.12` ↔ `database.*`** — Alembic gate enforces a contract owned by `database/`; the gate is CI, the migration discipline is database module's story.

---

## Open questions for Wave 1 review

1. **Preview environment substrate** — K8s ephemeral namespace (matches §10.3 prod target) vs. docker-compose-on-runner (cheaper, matches dev). Pick one before _cicd.10 expands into stories.
2. **Registry choice** — GHCR vs. ECR/GAR vs. Docker Hub. Affects _cicd.05 acceptance criteria (auth, retention, multi-arch).
3. **Versioning strategy** — does the monorepo cut a single version (one tag covers all three images and the SPA) or per-package versions? Affects _cicd.09 story shape.
4. **Renovate vs. Dependabot** — Renovate handles Docker base images + GHA pins natively in one tool; Dependabot needs three separate ecosystems configured. Decide before _cicd.04 / _cicd.17.
5. **Promotion approver model** — GitHub Environments with required reviewers (simple) vs. external approval (PagerDuty/Opsgenie integration). Affects _cicd.08.
6. **E2E job runtime** — Playwright against compose-up on the runner can exceed GHA free-tier minutes; do we need a self-hosted runner story? Surfaces in _cicd.13.
7. **Coverage parity for `tools/`** — backend gate scopes to `backend/`; do `tools/sample_data/*` and `scripts/*.py` (when they grow) fall under the same 85% bar or live with a documented exemption? Surfaces in _cicd.01 / _cicd.02.
