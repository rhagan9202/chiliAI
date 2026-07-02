# _cicd backlog

> **Scope:** CI/CD pipeline — quality gates, container delivery, environment promotion, release automation, security scanning, backlog consistency.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story _cicd.01: Enforce frontend coverage gate at ≥85% parity with backend

**ID:** _cicd.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_security.12, rag.10]
**Estimated size:** S

**As a** platform engineer,
**I need** the frontend test job to fail when coverage drops below the backend's 85% floor,
**so that** TypeScript code is held to the same quality bar as Python and silent regressions cannot land.

### Current State
- `.github/workflows/ci.yml:110-111` runs `npm run test:run` (vitest) without `--coverage`; the gate enforced by `--cov-fail-under=85` for backend at `ci.yml:53` has no frontend counterpart.
- `@vitest/coverage-v8` is already listed in `chili_app/package.json` devDependencies but is never executed.
- `chili_app/vitest.config.ts` has no `coverage` block configured — no `provider`, no `reporter`, no `thresholds`.
- `CLAUDE.md` "Quality gates" section requires coverage ≥ 85% per package; frontend currently exempted by omission.

### Acceptance Criteria
- [ ] `chili_app/vitest.config.ts` declares `coverage` block with `provider: 'v8'`, lcov + text reporters, and per-metric thresholds (`lines`, `statements`, `branches`, `functions`) set to 85.
- [ ] `chili_app/package.json` adds a `test:coverage` script equivalent to `vitest run --coverage`.
- [ ] `.github/workflows/ci.yml` frontend job replaces the `npm run test:run` step with `npm run test:coverage` and uploads the resulting `coverage/lcov.info` as a build artifact (mirroring backend pattern at `ci.yml:55-61`).
- [ ] Job exits non-zero when any threshold is missed.
- [ ] `chili_app/README.md` Commands section documents the new script.

### Verification
- Run `cd chili_app && npm run test:coverage` locally; confirm it prints coverage table and exits 0 on a clean tree.
- Temporarily lower a threshold to 99 and confirm the command exits non-zero.
- Push a branch with a stub file at < 85% coverage and confirm the CI frontend job fails on the new step.

### Code touch points
- `chili_app/vitest.config.ts` (modify)
- `chili_app/package.json` (modify)
- `.github/workflows/ci.yml` (modify)
- `chili_app/README.md` (modify)

---

## Story _cicd.02: Tighten pyright strict scope and fail CI on scope regressions

**ID:** _cicd.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_cicd.10]
**Estimated size:** M

**As a** platform engineer,
**I need** CI to fail when a new top-level backend package is added without being listed in `tool.pyright.include`,
**so that** untyped modules cannot silently bypass the strict type gate.

### Current State
- `.github/workflows/ci.yml:46-50` calls bare `pyright`; the inline comment explicitly states this honours `tool.pyright.include` and that passing `.` would check the whole tree — making the include list the de-facto allowlist.
- `backend/pyproject.toml` `[tool.pyright]` `include = [...]` enumerates only modules already hardened to strict; new packages added under `backend/` are invisible to the gate until manually appended.
- No audit script flags the delta between `backend/<top-level-pkg>/` directories on disk and the `include` array.

### Acceptance Criteria
- [ ] New script `scripts/audit_pyright_scope.py` enumerates top-level Python packages under `backend/` (directories with `__init__.py` excluding `tests/`, `__pycache__/`, etc.) and compares them against the parsed `tool.pyright.include` list in `backend/pyproject.toml`.
- [ ] Script supports an allow-list file (e.g. `backend/.pyright_scope_allowlist.txt`) for packages intentionally deferred, each entry requiring a justification comment.
- [ ] Script exits non-zero on any package present on disk, absent from `include`, and absent from the allow-list.
- [ ] `.github/workflows/ci.yml` backend job runs the audit before pyright.
- [ ] `backend/README.md` documents the policy and how to add a package to the allow-list.

### Verification
- Run `python scripts/audit_pyright_scope.py` locally on clean tree; confirm exit 0.
- Add a stub `backend/sandbox/__init__.py`, re-run; confirm exit non-zero with a clear message naming `sandbox`.
- Add `sandbox` to the allow-list and re-run; confirm exit 0.

### Code touch points
- `scripts/audit_pyright_scope.py` (new)
- `backend/.pyright_scope_allowlist.txt` (new)
- `.github/workflows/ci.yml` (modify)
- `backend/README.md` (modify)

---

## Story _cicd.03: Promote pip-audit and npm audit from soft to hard fail with allow-list

**ID:** _cicd.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_cicd.10]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-24-complete-backlog-design.md

**As a** platform engineer,
**I need** vulnerability scanners to hard-fail on real findings instead of being silently retried, governed by a reviewed allow-list,
**so that** known CVEs cannot reach `main` and exception decisions are auditable.

### Current State
- `.github/workflows/ci.yml:71-76` runs `pip-audit ... --ignore-vuln GHSA-0000-0000-0000 || pip-audit --skip-editable` — the trailing `|| pip-audit --skip-editable` masks the first invocation's exit code, defeating the gate. `GHSA-0000-0000-0000` is a placeholder.
- `.github/workflows/ci.yml:124-125` runs `npm audit --audit-level=high` with no allow-list mechanism for transitive findings that have no upstream fix.
- No file under `.github/` or `docs/` governs which CVEs may be ignored, who approved them, or an expiry date.

