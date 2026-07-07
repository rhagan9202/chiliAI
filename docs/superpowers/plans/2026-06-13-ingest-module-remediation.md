# Ingest Module Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the eight reviewed ingestion module and integration issues so uploaded/remote documents are durably enqueued, safely retried, bounded in memory, and correctly surfaced to clients.

**Status:** Completed. All eight tasks were implemented through subagents, reviewed, and verified from the parent thread.

**Architecture:** Use the existing `IngestionService`, object store, event bus, workflow, and API router boundaries. Prefer small additions to service models and recovery abstractions over large rewrites. Where tasks share files, execute sequentially and preserve earlier behavior/tests.

**Tech Stack:** FastAPI, Pydantic v2, pytest, Pyright, existing object-store/event-bus abstractions, React Query frontend.

---

## Execution Order

1. Task 1 and Task 2 are tightly coupled; complete Task 2 first if implementing durable recovery store methods, then Task 1 uses those methods to decide whether a duplicate object must be republished.
2. Task 3, Task 4, Task 5, and Task 8 can run in parallel if their write scopes stay narrow.
3. Task 6 must run after Task 5 because both edit `backend/ingestion/parsers/remote.py`.
4. Task 7 must run after Task 1/2 because it edits `backend/ingestion/service.py`.

## Task 1: Prevent Orphan Workflows on Stored-but-Unpublished Upload Retries

**Issue:** `IngestionService.register_documents()` suppresses `documents.uploaded` when the source object already exists, while the KB upload route starts a workflow for any returned receipt. A retry after publish failure can create a workflow with no event.

**Files:**
- Modify: `backend/ingestion/service_models.py`
- Modify: `backend/ingestion/service.py`
- Modify: `backend/api/routers/knowledgebases.py`
- Test: `backend/tests/ingestion/test_service.py`
- Test: `backend/tests/api/test_knowledgebases_router.py`

**Plan:**

- [ ] Add `enqueued: bool = False` to `DocumentReceipt`.
- [ ] In `register_documents`, set `enqueued=True` only for references included in the `DocumentsUploadedEvent`.
- [ ] If the object already exists but the recovery store reports a pending `documents.uploaded` marker for the same KB/document/content hash, include it in the new event so retries actually re-enqueue.
- [ ] After a successful publish, clear matching recovery markers.
- [ ] In the KB upload route, start `documents.uploaded` workflow only when at least one receipt has `enqueued=True`.
- [ ] Add tests:
  - service duplicate without recovery marker returns `enqueued=False` and publishes no second event;
  - service retry with recovery marker returns `enqueued=True`, republishes, and clears the marker;
  - API duplicate/suppressed receipt does not start a workflow.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/ingestion/test_service.py backend/tests/api/test_knowledgebases_router.py -q
```

## Task 2: Make Ingestion Recovery Durable and Replayable

**Issue:** `InMemoryIngestionRecoveryStore` is process-local and there is no replay path. Markers disappear on restart and cannot restore stranded source objects.

**Files:**
- Modify: `backend/ingestion/recovery.py`
- Modify: `backend/ingestion/service.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/ingestion/test_service.py`
- Test: `backend/tests/api/test_dependencies.py`
- Test: `backend/tests/agent/test_coordinator.py`

**Plan:**

- [ ] Define an `IngestionRecoveryStore` protocol-like base with `add_marker`, `list_markers`, `find_marker`, and `remove_marker`.
- [ ] Keep `InMemoryIngestionRecoveryStore` implementing the interface for tests.
- [ ] Add an object-store-backed recovery store that persists marker JSON under a deterministic prefix such as `recovery/ingestion/{marker_id}.json`.
- [ ] Wire API and worker dependencies to use the object-store-backed recovery store when an object store is available.
- [ ] Add `IngestionService.replay_recovery_markers()` that:
  - lists recovery markers for `documents.uploaded`;
  - reconstructs `DocumentsUploadedEvent` from marker plus stored object metadata/media type;
  - publishes the event;
  - deletes the marker after publish succeeds.
- [ ] Invoke replay once during worker startup before normal drain.
- [ ] Add tests:
  - markers survive by reading them back from an object-store-backed instance;
  - replay publishes `documents.uploaded` and removes marker;
  - failed replay leaves marker in place.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/ingestion/test_service.py backend/tests/api/test_dependencies.py backend/tests/agent/test_coordinator.py -q
```

## Task 3: Make Re-Upload Replacement Atomic Enough to Avoid Data Loss

**Issue:** The KB upload route deletes the prior graph/vector/document metadata before the new upload is safely stored/enqueued.

**Files:**
- Modify: `backend/api/routers/knowledgebases.py`
- Test: `backend/tests/api/test_knowledgebases_router.py`

**Plan:**

- [ ] Move destructive replacement cleanup until after `register_documents()` succeeds and at least one receipt is enqueued.
- [ ] Preserve `replaced_document_id` in the returned receipt.
- [ ] If cleanup of old graph/vector/source artifacts fails after new enqueue succeeds, return a clear 500 and avoid deleting the new source object.
- [ ] Add tests:
  - if `register_documents()` raises, existing repository document remains;
  - if new enqueue succeeds, old graph/vector/document cleanup still occurs and receipt has `replaced_document_id`.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/api/test_knowledgebases_router.py -q
