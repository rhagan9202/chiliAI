# Story E13-S01: LLM adapter protocol extension — streaming, batch, and token counting

## Story
As a platform developer, I want the `LLMAdapterProtocol` to expose streaming generation, per-request token counting, and tool/function-calling support so that production LLM adapters can support these capabilities without ad-hoc extension.

## Acceptance Criteria
1. `llm/adapters/protocols.py` adds to `LLMAdapterProtocol`:
   - `stream_generate(request: GenerationRequest) -> Iterator[str]` — yields token strings
   - `count_tokens(request: GenerationRequest) -> int` — returns estimated token count
2. `llm/models.py` extends `GenerationRequest` with an optional `tools: list[ToolDefinition] | None = None` field; `ToolDefinition` is a new Pydantic model (`name: str`, `description: str`, `parameters: dict[str, object]`).
3. `InMemoryLLMAdapter` in `llm/adapters/in_memory.py` provides stub implementations: `stream_generate` yields the full response as a single token; `count_tokens` returns `len(request.prompt.split())`.
4. Unit tests cover: `stream_generate` yields tokens, `count_tokens` returns non-negative int.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/llm/adapters/protocols.py` — add `stream_generate`, `count_tokens` to protocol
- `backend/llm/models.py` — add `ToolDefinition`, extend `GenerationRequest.tools`
- `backend/llm/adapters/in_memory.py` — implement stub methods
- `backend/tests/llm/test_service.py` — add tests for new methods on the in-memory adapter

## Reference Files to Read First
- `backend/llm/adapters/protocols.py` — current `LLMAdapterProtocol`
- `backend/llm/models.py` — `GenerationRequest`, `GenerationResult`
- `backend/llm/adapters/in_memory.py` — current in-memory echo stub
- `backend/tests/llm/` — existing LLM test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `stream_generate` must return a synchronous `Iterator[str]` not an `AsyncIterator` in this story; async streaming is E6-S06 at the RAG layer
- `ToolDefinition.parameters` uses `dict[str, object]` (JSON Schema blob) — not typed further in this story
- Extending the protocol must not break existing adapter implementations (add methods with default `NotImplementedError` raise to `InMemoryLLMAdapter` is acceptable)

## What NOT To Do
- Do not implement OpenAI or Anthropic streaming here — production adapters are E3-S04 and E3-S05
- Do not add retry logic here — that is E13-S02
- Do not add async variants of `generate` in this story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=llm tests/llm/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
