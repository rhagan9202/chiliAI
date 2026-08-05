# SAFE-CMS-016 RAG Contract Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RAG filters, streaming, citations, evidence scopes, KB context, and workflow/tool usage consistent across chat launch, non-streaming chat, streaming chat, and workflow capability calls.

**Architecture:** Keep the shallow scalar filter contract already used by `ChatMessageCreateRequest`, and add parity at the boundaries that currently drop scope data. Backend changes stay in the chat router, RAG service models, capability registry, and future workflow adapter layer; frontend changes centralize scope construction in `ragContext.ts` so launch URLs, chat payloads, and active-scope display share one representation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, TypeScript, React, Vitest, generated OpenAPI contracts when backend response/request models change.

---

## File Structure

- Modify `backend/api/routers/rag.py`: pass `ChatMessageCreateRequest.filters` and `include_graph_context` into streaming `RagQueryRequest`; include metadata in the final SSE event only after tests require it.
- Modify `backend/tests/api/test_chat_router.py`: streaming parity tests that capture the `RagQueryRequest`.
- Modify `backend/capabilities/registry.py`: tighten the `rag.query` input/output schemas once workflow invocation is added.
- Modify `backend/capabilities/service.py`: reuse existing `authorize()` envelopes for the RAG workflow adapter.
- Create `backend/workflow_definitions/rag_adapter.py`: small adapter that authorizes `rag.query`, calls `RagServiceProtocol.answer`, and returns a capability execution envelope.
- Test `backend/tests/workflow_definitions/test_rag_adapter.py`: adapter authorization, audit requirement, citation refs, and failure envelope coverage.
- Modify `chili_app/src/lib/ragContext.ts`: add typed RAG scope helpers for URL parse/build and message filters.
- Modify `chili_app/src/lib/__tests__/ragContext.test.ts`: route reload and filter parity tests.
- Modify `chili_app/src/pages/RagChatPage.tsx`: show active scope and use the shared scope helper.
- Modify `chili_app/src/pages/__tests__/RagChatPage.test.tsx`: active scope and reload behavior tests.

## Implementation Status

- Completed in this pass: Tasks 1, 2, and 3.
- Remaining work: Tasks 4 and 5.

---

### Task 1: Streaming RAG Filter Parity

**Files:**
- Modify: `backend/api/routers/rag.py`
- Test: `backend/tests/api/test_chat_router.py`

- [x] **Step 1: Write the failing streaming filter parity test**

Add a capture service and test to `backend/tests/api/test_chat_router.py`:

```python
class _CaptureRagService:
    def __init__(self) -> None:
        self.stream_requests: list[RagQueryRequest] = []

    def answer(self, request: RagQueryRequest) -> RagQueryResponse:
        raise NotImplementedError

    def answer_question(
        self,
        *,
        knowledge_base_ids: list[str],
        question: str,
    ) -> RagAnswer:
        raise NotImplementedError

    def stream_answer(self, request: RagQueryRequest) -> Iterator[RagStreamChunk]:
        self.stream_requests.append(request)
        yield RagStreamChunk(chunk_text="", is_final=True, citations=[])


def test_stream_message_forwards_filters_and_graph_context_flag() -> None:
    app = create_app()
    service = _CaptureRagService()
    state = ApiState()
    object.__setattr__(
        state,
        "_rag_service",
        cast(RagServiceProtocol, service),
    )
    app.dependency_overrides[get_api_state] = lambda: state
    client = TestClient(app)
    conversation_id = _new_conversation_id(client)

    with client.stream(
        "POST",
        f"/chat/conversations/{conversation_id}/messages",
        params={"knowledge_base_id": "kb-1", "stream": "true"},
        json={
            "content": "Explain this alert",
            "include_graph_context": False,
            "filters": {
                "source_type": "alert",
                "alert_id": "alert-1",
                "entity_id": "provider-204",
            },
        },
    ) as response:
        assert response.status_code == 200
        _ = b"".join(response.iter_bytes())

    assert len(service.stream_requests) == 1
    request = service.stream_requests[0]
    assert request.filters == {
        "source_type": "alert",
        "alert_id": "alert-1",
        "entity_id": "provider-204",
    }
    assert request.include_graph_context is False
```

- [x] **Step 2: Run the focused red test**

Run: `uv run --project backend pytest backend/tests/api/test_chat_router.py::test_stream_message_forwards_filters_and_graph_context_flag -q`

Expected: FAIL because `request.filters` is `{}` and `include_graph_context` remains `True`.

- [x] **Step 3: Implement minimal streaming parity**

Change `_stream_sse()` in `backend/api/routers/rag.py` to accept `filters` and `include_graph_context`, pass `payload.filters` and `payload.include_graph_context` from `add_message()`, and build:

```python
query_request = RagQueryRequest(
    knowledge_base_ids=knowledge_base_ids,
    question=question,
    include_graph_context=include_graph_context,
    filters=filters,
)
```

