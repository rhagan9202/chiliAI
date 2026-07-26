# Upload Size Limits + Pull-Based Record Origin Sources — Design

- **Date:** 2026-07-26
- **Status:** Approved (brainstorming session with PO)
- **Drivers:** Real-world feed files are very large (full CMS DE-SynPUF slices run to multiple GB). The release version must ingest from any reasonable origin — object store, S3/blob, local FS, HTTP API, stream — not just browser multipart upload.

## 1. Problem

Three separate constraints cap upload size today, and only one of them is visible:

1. **App limit** — `ValidationConfig.max_file_size_mb` (`config/schema.py`), default 50 MB, `gt=0` so it cannot be disabled. Enforced incrementally (stream-and-abort) by `read_upload_file_with_limit` in both upload routers (`api/routers/knowledgebases.py` documents, `api/routers/records.py` records). No pack overrides it.
2. **Hidden prod cap** — neither `chili_app/nginx.conf` nor `nginx-tls.conf` sets `client_max_body_size`; nginx defaults to **1 MB**, silently overriding the app limit in prod. Dev bypasses nginx, which masks the discrepancy.
3. **Memory architecture** — after the limit check both routers fully buffer the file (`b"".join`, sha256, full CSV/JSONL parse to `list[dict]`). The 50 MB limit protects this buffered pipeline; raising it far without streaming (records.04) invites OOM, not throughput.

Beyond HTTP upload, the only feed source types are `file_upload` and `api_push`
(`IngestionSourceConfig.type`). There is no pull-by-reference origin at all.

## 2. Decisions (Part A — immediate unblock)

- **A1.** Raise `ValidationConfig.max_file_size_mb` default **50 → 512** (MB). Packs may override in either direction. 512 MB covers every staged demo/sample feed file with margin while keeping worst-case buffered parse memory (~2–3 GB) inside a reasonably provisioned API container. The 5 GB end-state ships with records.04's streaming refactor, which re-scopes the limit to a Content-Length bound — that story's AC already says so.
- **A2.** Add `client_max_body_size 0;` to both nginx confs (server block). Rationale: the app limit is DomainConfig-driven and per-pack; any fixed nginx number will eventually contradict a pack silently (exactly what the 1 MB default does today). The app enforces incrementally, so a rejected oversized body costs streamed bandwidth, not memory. Revisit if an edge/WAF layer is introduced (tracked under `_security.md` hardening).
- **A3.** Documentation: update the E10-S10 input-validation notes (`docs/security_checklist.md`), `backend/records/README.md`, and `chili_app/README.md` where the 50 MB default is stated.

**Not in Part A:** any streaming change (records.04's scope), any origin adapter (Part B), Content-Length pre-check (arrives with records.04's semantics change).

## 3. Decisions (Part B — chartered release work, not implemented now)

### Architecture

A `RecordOriginSource` protocol in `backend/records/` (protocols + adapters layout per the architecture hard rules). Every origin normalizes to a **streaming row iterator** (`Iterator[dict[str, object]]`) feeding the same validate → dedup → persist → `records.ingested` path used today. Pull execution happens in the **worker** (origin pulls are pipeline work, not gateway work); the API only registers a pull request and returns a receipt. Data arrives **by reference** — no HTTP body carries bulk data, so upload limits do not apply to origins.

Dependency spine: **storage.01** (ObjectStore `get_stream`/presigned URLs) and **records.04** (streaming parse + chunked persist) are prerequisites for every origin story.

### Chartered stories

- **records.14 — Object-store pull origin** (`type: object_store`). Feed accepts an object reference (key or `s3://…` URI) via `POST /records/{kb}/feeds/{feed}/pulls`; worker streams via the pluggable ObjectStore adapters. One story deliberately covers **S3, MinIO, blob-style stores, and local FS** — they are one adapter family already. Prereqs: storage.01, records.04.
- **records.15 — HTTP API pull origin** (`type: http_pull`). Fetch a remote export/API URL; auth via env-var-named secret (existing `auth_env_var` pattern); paginated-GET support charted as an AC, not a separate story. Prereqs: records.04; records.14 (shares the pull-registration surface).
- **records.16 — Stream origin** (`type: stream`). Consume rows from an event stream; **Redis Streams adapter first** (transport exists). Kafka remains roadmap-only — no config literal until an adapter exists, per the architecture rules. Prereqs: records.04, records.14.
- **records.17 — Presigned-URL browser upload path.** For very large *interactive* uploads: browser → MinIO/S3 direct via presigned URL (storage.01), then register-by-reference through the records.14 pull surface. Complements, does not replace, multipart upload. Prereqs: storage.01, records.14.

### Requirements traceability

Add **REQ-INT-006**: "The system shall ingest structured records from pull-based origin sources — object store (local FS/S3/MinIO), HTTP API, and event stream — by reference, through the records source-adapter protocol, without HTTP upload size constraints."

### Rejected alternative

An ELT-connector sidecar service (Airbyte-style puller container): violates the three-path cross-module rule, adds heavy infra, and duplicates the adapter pattern the platform already standardizes on.

## 4. Testing

- **Part A:** unit tests asserting the new default (512) and pack-override behavior; existing 413 tests keep passing (they pin `max_file_size_mb=1` explicitly); prod-compose smoke: an upload > 1 MB traverses nginx (guards against the silent-cap regression).
- **Part B (per story, at implementation time):** in-memory origin adapters for fast tests per REQ-INT-003; integration tests against MinIO for records.14/17; memory-bound assertions inherited from records.04's harness.

## 5. Out of scope

- Document (`ingestion/`) pull origins — same pattern, separate later charter once records proves it.
- GCS/Azure-native adapters (roadmap; enter `DomainConfig` literals only when adapters exist).
- Kafka stream adapter (roadmap, same rule).
- Live external system connectors excluded by REQ-HOUSING-007 stay excluded.