```

## Task 4: Enforce Upload Size Limits While Streaming

**Issue:** KB and records upload endpoints read entire files into memory before size checks.

**Files:**
- Modify: `backend/api/routers/knowledgebases.py`
- Modify: `backend/api/routers/records.py`
- Test: `backend/tests/api/test_knowledgebases_router.py`
- Test: `backend/tests/api/test_records_router.py`

**Plan:**

- [ ] Add a private async helper in each router or shared API utility: read `UploadFile` in chunks, accumulate bytes, and raise `HTTPException(413)` as soon as total exceeds max.
- [ ] Use the helper for document uploads and record file uploads.
- [ ] Preserve existing behavior and error messages for files within the limit.
- [ ] Add tests with a file just over the configured limit and assert 413.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/api/test_knowledgebases_router.py backend/tests/api/test_records_router.py -q
```

## Task 5: Stream Remote Fetches with a Hard Byte Cap and Redirect Safety

**Issue:** `HttpxRemoteDocumentFetcher` follows redirects and then reads the full response body before enforcing `max_bytes` when there is no valid `content-length`. It also validates only the original URI scheme.

**Files:**
- Modify: `backend/ingestion/parsers/remote.py`
- Test: `backend/tests/ingestion/parsers/test_remote.py`

**Plan:**

- [ ] Use `client.stream("GET", source.uri)` or equivalent chunk iteration.
- [ ] Validate the final response URL scheme remains HTTPS after redirects.
- [ ] Accumulate chunks into `bytearray` and raise `RemoteFetchError` once `max_bytes` is exceeded.
- [ ] Preserve existing `RemoteDocumentPayload` fields.
- [ ] Add tests:
  - response without `content-length` exceeding `max_bytes` raises before returning payload;
  - redirect/final URL with non-HTTPS scheme raises `RemoteFetchError`;
  - normal fetch still succeeds.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/ingestion/parsers/test_remote.py -q
```

## Task 6: Treat Malformed Remote `content-length` as a Parse Failure

**Issue:** `int(content-length)` can raise `ValueError`, bypassing `RemoteFetchError` and therefore `documents.failed` publication.

**Files:**
- Modify: `backend/ingestion/parsers/remote.py`
- Test: `backend/tests/ingestion/parsers/test_remote.py`
- Test: `backend/tests/ingestion/test_service.py`

**Plan:**

- [ ] Parse `content-length` inside a helper that catches `ValueError`.
- [ ] Raise `RemoteFetchError("Remote response has invalid content-length.")` or similarly clear message.
- [ ] Add parser test for malformed header.
- [ ] Add/adjust service test proving malformed remote fetch through `process_documents_uploaded` publishes `DocumentsFailedEvent` instead of bubbling raw `ValueError`.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/ingestion/parsers/test_remote.py backend/tests/ingestion/test_service.py -q
```

## Task 7: Use Exact Source Object Keys for Existing Upload Detection

**Issue:** `_existing_document_storage_key()` returns the first key under a document prefix, which can select markers or future per-document artifacts.

**Files:**
- Modify: `backend/ingestion/service.py`
- Test: `backend/tests/ingestion/test_service.py`

**Plan:**

- [ ] Replace prefix-list based lookup with exact source key lookup: `knowledgebases/{kb}/documents/{doc}/source`.
- [ ] Return that key only if `object_store.exists(exact_source_key)` is true.
- [ ] Add a test where a non-source key exists under the document prefix and assert register writes/publishes the source object rather than treating the non-source key as the document source.

**Focused verification:**

```bash
uv run --project backend pytest backend/tests/ingestion/test_service.py -q
```

## Task 8: Add Frontend Pagination for KB Document Lists

**Issue:** Frontend `getKnowledgeBaseDocuments()` calls `/documents` without `limit`/`offset`, silently capping larger lists at the backend default.

**Files:**
- Modify: `chili_app/src/api/knowledgebases.ts`
- Modify: components/hooks that call `useKnowledgeBaseDocuments`
- Test: `chili_app/src/api/__tests__/knowledgebases.test.ts`

**Plan:**

- [ ] Extend `getKnowledgeBaseDocuments(knowledgeBaseId, {limit, offset})` to append query parameters.
- [ ] Extend `useKnowledgeBaseDocuments` to accept pagination options while keeping current default behavior.
- [ ] Add an API unit test asserting the request URL contains `limit` and `offset`.
- [ ] If a document list component exists with pagination controls, wire it to pass options; otherwise keep API support only.

**Focused verification:**

```bash
npm --prefix chili_app run test -- knowledgebases
```

## Final Verification

Run after all accepted changes:

```bash
uv run --project backend pyright
uv run --project backend pytest backend/tests/ingestion backend/tests/api/test_knowledgebases_router.py backend/tests/api/test_records_router.py backend/tests/api/test_dependencies.py backend/tests/agent/test_coordinator.py -q
git diff --check
```