### Acceptance Criteria
- [ ] New `.github/security/pip-audit-allowlist.yaml` and `.github/security/npm-audit-allowlist.yaml` files, each entry requiring `id`, `package`, `justification`, `approver`, `expires_on` (ISO date).
- [ ] `.github/workflows/ci.yml` pip-audit step removes the `|| pip-audit --skip-editable` retry and the placeholder GHSA, instead reading `--ignore-vuln` flags from the allow-list file.
- [ ] `.github/workflows/ci.yml` npm audit step adds a wrapper (`scripts/run_npm_audit.py` or equivalent) that diffs `npm audit --json` output against the allow-list and exits non-zero on any unsanctioned finding at `high` or above.
- [ ] CI fails when an allow-list entry's `expires_on` is in the past, forcing periodic review.
- [ ] `docs/architecture.md` §14.2 (or a new `docs/security/vuln-allowlist.md`) documents the process for adding an entry.

### Verification
- Pin a known-vulnerable dependency (e.g. an old `requests`) on a branch; confirm CI fails.
- Add the matching entry to the allow-list with a future `expires_on`; confirm CI passes.
- Set `expires_on` to yesterday; confirm CI fails with an "expired" message.

### Code touch points
- `.github/security/pip-audit-allowlist.yaml` (new)
- `.github/security/npm-audit-allowlist.yaml` (new)
- `scripts/run_npm_audit.py` (new)
- `scripts/run_pip_audit.py` (new)
- `.github/workflows/ci.yml` (modify)
- `docs/security/vuln-allowlist.md` (new)

---

## Story _cicd.04: Add Renovate config for backend, frontend, GitHub Actions, and Docker base images

**ID:** _cicd.04
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_cicd.10, _cicd.17, _plugins.06, api.13, llm.15]
**Estimated size:** M

**As a** platform engineer,
**I need** automated PRs that bump backend pip deps, frontend npm deps, GHA action pins, and Docker base images on a managed cadence,
**so that** dependency drift is detected and remediated continuously without manual sweeps.

### Current State
- No `.github/dependabot.yml`, no `renovate.json`, no Renovate GitHub App configured.
- `backend/pyproject.toml` and `chili_app/package.json` versions drift between manual updates.
- `.github/workflows/ci.yml` pins actions to floating major tags (`actions/checkout@v4`, `actions/setup-python@v5`, etc.) with no scheduled bump source — feeds directly into the SHA-pinning epic (`_cicd.17`).
- `backend/Dockerfile` and `chili_app/Dockerfile` reference base images by tag (e.g. `python:3.12-slim`, `nginx:alpine`) with no scheduled refresh.

### Acceptance Criteria
- [ ] New `renovate.json` at repo root configured with `pip_requirements`, `pep621`, `npm`, `github-actions`, and `dockerfile` managers, grouped weekly with conventional-commit titles.
- [ ] Renovate `schedule` blocks weekend evenings to avoid weekday churn.
- [ ] `dependencyDashboard: true` enabled so an issue tracks the queue.
- [ ] Renovate config explicitly enables `gomod`-equivalent automerge only for patch updates on dev deps; major bumps require human review.
- [ ] `docs/architecture.md` §14.2 documents the chosen tool (Renovate) and cadence; the open question from the auditor's notes ("Renovate vs. Dependabot") is resolved with rationale.

### Verification
- Run `npx --yes renovate-config-validator renovate.json` locally; confirm validation passes.
- After merge, confirm the Renovate dashboard issue appears within 24 h.
- Confirm at least one PR is opened for an outdated dep within a week.

### Code touch points
- `renovate.json` (new)
- `docs/architecture.md` (modify)
- `.github/CODEOWNERS` (modify — assign renovate PRs)

---

## Story _cicd.05: Build and push versioned container images on merge to main and on tags

**ID:** _cicd.05
**Status:** planned
**Prerequisites:** [_infra.10]
**Unblocks:** [_cicd.06, _cicd.07, _cicd.08, _cicd.13, agent.20, api.14, frontend.11, frontend.21]
**Estimated size:** L

**As a** release engineer,
**I need** every merge to `main` and every git tag to produce versioned, multi-arch `chili-api`, `chili-worker`, and `chili-app` images pushed to a registry,
**so that** deployers consume immutable artifacts instead of rebuilding from source per environment.

### Current State
- No workflow under `.github/workflows/` performs `docker build` or `docker push`.
- `backend/Dockerfile` and `chili_app/Dockerfile` exist and are exercised only by `make prod` locally.
- `Makefile` `prod` target uses `docker-compose -f docker-compose.prod.yaml` against local builds; no registry coordinates are configured.
- `_infra.10` will land registry/signing/SBOM decisions (GHCR vs ECR/GAR, cosign, CycloneDX) — this story consumes that decision.

