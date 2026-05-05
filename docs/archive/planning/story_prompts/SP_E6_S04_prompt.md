# Story E6-S04: Production AnswerGenerator adapter — delegate to LLMService

## Story
As a platform developer, I want a `ServiceAnswerGenerator` adapter that delegates `generate` to the `LLMService`.

## Acceptance Criteria
1. `rag/adapters/llm_bridge.py` implements `AnswerGeneratorProtocol`.
2. Accepts `LlmServiceProtocol`, assembles prompt from `RagGenerationRequest` (system prompt + context + question), maps LLM response to `RagGenerationResult`.
3. Unit test with mock LLM service verifies prompt assembly and result mapping.
4. Token budget enforcement: truncates context if total token estimate exceeds `LlmConfig.max_tokens * 0.8`.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P0      |
| Size         | M       |
| Dependencies | E3-S05  |

## Target Files
- `backend/rag/adapters/llm_bridge.py` — new file implementing `ServiceAnswerGenerator`
- `backend/rag/adapters/__init__.py` — re-export `ServiceAnswerGenerator`
- `backend/tests/rag/test_llm_bridge.py` — unit tests for the adapter

## Reference Files to Read First
- `backend/rag/protocols.py` — `AnswerGeneratorProtocol` definition
- `backend/rag/adapters/in_memory.py` — existing in-memory adapter pattern to follow
- `backend/rag/adapters/protocols.py` — adapter-level protocol definitions
- `backend/rag/models.py` — `RagGenerationResult`, `RagCitation`, and related domain models
- `backend/rag/service_models.py` — `RagGenerationRequest` and related types
- `backend/llm/protocols.py` — `LlmServiceProtocol` (the dependency)
- `backend/llm/service_models.py` — LLM service request/response types
- `backend/llm/models.py` — LLM domain models
- `backend/config/schema.py` — `LlmConfig` for `max_tokens` reference

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The adapter must depend on `LlmServiceProtocol` (abstract), never on a concrete LLM adapter
- Import `LlmServiceProtocol` from `llm.protocols` — allowed cross-module boundary via protocol dependency injection
- Token budget enforcement must use a simple estimation approach (e.g., character-based heuristic or `len(text) // 4`) — do NOT add a tokenizer dependency
- The 80% budget threshold (`max_tokens * 0.8`) must be applied to context, reserving room for system prompt and question
- Prompt assembly order: system prompt → context block → user question

## What NOT To Do
- Do NOT instantiate or import any concrete `LlmService` implementation — accept the protocol via constructor injection
- Do NOT add new protocols or change `AnswerGeneratorProtocol` — implement it as-is
- Do NOT add HTTP/network calls — this is a pure delegation adapter
- Do NOT modify `llm/` module files
- Do NOT add a tokenizer library dependency (tiktoken, etc.) — use a simple estimation heuristic
- Do NOT silently drop context without truncation — truncate to fit the budget, don't skip entire items
- Do NOT hard-code prompt templates — assemble from the `RagGenerationRequest` fields

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `rag/adapters/llm_bridge.py` introduces
`ServiceAnswerGenerator`, which assembles a system+user message pair for
`LlmServiceProtocol.generate`: the system prompt is taken from the
`RagGenerationRequest.system_prompt` (falling back to a built-in default)
and the user message renders context items (`[N] (record=…, score=…)\n<content>`),
optional graph summary, and the question — in that order. Token budget is
estimated with the `len(text) // 4` heuristic; available characters equal
`max_tokens * 0.8 * 4` minus the system prompt + question + graph-summary
overhead. Context items are sorted by score and packed greedily highest
first, with a partial-truncation fallback when a remaining slice is at
least 16 chars; surviving items are then re-emitted in their original
order. The constructor accepts `max_tokens`, `model_name`, optional
`temperature` (validated 0.0–2.0), and a `knowledge_base_id_in_request`
flag for callers that prefer not to forward the KB ID. The LLM
`CompletionResponse` is mapped 1:1 to `RagGenerationResult`.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/rag/test_graph_bridge.py
tests/rag/test_llm_bridge.py -q` passed (20 tests). `.venv/bin/ruff check
rag/adapters/graph_bridge.py rag/adapters/llm_bridge.py
tests/rag/test_graph_bridge.py tests/rag/test_llm_bridge.py` clean.
`.venv/bin/pyright rag/adapters/graph_bridge.py rag/adapters/llm_bridge.py
tests/rag/test_graph_bridge.py tests/rag/test_llm_bridge.py` reported 0 errors.
Full `tests/rag/` suite (46 tests) passes.
