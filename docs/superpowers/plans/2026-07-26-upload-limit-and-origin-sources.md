# Upload Limit Unblock + Origin-Source Chartering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the config-driven upload limit to 512 MB, remove the silent 1 MB nginx cap, and charter the pull-based record origin-source stories (records.14–17 + REQ-INT-006) per the approved spec.

**Architecture:** Part A is a default-value change in `DomainConfig` plus nginx directives — the existing incremental 413 enforcement is untouched. Part B is documentation-only: four new backlog stories in the house format, rollup updates, and one requirements line. Spec: `docs/superpowers/specs/2026-07-26-records-origin-sources-design.md`.

**Tech Stack:** Python 3.12 / Pydantic v2 (backend config), pytest, nginx, markdown backlogs validated by `scripts/backlog_consistency.py`.

## Global Constraints

- Branch: `feat/upload-limit-and-origin-sources` (already created; spec committed on it).
- Python via project venv only: `backend/.venv/bin/pytest`, `backend/.venv/bin/pyright`, `backend/.venv/bin/ruff check --no-cache .` (ruff's cache dir is not writable).
- Never export a `DATABASE_URL` pointing at the dev `chili` DB; tests default to `chili_test`.
- pyright strict must stay clean (bare `pyright` from `backend/`); no `Any`, no suppression comments.
- If `chili_app/openapi.json` changes after the schema edit, regenerate contracts: from repo root `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`, then `cd chili_app && npm run codegen:api`. CI fails on drift.
- Backlog edits must keep `backend/.venv/bin/python scripts/backlog_consistency.py --check` (run from repo root) exiting 0.
- Commit after each task; end every commit message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Raise `ValidationConfig.max_file_size_mb` default to 512

**Files:**
- Modify: `backend/config/schema.py:304`
- Modify: `docs/wiki/contracts/domain-config.md:231`
- Test: `backend/tests/config/test_schema.py`
- Possibly regenerated: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`

**Interfaces:**
- Consumes: existing `ValidationConfig` model (`config/schema.py:302-312`).
- Produces: `ValidationConfig().max_file_size_mb == 512`; no signature changes.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/config/test_schema.py`:

```python
def test_validation_config_default_file_size_is_512_mb() -> None:
    """Spec 2026-07-26: buffered-path default raised 50 -> 512 MB.

    records.04 later re-scopes this to a Content-Length bound at 5120.
    """
    config = ValidationConfig()
    assert config.max_file_size_mb == 512
```

Use the file's existing import of `ValidationConfig` (add `ValidationConfig` to the existing `from config.schema import ...` line if absent).

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`: `.venv/bin/pytest tests/config/test_schema.py -q -k default_file_size`
Expected: FAIL with `assert 50 == 512`

- [ ] **Step 3: Change the default**

In `backend/config/schema.py` line 304 change:

```python
    max_file_size_mb: int = Field(default=50, gt=0)
```

to:

```python
    max_file_size_mb: int = Field(default=512, gt=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/config/test_schema.py -q -k default_file_size` → PASS.
Then the full guard set for regressions (tests that pin `max_file_size_mb=1` must stay green):
`.venv/bin/pytest tests/config/ tests/api/test_input_validation.py tests/api/test_records_router.py tests/api/test_kb_delete_cascade.py -q` → all PASS.

- [ ] **Step 5: Update the wiki contract mirror**

In `docs/wiki/contracts/domain-config.md` line 231 change `max_file_size_mb: int = 50                    # > 0` to `max_file_size_mb: int = 512                   # > 0` (keep column alignment).

- [ ] **Step 6: Check OpenAPI drift**

From repo root run the canonical export: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`, then `git diff --stat chili_app/openapi.json`. If it changed, run `cd chili_app && npm run codegen:api` and stage both generated files. If unchanged, nothing to stage.

- [ ] **Step 7: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_schema.py docs/wiki/contracts/domain-config.md chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(config): raise default upload limit 50 -> 512 MB (spec 2026-07-26)"
```

(If Step 6 produced no diff, drop the two chili_app paths from `git add`.)

---

### Task 2: Disable nginx body-size cap in both prod configs

**Files:**
- Modify: `chili_app/nginx.conf` (server block starting line 6)
- Modify: `chili_app/nginx-tls.conf` (the `listen 443 ssl http2;` server block starting line 16)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: prod nginx no longer 413s before the API's DomainConfig-driven gate.

- [ ] **Step 1: Edit `chili_app/nginx.conf`**

Immediately after the `server_name _;` line (line 8) insert:

```nginx

    # Body size checking is delegated to the API gateway, whose limit is
    # DomainConfig-driven (validation.max_file_size_mb) and enforced
    # incrementally with 413. nginx's 1 MB default would silently override it.
    client_max_body_size 0;
```

- [ ] **Step 2: Edit `chili_app/nginx-tls.conf`**

Insert the identical block after the `server_name _;` line of the **:443** server block only (the :80 block is a pure 301 redirect and never reads bodies).

- [ ] **Step 3: Verify syntax**

Run: `docker run --rm -v /home/rdhagan92/chiliAI/chili_app/nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t 2>&1 | tail -2`
Expected: `syntax is ok` / `test is successful` — if it instead fails resolving upstream `api`, that is a known limitation of testing outside compose; rely on the Task 6 prod smoke instead and note it.

- [ ] **Step 4: Commit**

```bash
git add chili_app/nginx.conf chili_app/nginx-tls.conf
git commit -m "fix(nginx): disable client_max_body_size — app gate is authoritative (spec 2026-07-26)"
```

---

### Task 3: Security checklist + records README notes

**Files:**
- Modify: `docs/security_checklist.md` (Input-validation bullet, lines 74-76 area)
- Modify: `backend/records/README.md` (add a limits note near its upload/API section)

**Interfaces:** documentation only.

- [ ] **Step 1: Extend the input-validation bullet**

In `docs/security_checklist.md`, directly after the existing bullet that begins `- **Input validation.**` (line 74) and its continuation lines, add a new bullet:

```markdown
- **Upload size limits.** File uploads are bounded by the DomainConfig-driven
  `validation.max_file_size_mb` (default 512 MB, pack-overridable), enforced
  incrementally with HTTP 413 in `api/shared` upload readers. nginx body-size
  checking is deliberately disabled (`client_max_body_size 0`) so the config
  gate is the single authority — a fixed nginx number silently contradicted
  per-pack limits (it defaulted to 1 MB). Multi-GB uploads become safe when
  records.04 (streaming parse) lands; pull-based origins that bypass HTTP
  upload entirely are chartered as records.14–17.
```

- [ ] **Step 2: Records README note**

In `backend/records/README.md`, in the section describing the upload endpoints (find the `POST /records/{kb}/files` description), append:

```markdown
Upload size is bounded by `validation.max_file_size_mb` (default 512 MB;
enforced incrementally with 413). The buffered read path makes this the
practical ceiling until records.04 (streaming) lands; pull-based origins
(object store / HTTP / stream — records.14–17) ingest by reference and are
not subject to HTTP upload limits.
```

- [ ] **Step 3: Commit**

```bash
git add docs/security_checklist.md backend/records/README.md
git commit -m "docs: record 512 MB upload default + nginx delegation (spec 2026-07-26)"
```

---

### Task 4: Charter records.14–17 in the backlog

**Files:**
- Modify: `docs/backlog/records.md` (scope line 3; append 4 stories after records.13, which ends at line 559; update records.04's `Unblocks`)
- Modify: `docs/backlog/storage.md` (storage.01's `Unblocks` list)
- Modify: `docs/backlog/README.md` (rollup row line 39; module link line 146)

**Interfaces:**
- Produces: story IDs `records.14`–`records.17` referenced by Task 5's REQ line and by the spec.

- [ ] **Step 1: Update the records scope line**

Line 3 of `docs/backlog/records.md`: append to the scope sentence so it ends: `…observability, streaming, pull-based origin sources (object store / HTTP / stream).`

- [ ] **Step 2: Append the four stories**

Add after the end of records.13 (current end of file), matching the house template exactly:

```markdown
## Story records.14: Object-store pull origin (S3 / MinIO / blob / local FS) by reference

**ID:** records.14
**Status:** planned
**Prerequisites:** [storage.01, records.04]
**Unblocks:** [records.15, records.16, records.17]
**Estimated size:** L

**As a** data engineer staging multi-GB feed files,
**I need** feeds to accept an object reference (store key or `s3://` URI) that the worker pulls and streams through the records pipeline,
**so that** bulk data never traverses an HTTP upload body and size limits stop applying to it.

### Current State
- `IngestionSourceConfig.type` is `Literal["file_upload", "api_push"]` (`backend/config/schema.py:64`) — no pull origin exists.
- The ObjectStore protocol has no streaming read; storage.01 adds `get_stream` (`docs/backlog/storage.md`).
- `read_upload_file_with_limit` (`backend/api/routers/records.py:45`) is the only inbound byte path for records files.
- Design: `docs/superpowers/specs/2026-07-26-records-origin-sources-design.md` §3.

### Acceptance Criteria
- [ ] `RecordOriginSource` protocol in `backend/records/adapters/protocols.py`: `iter_rows(ref: str) -> Iterator[dict[str, object]]` streaming rows; in-memory adapter for tests (REQ-INT-003).
- [ ] `ObjectStoreOriginSource` adapter streams via `ObjectStore.get_stream` (storage.01) and reuses the records.04 streaming CSV/JSONL parsers; accepts bare keys and `s3://bucket/key` URIs.
- [ ] `IngestionSourceConfig.type` gains `"object_store"`; feed config validates that object-store feeds name an accepted format.
- [ ] `POST /records/{kb}/feeds/{feed}/pulls` (RBAC `analyst`) registers a pull `{ref: str}` and returns a 202 receipt with `correlation_id`; the worker executes the pull via a new `records.pull.requested` event handled in `agent/coordinator.py`, ending in the existing validate → dedup → persist → `records.ingested` path.
- [ ] Pull failures publish the existing ingest-failure surface (no new alert path); receipts are queryable through the existing run timeline.
- [ ] Integration test against MinIO (`@pytest.mark.integration`) pulls a staged CSV object end-to-end.
- [ ] `backend/records/README.md` documents the origin model.

### Verification
- `pytest backend/tests/records/ backend/tests/api/test_records_router.py -q` green; coverage ≥ 85% on new modules.
- `pytest -m integration -k object_store_origin` green with the dev stack up.
- Manual: register a pull for a staged `sample_data` object; `records.ingested` appears with the object's row count.

### Code touch points
- `backend/records/adapters/protocols.py` (modify — `RecordOriginSource`)
- `backend/records/adapters/sources/object_store_source.py` (create)
- `backend/config/schema.py` (modify — source type literal)
- `backend/api/routers/records.py` (modify — pull registration endpoint)
- `backend/agent/coordinator.py` (modify — pull execution handler)
- `backend/events/types.py` (modify — `RecordsPullRequestedEvent`)
- `backend/tests/records/test_object_store_source.py` (create)

## Story records.15: HTTP API pull origin

**ID:** records.15
**Status:** planned
**Prerequisites:** [records.14]
**Unblocks:** []
**Estimated size:** M

**As a** data engineer whose upstream publishes export URLs,
**I need** a feed origin that fetches a remote HTTP(S) export and streams it through the records pipeline,
**so that** scheduled exports ingest without an intermediate manual download/upload.

### Current State
- No outbound-fetch origin exists; records.14 establishes the pull surface and `RecordOriginSource` protocol this story implements against.
- Auth-by-env-var precedent: `GraphDbConfig.auth_env_var` (`backend/config/schema.py:110`).

### Acceptance Criteria
- [ ] `HttpPullOriginSource` adapter implements `RecordOriginSource` with chunked `httpx` streaming; `IngestionSourceConfig.type` gains `"http_pull"` with `endpoint` required and optional `auth_env_var` (bearer header).
- [ ] Response size guard: abort with a recorded failure past a configurable `max_pull_bytes` (default 10 GiB); malformed/absent Content-Length handled (precedent: `tests/ingestion/test_service.py` remote content-length cases).
- [ ] Paginated-GET support via an optional `next_link_field` config key (JSON responses only); CSV/JSONL exports fetch single-shot streams.
- [ ] Unit tests with a stub transport cover success, auth header, oversize abort, and pagination.

### Verification
- `pytest backend/tests/records/test_http_pull_source.py -q` green; coverage ≥ 85%.
- Manual: point a feed at a local `python -m http.server` export and confirm `records.ingested`.

### Code touch points
- `backend/records/adapters/sources/http_pull_source.py` (create)
- `backend/config/schema.py` (modify — source type literal + fields)
- `backend/tests/records/test_http_pull_source.py` (create)

## Story records.16: Stream origin (Redis Streams first)

**ID:** records.16
**Status:** planned
**Prerequisites:** [records.14]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator with continuously produced records,
**I need** a feed origin that consumes rows from an event stream with its own consumer group,
**so that** near-real-time sources feed the same validate/dedup/persist pipeline as files.

### Current State
- Redis Streams is the existing event transport (`backend/events/adapters/`); no records-facing stream consumption exists.
- Kafka has no adapter — per the architecture rules it must not enter `DomainConfig` literals until one exists (roadmap).

### Acceptance Criteria
- [ ] `StreamOriginSource` consumes a configured Redis stream key with consumer group `records:<feed>`, batching rows (configurable batch size / max wait) into pipeline submissions.
- [ ] `IngestionSourceConfig.type` gains `"stream"` with `stream_key` required; validation rejects it when the event backend is in-memory.
- [ ] At-least-once semantics documented; per-row dedup relies on the existing records content-hash idempotency (records.02).
- [ ] Worker lifecycle: consumption starts/stops with the coordinator; unacked entries are reclaimed on restart (respecting the CHILI_EVENT_RECLAIM_MIN_IDLE_MS trap noted in sprint 2026-28 ops lessons).
- [ ] Integration test (`@pytest.mark.integration`) produces rows to a test stream and asserts persisted records.

### Verification
- `pytest backend/tests/records/test_stream_source.py -q` green; `pytest -m integration -k stream_origin` green with the stack up.
- Manual: `redis-cli XADD` a row envelope; observe `records.ingested`.

### Code touch points
- `backend/records/adapters/sources/stream_source.py` (create)
- `backend/config/schema.py` (modify — source type literal + fields)
- `backend/agent/coordinator.py` (modify — consumer lifecycle)
- `backend/tests/records/test_stream_source.py` (create)

## Story records.17: Presigned-URL direct upload path for large interactive files

**ID:** records.17
**Status:** planned
**Prerequisites:** [storage.01, records.14]
**Unblocks:** []
**Estimated size:** M

**As an** analyst uploading a very large file from the browser,
**I need** the app to upload directly to object storage via a presigned URL and then register the object by reference,
**so that** interactive uploads scale past API-buffered limits without traversing the gateway.

### Current State
- Browser uploads go through `apiUploadWithProgress` (`chili_app/src/lib/apiClient.ts`) as multipart bodies to the API.
- storage.01 charters `generate_presigned_url`; records.14 charters register-by-reference — this story is the frontend/API glue.

### Acceptance Criteria
- [ ] `POST /records/{kb}/feeds/{feed}/uploads:presign` (RBAC `analyst`) returns `{url, key, expires_in}` for S3/MinIO backends; 409 with a clear detail on backends without presign support (local FS/in-memory).
- [ ] Frontend upload flow: files past a configurable threshold (default 256 MB) use presign → PUT direct → register pull by `key` via the records.14 endpoint; smaller files keep the existing multipart path with its progress bar.
- [ ] Progress + Retry UX parity with the existing `apiUploadWithProgress` behavior.
- [ ] Playwright e2e against the full stack (MinIO) exercises the presigned path with a >threshold synthetic CSV.

### Verification
- `npm run test:run` green; `make test-e2e` includes the presigned-path spec, green.
- Manual: upload a 300 MB synthetic CSV in the browser; observe direct-to-MinIO traffic and a registered pull.

### Code touch points
- `backend/api/routers/records.py` (modify — presign endpoint)
- `chili_app/src/lib/apiClient.ts` (modify — threshold branch)
- `chili_app/src/api/records.ts` (modify — presign + register calls)
- `chili_app/e2e/` (create — presigned upload spec)
```

- [ ] **Step 3: Back-reference `Unblocks`**

In `docs/backlog/records.md`, records.04's `**Unblocks:**` list: add `records.14` (keep existing entries). In `docs/backlog/storage.md`, storage.01's `**Unblocks:**` list: add `records.14, records.17` (keep existing entries).

- [ ] **Step 4: Update the backlog README rollup**

`docs/backlog/README.md` line 39: change `| records.md | 10 | 2 | 1 | 13 | 7% |` to `| records.md | 14 | 2 | 1 | 17 | 6% |`. Line 146: change the link line to `- [records.md](records.md) — structured/tabular ingestion (CSV/JSONL/api-push + pull-based origins)`. If the file carries a total-story count elsewhere, let the checker's output correct you.

- [ ] **Step 5: Run the invariant checker**

From repo root: `backend/.venv/bin/python scripts/backlog_consistency.py --check`
Expected: exit 0. If it reports rollup or unblocks mismatches, fix exactly what it names and re-run.

- [ ] **Step 6: Commit**

```bash
git add docs/backlog/records.md docs/backlog/storage.md docs/backlog/README.md
git commit -m "docs(backlog): charter records.14-17 pull-based origin sources (spec 2026-07-26)"
```

---

### Task 5: Add REQ-INT-006 to requirements.md

**Files:**
- Modify: `docs/project/planning/requirements.md` (after REQ-INT-005, line 196)

**Interfaces:** consumed by PM traceability; references records.14–17 from Task 4.

- [ ] **Step 1: Insert the requirement**

After the REQ-INT-005 line insert:

```markdown
- **REQ-INT-006** — The system shall ingest structured records from pull-based origin sources — object store (local FS/S3/MinIO), HTTP API, and event stream — by reference, through the records source-adapter protocol, without HTTP upload size constraints (stories records.14–records.17).
```

- [ ] **Step 2: Commit**

```bash
git add docs/project/planning/requirements.md
git commit -m "docs(requirements): REQ-INT-006 pull-based record origin sources"
```

---

### Task 6: Full gates + prod nginx smoke

**Files:** none new — verification only (fix anything red before finishing).

- [ ] **Step 1: Backend gates**

From `backend/`: `.venv/bin/pytest --cov -q 2>&1 | tail -5` (≥ 85%, all green), `.venv/bin/pyright 2>&1 | tail -3` (0 errors), `.venv/bin/ruff check --no-cache . | tail -2` (clean).

- [ ] **Step 2: Frontend gates** (only if Task 1 Step 6 regenerated contracts)

From `chili_app/`: `npm run lint && npm run test:run 2>&1 | tail -3 && npm run build 2>&1 | tail -3` — all green.

- [ ] **Step 3: Prod nginx smoke (the spec's regression guard)**

Run `make prod` (built images; ensure the dev stack is down first with `make down`). Then upload a >1 MB file through nginx:

```bash
mkdir -p /tmp/smoke && head -c 2000000 /dev/zero | tr '\0' 'a' > /tmp/smoke/smoke_2mb.txt
curl -s -o /dev/null -w '%{http_code}\n' -F "files=@/tmp/smoke/smoke_2mb.txt;type=text/plain" \
  http://localhost/api/knowledge-bases/smoke-test/documents
```

Expected: anything but `413` (the pre-fix config 413'd at nginx before auth or routing ran, so a `401`/`404`/`422` here proves the 2 MB body traversed nginx and reached the API). No token or real KB id is needed for this proof; for the positive-path 202, take a KB id from `curl -s http://localhost/api/knowledge-bases | jq` and an analyst token per `docs/demo/README.md`. Tear down with the prod-stack stop target when done.

- [ ] **Step 4: Doc reconciliation check**

Confirm no doc still claims the 50 MB default: `grep -rn "50 MB\|default=50" --include='*.md' docs/ backend/ chili_app/README.md | grep -i file` → expect no hits about upload size.

- [ ] **Step 5: Final commit (if gates produced fixes)**

```bash
git add -A && git commit -m "chore: gate fixes for upload-limit branch"
```

Only commit if something changed; otherwise the branch is complete.