### Acceptance Criteria
- [ ] New `.github/workflows/release-images.yml` triggers on push to `main` and on tags matching `v*.*.*`.
- [ ] Workflow builds `chili-api` (from `backend/Dockerfile`), `chili-worker` (from `backend/Dockerfile` with worker entrypoint), and `chili-app` (from `chili_app/Dockerfile`) as multi-arch (linux/amd64, linux/arm64) using `docker/build-push-action`.
- [ ] Images tagged with `:edge` on `main`, `:vX.Y.Z` on tags, and `:sha-<short>` always; latest pushed only for release tags.
- [ ] Images signed with cosign keyless OIDC, SBOM emitted (CycloneDX) and attached, per `_infra.10` decisions.
- [ ] Workflow uses GitHub OIDC for registry auth (no long-lived secret).
- [ ] `docs/architecture.md` §10 documents the image naming/tagging scheme.

### Verification
- Merge a no-op PR to `main`; confirm three `:edge` and three `:sha-<short>` images appear in the registry.
- Push tag `v0.0.0-test1`; confirm three `:v0.0.0-test1` images and matching cosign attestations.
- Pull each image on amd64 and arm64 and run its default command — confirms multi-arch.

### Code touch points
- `.github/workflows/release-images.yml` (new)
- `backend/Dockerfile` (modify — confirm worker entrypoint variant)
- `docs/architecture.md` (modify)

---

## Story _cicd.06: Scan container images for vulnerabilities before promotion

**ID:** _cicd.06
**Status:** planned
**Prerequisites:** [_cicd.05]
**Unblocks:** [_cicd.13, _observability.08, api.15, frontend.20, ingestion.25]
**Estimated size:** M

**As a** security-conscious release engineer,
**I need** built container images scanned for OS- and language-level CVEs with policy-driven severity gates before they are promoted,
**so that** image-layer vulnerabilities are caught alongside source-level audits.

### Current State
- `.github/workflows/ci.yml` runs only `pip-audit` and `npm audit` against source manifests — never against built images.
- No Trivy, Grype, or Snyk action configured.
- The image-scanning policy and severity thresholds (`.github/security/image-scan-policy.yaml`) that govern which findings block promotion are **owned by this story** — the prior `_security.07` prereq was mislabeled (`_security.07` is PII/secret redaction, and no separate image-scan-policy story exists). Edge dropped (2026-06-23 PM run); the policy file is defined in this story's AC.
- Once `_cicd.05` lands, immutable image artifacts exist for scanning.

### Acceptance Criteria
- [ ] `.github/workflows/release-images.yml` (from `_cicd.05`) gains a `scan` job that runs Trivy against every just-built image with severity threshold from `.github/security/image-scan-policy.yaml` (defined by this story).
- [ ] Scan results uploaded as SARIF to GitHub code scanning.
- [ ] Job fails on findings exceeding the policy threshold, blocking the registry push of higher tags (e.g. `:vX.Y.Z` not published if scan fails; `:sha-*` may still be pushed for forensic analysis).
- [ ] Allow-list referenced from `.github/security/image-scan-allowlist.yaml` (CVE id + justification + expiry, mirroring `_cicd.03` shape).
- [ ] `docs/security/image-scanning.md` documents the policy and triage workflow.

### Verification
- Build an image with a known vulnerable base (e.g. an old debian-slim); confirm scan job fails.
- Update the allow-list with a future expiry; confirm scan job passes.
- Trigger a tag release after scan failure; confirm `:vX.Y.Z` is not pushed but `:sha-*` exists.

### Code touch points
- `.github/workflows/release-images.yml` (modify)
- `.github/security/image-scan-allowlist.yaml` (new)
- `docs/security/image-scanning.md` (new)

---

## Story _cicd.07: Deliver a deploy workflow for the dev environment off `main` merges

**ID:** _cicd.07
**Status:** planned
**Prerequisites:** [_cicd.05, _infra.05]
**Unblocks:** [_cicd.08, _cicd.13, _cicd.15, api.16]
**Estimated size:** L

**As a** release engineer,
**I need** every merge to `main` to automatically deploy the resulting `:edge` images to the shared dev cluster,
**so that** developers see real-environment integration without manual `helm upgrade` invocations.

### Current State
- `infra/k8s/` flat manifests and `infra/helm/chili/` chart exist (see `_infra.02`, `_infra.05`).
- No `.github/workflows/deploy-*.yml` file applies them; deployment today is manual.
- Architecture §10.5 envisions hybrid deploy; §14.2 explicitly defers "deploy/promotion jobs once environments are finalized" — this story closes the dev half.
- `_infra.05` will land the `values-dev.yaml` profile this workflow consumes.

### Acceptance Criteria
- [ ] New `.github/workflows/deploy-dev.yml` triggers on completed `release-images.yml` (workflow_run) for `main` branch.
- [ ] Workflow uses GitHub Environment `dev` with no required reviewers (auto-deploy) and OIDC for cluster auth (`aws-actions/configure-aws-credentials` or equivalent per cloud).
- [ ] Workflow runs `helm upgrade --install chili infra/helm/chili -f infra/helm/chili/values-dev.yaml --set image.tag=sha-<short> --atomic --wait --timeout 5m`.
- [ ] Workflow records the deployed image SHA in a GitHub deployment status visible on the commit.
- [ ] On `--atomic` failure, helm rolls back automatically; workflow exits non-zero so the deployment shows red.
- [ ] `docs/architecture.md` §10 documents the dev deploy contract.

