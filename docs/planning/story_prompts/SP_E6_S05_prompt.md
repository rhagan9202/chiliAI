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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
