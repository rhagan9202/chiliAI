# Story E6-S05: Domain-configurable RAG system prompt

## Story
As a platform operator, I want the RAG system prompt to be loaded from `RagConfig.system_prompt_template`, so that domain-specific prompts can be configured without code changes.

## Acceptance Criteria
1. `RagService.answer()` reads `system_prompt` from request, falls back to `RagConfig.system_prompt_template` from domain config when None.
2. Template supports `{domain_name}` and `{entity_types}` placeholders, resolved at call time from `DomainConfig`.
3. Unit test verifies placeholder resolution and fallback behavior.
4. Default YAML fixture includes sample system prompt template.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P1      |
| Size         | S       |
| Dependencies | E1-S06  |

## Target Files
- `backend/rag/service.py` — modify `RagService.answer()` to support system prompt template resolution
- `backend/config/schema.py` — ensure `RagConfig.system_prompt_template` field exists (verify, add if missing)
- `backend/config/defaults/` — add or update default YAML fixture with sample system prompt template
- `backend/tests/rag/test_service.py` — add tests for placeholder resolution and fallback behavior

## Reference Files to Read First
- `backend/rag/service.py` — current `RagService.answer()` implementation
- `backend/rag/service_models.py` — `RagQueryRequest` (check for `system_prompt` field)
- `backend/rag/protocols.py` — `RagServiceProtocol` definition
- `backend/config/schema.py` — `RagConfig`, `DomainConfig` definitions
- `backend/config/loader.py` — how config is loaded and accessed
- `backend/config/defaults/` — existing default configuration files
- `backend/tests/rag/test_service.py` — existing service tests to extend

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Template resolution must use Python `str.format_map()` or equivalent safe formatting — not `eval()` or `exec()`
- Placeholder resolution must be safe: unknown placeholders should not crash, use `string.Template` safe_substitute or equivalent
- The `DomainConfig` must be injected into `RagService` (or accessible via config), not hard-coded
- Fallback chain: request `system_prompt` → `RagConfig.system_prompt_template` → reasonable hardcoded default

## What NOT To Do
- Do NOT use `eval()`, `exec()`, or any unsafe template rendering
- Do NOT modify the `RagServiceProtocol` signature — changes go in the implementation
- Do NOT add Jinja2 or other template engine dependencies — use stdlib string formatting
- Do NOT hard-code domain-specific content in Python files — all domain text goes in config YAML
- Do NOT break existing `RagService.answer()` tests — extend, don't replace

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note (2026-04-26)

`RagService.answer()` and `RagService.stream_answer()` now resolve the
generation-request system prompt through `_resolve_system_prompt`:

1. If `RagQueryRequest.system_prompt` is set, use it verbatim.
2. Else if a `DomainConfig` is injected (new optional `domain_config=` ctor
   arg + plumbed through `create_rag_service`) and
   `DomainConfig.rag.system_prompt_template` is set, render it with
   `str.format_map` against a `_SafeFormatMap` so unknown `{...}` tokens are
   preserved instead of raising. Placeholders resolved: `{domain_name}`
   (from `DomainConfig.domain.display_name`) and `{entity_types}` (joined
   `EntityDefinition.display_label` — `display_label` is the actual schema
   field; the spec's `e.label` was a typo).
3. Else `system_prompt` stays `None` and the answer-generator bridge applies
   its own default.

`RagConfig.system_prompt_template: str | None` already existed in
`config/schema.py`; both default YAMLs now uncomment the `rag:` block and
ship a sample template:
`"You are an expert assistant for {domain_name}. Use the provided context to answer questions about {entity_types}."`

## Validation Note (2026-04-26)

```
.venv/bin/pytest tests/rag tests/api/test_chat_router.py tests/config -q   # 130 passed
.venv/bin/ruff check rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config  # clean
.venv/bin/pyright rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config     # 0 errors
.venv/bin/pytest tests/rag --cov=rag                                       # 95% line coverage
```