### Verification
- Merge a no-op PR; observe the deploy-dev workflow trigger after the image build completes and the GitHub deployment status flip to "success".
- `kubectl -n chili-dev describe deploy chili-api` shows the new image SHA.
- Force a helm chart syntax error on a branch; confirm `--atomic` rolls back and the workflow fails.

### Code touch points
- `.github/workflows/deploy-dev.yml` (new)
- `infra/helm/chili/values-dev.yaml` (new, may be owned by `_infra.05`)
- `docs/architecture.md` (modify)

---

## Story _cicd.08: Add staging→prod promotion workflow with manual approval gate

**ID:** _cicd.08
**Status:** planned
**Prerequisites:** [_cicd.05, _cicd.07, _infra.05]
**Unblocks:** [_cicd.15, api.27]
**Estimated size:** L

**As a** release manager,
**I need** a manually-triggered workflow that promotes a vetted image tag from staging to production behind a required-reviewer gate,
**so that** prod releases are intentional, auditable, and irreversibly distinct from dev pushes.

### Current State
- No `environment:` blocks anywhere in `.github/workflows/`; no GitHub Environments configured.
- No promotion workflow exists.
- Architecture §14.2 explicitly defers "deploy/promotion jobs once environments are finalized"; the auditor's open question on approver model (GH Environments vs PagerDuty) needs a decision before this story expands.
- Once `_cicd.07` lands the dev path and `_infra.05` lands `values-staging.yaml` / `values-prod.yaml`, this epic adds the promotion edge.

### Acceptance Criteria
- [ ] New `.github/workflows/promote.yml` with `workflow_dispatch` inputs `from_env` (staging|prod-canary), `to_env` (prod-canary|prod), and `image_tag` (must match `^v\d+\.\d+\.\d+$`).
- [ ] Workflow declares GitHub Environment `prod` with required reviewers (decision recorded in `docs/architecture.md` §10) and OIDC for cluster auth.
- [ ] Promotion runs `helm upgrade --install chili infra/helm/chili -f infra/helm/chili/values-<to_env>.yaml --set image.tag=<image_tag> --atomic --wait --timeout 10m`.
- [ ] Pre-flight job verifies the image tag exists in the registry and was scanned green by `_cicd.06`.
- [ ] Promotion outcome posts to a Slack/Teams webhook (URL stored as repo secret) and records a GitHub deployment.
- [ ] Workflow refuses to promote `:edge` or `:sha-*` tags to prod.

### Verification
- Trigger workflow with `to_env=prod`, `image_tag=v0.0.0-test1`; observe required-reviewer gate fires before the helm step runs.
- Approve and confirm helm upgrade succeeds; confirm a `prod` GitHub deployment is recorded.
- Try to promote `:sha-abc1234`; confirm pre-flight rejects.

### Code touch points
- `.github/workflows/promote.yml` (new)
- `infra/helm/chili/values-staging.yaml` (new, may be owned by `_infra.05`)
- `infra/helm/chili/values-prod.yaml` (modify, may be owned by `_infra.05`)
- `docs/architecture.md` (modify)

---

## Story _cicd.09: Automate release tagging, semantic version bump, and CHANGELOG

**ID:** _cicd.09
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L

**As a** release manager,
**I need** a release-please (or equivalent) workflow that proposes version bumps and CHANGELOG updates from conventional commits and tags accepted releases,
**so that** `pyproject.toml`, `package.json`, the changelog, and git tags stay synchronized without manual ceremony.

### Current State
- `backend/pyproject.toml` `version = "0.1.0"` placeholder; `chili_app/package.json` `version = "0.0.0"` placeholder.
- No root `CHANGELOG.md`; `docs/wiki/CHANGELOG.md` is unrelated wiki content.
- No `release-please-config.json`, no `.changeset/`, no `semantic-release` config.
- Auditor's open question on versioning strategy (single monorepo tag vs per-package versions) needs resolution; recent commits use Conventional Commits style (`feat(...):`, `fix(...):`, `docs(...):`), aligning with release-please.

### Acceptance Criteria
- [ ] New `.github/workflows/release-please.yml` runs `googleapis/release-please-action` on push to `main`.
- [ ] New `release-please-config.json` and `.release-please-manifest.json` at repo root, configured for the chosen versioning strategy (decision recorded in `docs/architecture.md` §14.2).
- [ ] Backend version bumped via `pyproject.toml` updater; frontend version bumped via `package.json` updater.
- [ ] New `CHANGELOG.md` at repo root generated from conventional commits; per-package changelogs under `backend/CHANGELOG.md` and `chili_app/CHANGELOG.md` if per-package versioning is chosen.
- [ ] Release-please opens a release PR; merging tags the commit `vX.Y.Z` which triggers `_cicd.05` image build.
- [ ] `docs/architecture.md` documents the release flow end-to-end.