- [x] **Step 4: Run focused green tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py::test_stream_message_forwards_filters_and_graph_context_flag backend/tests/api/test_chat_router.py::test_stream_message_final_event_citations_match_contract -q
uv run --project backend ruff check backend/api/routers/rag.py backend/tests/api/test_chat_router.py
```

Expected: PASS and Ruff clean.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/api/routers/rag.py backend/tests/api/test_chat_router.py docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md
git commit -m "fix: preserve rag streaming filters"
```

### Task 2: Typed Frontend RAG Scope Helper

**Files:**
- Modify: `chili_app/src/lib/ragContext.ts`
- Test: `chili_app/src/lib/__tests__/ragContext.test.ts`

- [x] **Step 1: Write failing helper tests**

Add tests proving one helper can create both route params and chat filters:

```ts
it('creates a typed rag scope from launch context for route reloads and message filters', () => {
  const scope = buildRagScope({
    knowledgeBaseId: 'kb-1',
    source: 'alert',
    alertId: 'alert-1',
    entityId: 'provider-204',
    evidencePackId: 'evidence-1',
  })

  expect(scope.filters).toEqual({
    source_type: 'alert',
    alert_id: 'alert-1',
    entity_id: 'provider-204',
    evidence_pack_id: 'evidence-1',
  })
  expect(scope.label).toBe('Alert alert-1')
})
```

- [x] **Step 2: Run focused red test**

Run: `npm run test:run -- src/lib/__tests__/ragContext.test.ts -t "typed rag scope"`

Expected: FAIL because `buildRagScope` does not exist.

- [x] **Step 3: Implement `RagScope` and `buildRagScope()`**

Add a `RagScope` type with `knowledgeBaseId`, `source`, `filters`, and `label`; make `buildRagMessageFilters()` delegate to `buildRagScope(context).filters`.

- [x] **Step 4: Run focused green tests**

Run: `npm run test:run -- src/lib/__tests__/ragContext.test.ts`

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add chili_app/src/lib/ragContext.ts chili_app/src/lib/__tests__/ragContext.test.ts docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md
git commit -m "feat: add typed rag scope helper"
```

### Task 3: Active Scope Display In RAG Chat

**Files:**
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Test: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`

- [x] **Step 1: Write failing active-scope test**

Add a test that loads `/rag-chat?kb=kb-1&source=alert&alert=alert-1&entity=provider-204` and expects visible scope text `Alert alert-1`.

- [x] **Step 2: Run focused red test**

Run: `npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx -t "active scope"`

Expected: FAIL because the page does not expose the active scope.

- [x] **Step 3: Render active scope from `buildRagScope()`**

Use the parsed launch context to build scope once and render a compact scope chip near the chat toolbar/input.

- [x] **Step 4: Run focused green tests**

Run: `npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx`

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add chili_app/src/pages/RagChatPage.tsx chili_app/src/pages/__tests__/RagChatPage.test.tsx docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md
git commit -m "feat: show rag active scope"
```

### Task 4: Workflow RAG Capability Adapter

**Files:**
- Create: `backend/workflow_definitions/rag_adapter.py`
- Modify: `backend/capabilities/registry.py`
- Test: `backend/tests/workflow_definitions/test_rag_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Create tests for authorized `rag.query` execution returning `CapabilityExecutionEnvelope` with `citation_refs`, and denied viewer execution returning `capability_role_denied`.

- [ ] **Step 2: Run focused red tests**

Run: `uv run --project backend pytest backend/tests/workflow_definitions/test_rag_adapter.py -q`

Expected: FAIL because the adapter module does not exist.

- [ ] **Step 3: Implement the adapter**

Add a small `execute_rag_query_capability()` function that calls `CapabilityRegistryService.authorize("rag.query", actor_roles, domain_name=..., environment_tag=...)`, short-circuits denied envelopes, then invokes `RagServiceProtocol.answer()`.

- [ ] **Step 4: Run focused green tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_rag_adapter.py backend/tests/capabilities/test_registry.py -q
uv run --project backend ruff check backend/workflow_definitions/rag_adapter.py backend/tests/workflow_definitions/test_rag_adapter.py backend/capabilities
```

Expected: PASS and Ruff clean.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/workflow_definitions/rag_adapter.py backend/capabilities/registry.py backend/tests/workflow_definitions/test_rag_adapter.py docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md
git commit -m "feat: add workflow rag capability adapter"
```

### Task 5: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md`

- [ ] **Step 1: Run backend gates**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py backend/tests/workflow_definitions/test_rag_adapter.py backend/tests/capabilities/test_registry.py -q
uv run --project backend pytest -m "not integration" backend/tests -q
uv run --project backend ruff check backend
uv run --project backend pyright
```

- [ ] **Step 2: Run frontend gates**

Run:

```bash
npm run test:run -- src/lib/__tests__/ragContext.test.ts src/pages/__tests__/RagChatPage.test.tsx
npm run test:run
npm run build
```

- [ ] **Step 3: Run migration/schema and whitespace gates**

Run:

```bash
scripts/ci_migration_check.sh
git diff --check
```

- [ ] **Step 4: Commit final plan status**

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-016-rag-contract-gaps.md
git commit -m "docs: update safe cms 016 plan status"
```
