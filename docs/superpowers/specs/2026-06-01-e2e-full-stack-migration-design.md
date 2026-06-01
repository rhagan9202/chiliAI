# Design: Migrate the e2e suite to run against the full stack (`make dev`)

> Status: approved 2026-06-01
> Drives toward CLAUDE.md rule: "E2E tests MUST run against the full running stack … `page.route`/mock fixtures must never stand in for the component, endpoint, or integration under test."

## 1. Problem

All 14 Playwright specs currently mock every API via `page.route` (`e2e/helpers/mocks.ts`) and a fake analyst session. That violates the full-stack rule: the subject under test (API, worker, persistence, auth) is mocked away. Three specs (`alert-acknowledge`, `investigation-workbench`, `rag-chat`) already fail because they leak to a non-running backend (`ECONNREFUSED :8000`).

Goal: run the e2e suite against the real running stack (`make dev` — app + api + worker + Redis/Neo4j/Qdrant/MinIO/Postgres), with real auth and real, pipeline-produced data.

## 2. Constraints discovered

- **Vite already proxies** `/api` → `${VITE_API_PROXY_TARGET}` (`api:8000` in compose). The compose serves the app on `:5173`. Playwright's `reuseExistingServer: true` makes it target the compose's `:5173` rather than starting its own Vite.
- **Anonymous dev user is viewer-only** (`auth.py:build_anonymous_user` → `roles=["viewer"]`). Write specs (case create/patch/feedback, promote, alert acknowledge) need **analyst**.
- **Alerts & evidence have no public create API** — they are produced only by the worker pipeline (records/docs → graph → risk → monitoring → explainability). KBs and cases are API-creatable; alerts/evidence are not.

## 3. Decisions (confirmed)

1. **Auth:** dev-gated analyst override env. `build_anonymous_user()` reads `CHILI_DEV_ANONYMOUS_ROLE` (default `viewer`). A non-viewer value is honored only when `CHILI_ENV != "production"`; under production it is ignored (stays viewer). Default behaviour unchanged.
2. **Data seeding:** real pipeline — create a KB, ingest a fixture records file, poll `/alerts` + `/evidence-packs/{id}` until the worker produces them, then assert the UI against that real data.
3. **Orchestration:** a `make test-e2e` target that **first** runs `docker compose … down -v` (clean slate; avoids multiple stacks / port collisions), then `up -d --build`, waits for api `/health`, runs Playwright, then `down`. CI runs the same target.

## 4. Components

### 4.1 Backend — dev-gated analyst override
- `backend/api/middleware/auth.py`: `build_anonymous_user()` resolves the role from `CHILI_DEV_ANONYMOUS_ROLE` (default `"viewer"`). If the value is not `viewer` and `CHILI_ENV == "production"`, force `viewer` (the override is non-production only). Validate the role against the known set (`viewer/analyst/service/admin`); unknown → `viewer`.
- Tests (`backend/tests/api/test_auth.py` or similar): default → viewer; `analyst` + non-prod → analyst; `analyst` + production → viewer.

### 4.2 Compose env
- `docker-compose.dev.yaml`: add to the **api** and **worker** service env:
  `- CHILI_DEV_ANONYMOUS_ROLE=${CHILI_DEV_ANONYMOUS_ROLE:-viewer}`. Default `viewer` (today's behaviour); `make test-e2e` exports `analyst`.

### 4.3 `make test-e2e` (Makefile)
```
test-e2e:
	docker compose -f docker-compose.dev.yaml down -v
	CHILI_DEV_ANONYMOUS_ROLE=analyst docker compose -f docker-compose.dev.yaml up -d --build
	scripts/wait_for_stack.sh            # poll http://localhost:8000/health until ready (bounded)
	cd chili_app && npm run test:e2e
	docker compose -f docker-compose.dev.yaml down
```
`npm run test:e2e:full` (or the existing `test:e2e`) runs Playwright against the reused `:5173`. A `scripts/wait_for_stack.sh` bounded health-poll guards startup.

### 4.4 Seeding — `e2e/global-setup.ts`
- Node-side setup (runs once before specs) hits the stack over `http://localhost:5173/api/...`:
  1. `POST /knowledgebases` → KB id.
  2. `POST /records/{kb}/files` with a fixture CSV designed to cross risk/monitoring thresholds (see §6).
  3. Poll `GET /alerts` until ≥1 alert; capture an alert id + entity id + its `evidence_pack_id`.
  4. Poll `GET /evidence-packs/{id}?knowledge_base_id={kb}` until 200.
  5. Write the captured ids to `e2e/.seeded.json` (gitignored).
- `e2e/helpers/seeded.ts`: typed loader that reads `.seeded.json` and exposes `{ knowledgeBaseId, alertId, entityId, evidencePackId }` to specs. Replaces the per-spec `FAKE_*` constants.
- Wired via `globalSetup` in `playwright.config.ts`.

### 4.5 Spec migration
- Delete `e2e/helpers/mocks.ts`; rewrite all 14 specs to drive the real app against `seeded.ts` data: navigate real routes, perform writes through the UI (create case / promote / feedback / acknowledge) → real API → real persistence, and assert on real responses.
- `alert-acknowledge`, `investigation-workbench`, `rag-chat` become real and should pass with live data.

## 5. Phasing

1. **Harness:** §4.1 auth override + §4.2 compose + §4.3 make target + §4.4 globalSetup/seeded loader, proven against the **API-seedable** specs (KB, cases CRUD/promote).
2. **Pipeline specs:** migrate alert/evidence/investigation/rag specs once the seed fixture reliably emits alerts.
3. **Cleanup:** remove `mocks.ts`, retire `FAKE_*`, update `chili_app/README.md` + e2e docs.

## 6. Risks & mitigations

- **Stack bring-up in this environment** is heavy (image builds + 5 infra services). Mitigation per directive: if `make dev` cannot be brought up, **fix the Docker setup** (compose/Dockerfile/healthcheck/env issues) until it does; only as a last resort fall back to a host-process stack for local validation.
- **Deterministic alert fixture:** crafting records that reliably trip thresholds under `medicare_fraud_cms_desynpuf` is the key unknown. Mitigation: use the existing Tennessee/DE-SynPUF fixtures or a small hand-built CSV tuned to the config's risk thresholds; poll with a generous bounded timeout; if thresholds are too data-sensitive, pin an e2e config overlay with deterministic thresholds.
- **Pipeline latency/flakiness:** poll-until-present with backoff and a single generous global timeout; seed once in `globalSetup`, not per-spec.

## 7. Non-goals
- No change to production auth behaviour (override is non-production only).
- No new public alert-creation API (alerts stay pipeline-produced).
- Visual-regression/screenshot testing is out of scope.