### Verification
- Land a conventional commit `feat(api): add foo endpoint` on `main`; confirm release-please opens a PR within minutes proposing the next minor bump and CHANGELOG entry.
- Merge the release PR; confirm `vX.Y.Z` tag is created and `_cicd.05` workflow runs.
- Confirm `backend/pyproject.toml` and `chili_app/package.json` versions match the tag.

### Code touch points
- `.github/workflows/release-please.yml` (new)
- `release-please-config.json` (new)
- `.release-please-manifest.json` (new)
- `CHANGELOG.md` (new)
- `backend/pyproject.toml` (modify — initial version sync)
- `chili_app/package.json` (modify — initial version sync)
- `docs/architecture.md` (modify)

---

## Story _cicd.10: Provision basic per-PR preview environments

**ID:** _cicd.10
**Status:** planned
**Prerequisites:** [_cicd.02, _cicd.03, _cicd.04]
**Unblocks:** [_cicd.18]
**Estimated size:** L

### Narrative
As a reviewer,
I want each pull request to publish an isolated preview environment,
so that UI and API changes can be inspected before merge.

### Current State
Container images and CI jobs exist, but PR previews do not yet provision an isolated app stack or publish a stable reviewer URL.

### Acceptance Criteria
- [ ] Preview substrate decision is recorded for PR environments (Compose-on-runner, Kubernetes namespace, or managed preview provider).
- [ ] CI creates a per-PR environment with frontend, backend, database, and required service dependencies.
- [ ] A sticky PR comment exposes the preview URL, health URL, branch, commit SHA, and deployment status.
- [ ] Preview provisioning is idempotent for repeated pushes to the same PR.

### Verification
- [ ] Open a PR in a test repository and confirm the preview URL reaches the app health page.
- [ ] Push a second commit and confirm the sticky comment updates instead of duplicating.

### Code touch points
- `.github/workflows/**`
- `docker-compose*.yml`
- `scripts/**`
- `docs/architecture.md`

---
## Story _cicd.11: Add backlog consistency check CI hook

**ID:** _cicd.11
**Status:** in-progress
**Prerequisites:** []
**Unblocks:** [events.08]
**Estimated size:** S
**Spec:** docs/superpowers/specs/2026-05-24-complete-backlog-design.md

**As a** backlog maintainer,
**I need** the GitHub Actions CI to run `python scripts/backlog_consistency.py --check` on any PR that touches `docs/backlog/`,
**so that** duplicate IDs, unresolved prereqs, DAG cycles, status/Done mismatches, and Unblocks drift cannot land on `main`.

### Current State
- Spec `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` §8 ("CI hook") mandates this exact step.
- The `scripts/backlog_consistency.py` script does not yet exist — **it is built in Wave 3 of this very backlog-design initiative** (spec §10 "Execution waves" / Wave 3 deliverables). This story adds only the workflow invocation; the script delivery is tracked under the Wave 3 plan, not as a backlog story.
- `.github/workflows/ci.yml` has no step that runs the consistency check; no path filter or `paths:` trigger currently scopes work to `docs/backlog/`.
- The change-detection idiom in the spec uses `contains(github.event.pull_request.changed_files, 'docs/backlog/')` which is not a real Actions context expression — implementation must use `dorny/paths-filter` or a `paths:` trigger on a separate workflow file.

### Acceptance Criteria
- [x] `.github/workflows/ci.yml` (or a new `.github/workflows/backlog.yml`) runs `python scripts/backlog_consistency.py --check` whenever any file under `docs/backlog/` changes on a pull request. _(landed at `ci.yml:193`; currently runs unconditionally rather than path-scoped — see AC#2/#4 below.)_
- [ ] Uses `dorny/paths-filter@v3` (or a path-filtered `on: pull_request: paths:` trigger on a dedicated workflow) — never the bogus `contains(github.event.pull_request.changed_files, ...)` form.
- [x] Step exits non-zero on validation errors or Unblocks drift, failing the PR.
- [ ] When no `docs/backlog/` files change, the step is skipped cleanly (no spurious failures, no wasted minutes).
- [x] Step uses Python 3.12 (matching `setup-python@v5 with python-version: "3.12"` at `ci.yml:24-27`) and installs no extra dependencies (the script is stdlib-only per spec §8).
- [ ] `docs/backlog/README.md` (delivered by Wave 3) is referenced from the workflow comment so maintainers can find the gate's purpose.

### Verification
- Open a PR that introduces a duplicate story ID across two `docs/backlog/*.md` files; confirm the new step fails with a clear error.
- Open a PR with valid backlog edits; confirm the step runs and passes.
- Open a PR that touches only code (no `docs/backlog/` change); confirm the step is skipped.

### Code touch points
- `.github/workflows/ci.yml` (modify) or `.github/workflows/backlog.yml` (new)
- `docs/backlog/README.md` (referenced, not authored by this story)

---

## Story _cicd.12: Add Alembic migration dry-run / drift gate

**ID:** _cicd.12
**Status:** planned
**Prerequisites:** [database.04]
**Unblocks:** []
**Estimated size:** M

**As a** database steward,
**I need** CI to verify that `alembic upgrade head` applies cleanly against a fresh Postgres and that no SQLAlchemy model change is missing a migration revision,
**so that** a PR cannot land a schema-affecting code change without the accompanying migration.

### Current State
- Migrations live at `backend/database/migrations/versions/` and are applied at runtime via `make migrate`.
- `.github/workflows/ci.yml` never invokes Alembic; the backend job only runs ruff, pyright, pytest, pip-audit.
- A PR can ship a model change without a matching revision and CI will pass.
- `database.04` ("Detect migration drift in CI") owns the schema-drift detection contract on the database module side; this `_cicd.12` story owns the workflow plumbing that runs it.

### Acceptance Criteria
- [ ] `.github/workflows/ci.yml` backend job (or a new `db-migrations` job) starts a fresh Postgres service container (matching the dev-compose Postgres version).
- [ ] Job runs `alembic upgrade head` against the fresh DB; fails on non-zero exit.
- [ ] Job runs the drift-detection command defined by `database.04` (e.g. `alembic check` or a schema-snapshot diff helper) and fails on drift.
- [ ] Job runs only when files under `backend/database/migrations/`, `backend/**/models.py`, or `backend/database/` change — uses `dorny/paths-filter@v3`.
- [ ] Postgres service container declared with `--health-cmd "pg_isready"` so the step waits for readiness.
- [ ] `backend/database/README.md` documents the gate (likely added alongside `database.04`).

### Verification
- Open a PR that adds a column to a model without a new revision; confirm the new job fails on drift.
- Generate the revision and commit; confirm the job passes.
- Touch an unrelated file (e.g. `chili_app/src/App.tsx`); confirm the job is skipped.

### Code touch points
- `.github/workflows/ci.yml` (modify)
- `backend/database/README.md` (modify — may be owned by `database.04`)

---

## Story _cicd.13: Run baseline E2E smoke tests in CI

**ID:** _cicd.13
**Status:** planned
**Prerequisites:** [_cicd.05, _cicd.06, _cicd.07]
**Unblocks:** [_cicd.20]
**Estimated size:** L

### Narrative
As a maintainer,
I want a CI E2E job that boots the stack and runs the highest-value browser smoke tests,
so that regressions in the integrated app fail before merge.

### Current State
Browser tests exist locally, but CI does not yet own a reliable full-stack smoke lane.

### Acceptance Criteria
- [ ] CI workflow pulls or builds the required images and boots the app stack with deterministic configuration.
- [ ] Playwright smoke tests run against the live CI stack.
- [ ] The job fails on backend startup, frontend startup, or smoke-test failure.
- [ ] Logs clearly identify which service or test caused the failure.

### Verification
- [ ] Run the workflow on a PR and confirm a passing smoke result.
- [ ] Introduce a temporary smoke-test failure and confirm CI fails with useful logs.

### Code touch points
- `.github/workflows/**`
- `tests/e2e/**`
- `docker-compose*.yml`

---
## Story _cicd.14: Add a performance regression tracking job

**ID:** _cicd.14
**Status:** planned
**Prerequisites:** [_observability.05]
**Unblocks:** []
**Estimated size:** L

**As a** platform engineer,
**I need** CI to measure key API latencies and frontend Web Vitals on every PR and compare against a stored baseline,
**so that** performance regressions are caught before they reach prod and there is a historical record of trend.

### Current State
- No perf gate of any kind in `.github/workflows/`.
- Architecture §11.2 lists Prometheus metrics for latency, but CI never measures or compares.
- No Lighthouse / Web Vitals job for the SPA; no API benchmark step; no historical comparison store.
- `_observability.05` owns the SLO-target definitions (latency budgets per endpoint) this gate enforces; this story consumes them.

### Acceptance Criteria
- [ ] New `.github/workflows/perf.yml` triggers on `pull_request` (paths-filtered to backend/frontend code) and on push to `main` (always, to record the baseline).
- [ ] Frontend job runs `treosh/lighthouse-ci-action` against a preview env or the built bundle served locally; records LCP, FID, CLS, TBT against budgets in `.lighthouserc.json`.
- [ ] Backend job runs a `pytest`-driven benchmark suite under `backend/tests/perf/` (or `locust --headless` against a booted stack) hitting representative endpoints (`/chat/conversations/.../messages`, `/knowledgebases`, `/rag/search`), records p50/p95/p99.
- [ ] Results uploaded to a baseline store (GitHub artifact + comparison action, or a small object-storage bucket) keyed by commit SHA on `main`.
- [ ] PR job compares results against the most-recent `main` baseline; fails if p95 latency regresses > 20% on any tracked endpoint or any Lighthouse budget is missed.
- [ ] `docs/architecture.md` §11 documents the perf-gate budgets and the regression threshold.

### Verification
- Open a PR that adds an artificial `time.sleep(2)` to a hot endpoint; confirm the perf job fails citing the regression.
- Remove the sleep; confirm green.
- Confirm baseline artifacts accumulate on `main`.

### Code touch points
- `.github/workflows/perf.yml` (new)
- `.lighthouserc.json` (new)
- `backend/tests/perf/` (new)
- `docs/architecture.md` (modify)

---

## Story _cicd.15: Provide rollback automation for failed promotions

**ID:** _cicd.15
**Status:** planned
**Prerequisites:** [_cicd.07, _cicd.08]
**Unblocks:** []
**Estimated size:** M

**As a** release manager,
**I need** a one-click rollback workflow that pins a prior known-good image tag in any environment,
**so that** failed promotions or post-deploy incidents can be reverted without manual `helm rollback` ceremony.

### Current State
- No `workflow_dispatch` rollback workflow exists.
- No documented Helm rollback procedure tied to CI.
- Architecture §10 describes deployment targets but offers no rollback story.
- `_cicd.07` and `_cicd.08` land the forward-deploy plumbing this story inverts.

### Acceptance Criteria
- [ ] New `.github/workflows/rollback.yml` with `workflow_dispatch` inputs `environment` (dev|staging|prod), `to_revision` (helm revision number, optional — defaults to previous), and `reason` (required free-text).
- [ ] Workflow uses the same GitHub Environment gating as `_cicd.08` (required reviewers for prod).
- [ ] Workflow runs `helm rollback chili <to_revision> --wait --timeout 5m --namespace chili-<env>`.
- [ ] Workflow posts to the same Slack/Teams webhook as promotions, prefixed `[ROLLBACK]` with the reason.
- [ ] Workflow records the rollback as a GitHub deployment with `description=rollback` so the deployment timeline shows it.
- [ ] `docs/runbooks/rollback.md` documents when to use this workflow vs forward-fix and the post-rollback checklist (incident ticket, RCA owner, scheduled review).

### Verification
- Trigger workflow with `environment=dev`, leave `to_revision` blank; confirm helm rolls back one revision and the GitHub deployment appears.
- Trigger with `environment=prod`; confirm required-reviewer gate fires.
- Confirm Slack message arrives with the supplied reason.

### Code touch points
- `.github/workflows/rollback.yml` (new)
- `docs/runbooks/rollback.md` (new)

---

## Story _cicd.16: Add secret scanning and pre-commit hook scaffolding

**ID:** _cicd.16
**Status:** planned
**Prerequisites:** [_security.04]
**Unblocks:** []
**Estimated size:** M

**As a** security-conscious developer,
**I need** secret scanning to run both pre-commit locally and in CI on every PR, with a curated allow-list,
**so that** accidental commits of API keys, tokens, and credentials are caught before they reach `main` and before they reach the remote at all.

### Current State
- No `.pre-commit-config.yaml` at repo root.
- No gitleaks/trufflehog GitHub Action.
- No GitHub Advanced Security secret-scanning configuration committed (may be enabled at org level, but not tracked in repo).
- `_security.04` owns the secret-management policy (rotation, vaulting); this story owns the detection plumbing.

### Acceptance Criteria
- [ ] New `.pre-commit-config.yaml` at repo root configures `gitleaks/gitleaks` (or `trufflesecurity/trufflehog`), `ruff`, `eslint --fix`, `mixed-line-ending`, and `end-of-file-fixer` hooks.
- [ ] `pre-commit install` integrated into `make dev` setup and documented in `backend/README.md` and `chili_app/README.md`.
- [ ] New `.github/workflows/secret-scan.yml` runs `gitleaks/gitleaks-action` on every PR (full history scan on push to `main` weekly).
- [ ] Allow-list at `.gitleaks.toml` for known false positives (test fixtures, example tokens) with justification comments.
- [ ] CI step fails the PR on any unfiltered finding.
- [ ] `docs/security/secrets.md` documents the policy (no plaintext secrets in repo, where to put real secrets, how to rotate if leaked).

### Verification
- Add a fake AWS key `AKIAIOSFODNN7EXAMPLE` to a file on a branch; confirm pre-commit blocks locally and CI fails if bypassed.
- Add the entry to `.gitleaks.toml` allow-list with justification; confirm CI passes.
- Run `pre-commit run --all-files` on clean tree; confirm exit 0.

### Code touch points
- `.pre-commit-config.yaml` (new)
- `.gitleaks.toml` (new)
- `.github/workflows/secret-scan.yml` (new)
- `Makefile` (modify — `make dev` installs pre-commit)
- `backend/README.md` (modify)
- `chili_app/README.md` (modify)
- `docs/security/secrets.md` (new)

---

## Story _cicd.17: Pin all GitHub Actions versions to commit SHAs and add a renewal cadence

**ID:** _cicd.17
**Status:** planned
**Prerequisites:** [_cicd.04]
**Unblocks:** []
**Estimated size:** S

**As a** supply-chain-conscious platform engineer,
**I need** every `uses:` directive in our GitHub Actions workflows pinned to a commit SHA (not a floating tag), with Renovate keeping the pins fresh,
**so that** a hijacked third-party tag cannot inject malicious code into our CI runs.

### Current State
- `.github/workflows/ci.yml` pins actions to floating major tags: `actions/checkout@v4` (`ci.yml:22`), `actions/setup-python@v5` (`ci.yml:25`), `actions/cache@v4` (`ci.yml:30,94`), `actions/upload-artifact@v4` (`ci.yml:57,118`), `actions/setup-node@v4` (`ci.yml:89`).
- Supply-chain best practice (and StepSecurity / SLSA recommendation) is SHA pinning.
- `_cicd.04` (Renovate) is a soft prereq — without scheduled bumps, SHA pins go stale and become a maintenance burden; Renovate's `helpers:pinGitHubActionDigests` preset solves this.

### Acceptance Criteria
- [ ] Every `uses:` in every file under `.github/workflows/` pinned to a 40-char commit SHA with the human-readable tag in a trailing comment (e.g. `uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1`).
- [ ] `renovate.json` (from `_cicd.04`) extends `helpers:pinGitHubActionDigests` so future actions added are also SHA-pinned and Renovate proposes weekly bumps.
- [ ] New repo-level lint (`scripts/lint_action_pins.py` or `zgosalvez/github-actions-ensure-sha-pinned-actions`) runs in CI on PRs that touch `.github/workflows/` and fails any non-SHA pin.
- [ ] `docs/security/supply-chain.md` documents the policy.

### Verification
- Run the lint locally; confirm exit 0 on the converted workflows.
- Open a PR adding `uses: foo/bar@v1` (tag-pinned); confirm the lint fails.
- Confirm Renovate's next run proposes a SHA bump PR for an outdated action.

### Code touch points
- `.github/workflows/ci.yml` (modify)
- `.github/workflows/release-images.yml` (modify — once `_cicd.05` lands)
- `.github/workflows/deploy-dev.yml` (modify — once `_cicd.07` lands)
- `.github/workflows/promote.yml` (modify — once `_cicd.08` lands)
- (all other workflows produced by sibling _cicd stories)
- `scripts/lint_action_pins.py` (new)
- `renovate.json` (modify)
- `docs/security/supply-chain.md` (new)

## Story _cicd.18: Seed preview environments with deterministic data

**ID:** _cicd.18
**Status:** planned
**Prerequisites:** [_cicd.10]
**Unblocks:** [_cicd.19]
**Estimated size:** M

### Narrative
As a reviewer,
I want PR previews to include deterministic demo data,
so that each preview can be exercised without manual setup.

### Acceptance Criteria
- [ ] Preview startup seeds users, knowledge bases, documents, and graph data required by smoke tests.
- [ ] Seed data is deterministic per environment and does not include real secrets or customer data.
- [ ] Seed failures fail the preview job with actionable logs.

### Verification
- [ ] Create a preview and confirm seeded records are visible through API and UI flows.
- [ ] Re-run preview provisioning and confirm seed data remains idempotent.

### Code touch points
- `scripts/**`
- `.github/workflows/**`
- `backend/tests/**`

---

## Story _cicd.19: Tear down stale preview environments

**ID:** _cicd.19
**Status:** planned
**Prerequisites:** [_cicd.18]
**Unblocks:** []
**Estimated size:** M

### Narrative
As an operator,
I want preview environments to be cleaned up automatically,
so that closed PRs and abandoned branches do not leak infrastructure cost.

### Acceptance Criteria
- [ ] PR close events tear down the matching preview environment.
- [ ] Scheduled reaper removes stale previews whose PRs are closed or whose branches no longer exist.
- [ ] Teardown logs identify resources removed and resources skipped.

### Verification
- [ ] Close a test PR and confirm the preview is removed.
- [ ] Run the reaper against a stale preview fixture and confirm only stale resources are deleted.

### Code touch points
- `.github/workflows/**`
- `scripts/**`
- `docs/operations/**`

---

## Story _cicd.20: Seed CI E2E data through a deterministic fixture path

**ID:** _cicd.20
**Status:** planned
**Prerequisites:** [_cicd.13]
**Unblocks:** [_cicd.21]
**Estimated size:** M

### Narrative
As a test maintainer,
I want CI E2E tests to use deterministic fixture data,
so that browser failures are not caused by implicit local setup.

### Acceptance Criteria
- [ ] CI job loads a documented fixture bundle before Playwright tests run.
- [ ] Fixture setup covers auth/session state, knowledge bases, documents, and representative graph data.
- [ ] Fixture setup can be run locally with the same command used by CI.

### Verification
- [ ] Run fixture setup locally and in CI and compare expected record counts.
- [ ] Playwright smoke tests pass from a clean database after fixture setup.

### Code touch points
- `tests/e2e/**`
- `scripts/**`
- `.github/workflows/**`

---

## Story _cicd.21: Publish E2E artifacts and shard browser tests

**ID:** _cicd.21
**Status:** planned
**Prerequisites:** [_cicd.20]
**Unblocks:** []
**Estimated size:** M

### Narrative
As a maintainer,
I want CI E2E failures to publish artifacts and support sharding,
so that failures are diagnosable and the lane can scale as coverage grows.

### Acceptance Criteria
- [ ] CI uploads Playwright traces, screenshots, videos, and service logs on failure.
- [ ] Browser tests can be sharded across parallel jobs without sharing mutable state.
- [ ] Job summary links directly to artifacts and failed test names.

### Verification
- [ ] Force a browser failure and confirm artifacts are attached to the workflow run.
- [ ] Run sharded jobs and confirm the combined suite covers the same tests as the serial run.

### Code touch points
- `.github/workflows/**`
- `tests/e2e/**`
- `playwright.config.*`

---
