# Story E12-S02: LlmDocumentExtractor — LLM-backed entity and relationship extraction

## Story
As a platform developer, I want an `LlmDocumentExtractor` that uses the `LLMService` with structured prompts to extract entities and relationships with higher recall, coreference resolution, and cross-chunk relationship support — replacing the regex-only `PatternDocumentExtractor` as the default for production ingestion.

## Acceptance Criteria
1. `ingestion/extractor.py` adds a new `LlmDocumentExtractor` class that implements the same interface as `PatternDocumentExtractor` (accepts `entity_definitions`, `relationship_definitions`, `llm_service`, and optionally a `prompt_template_overrides` dict).
2. For each chunk the extractor calls `LLMService.generate()` with a structured prompt built from entity/relationship definitions; the LLM response is parsed as JSON into `CandidateEntity` / `CandidateRelationship` objects.
3. Entities extracted with the same canonical identifier value are deduplicated with fuzzy confidence averaging across chunks.
4. If the LLM response is malformed JSON the extractor falls back to `PatternDocumentExtractor` for that chunk and emits a `warning`.
5. `create_document_extractor()` is updated to accept a `mode: Literal["pattern", "llm"] = "pattern"` parameter and return the appropriate extractor.
6. Unit tests cover: single-chunk extraction, multi-chunk deduplication, malformed LLM response fallback, and empty LLM response.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | L    | E3-S04, E13-S01 |

## Target Files
- `backend/ingestion/extractor.py` — add `LlmDocumentExtractor`, update `create_document_extractor()`
- `backend/tests/ingestion/test_extractor.py` — add LlmDocumentExtractor tests with mock LLMService

## Reference Files to Read First
- `backend/ingestion/extractor.py` — current `PatternDocumentExtractor` and `create_document_extractor()`
- `backend/ingestion/models.py` — `CandidateEntity`, `CandidateRelationship`, `ExtractionResult`
- `backend/llm/service.py` — `LLMService.generate()` interface
- `backend/llm/models.py` — `GenerationRequest` and `GenerationResult`
- `backend/shared/types.py` — `EntityDefinition`, `RelationshipDefinition`
- `docs/architecture.md` §6 — ingestion pipeline and extraction design

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- LLM interaction is via the `LLMService` protocol — never call an SDK directly from the extractor
- Prompt templates must be domain-agnostic: built from `EntityDefinition.properties` at runtime
- Cross-chunk entity deduplication must use property value equality, not fuzzy string matching in the first pass
- The extractor must be pure Python with no subprocess calls

## What NOT To Do
- Do not remove `PatternDocumentExtractor` — it remains the fallback and default
- Do not hardcode entity type names or property names
- Do not add cross-module imports outside `shared/`, `llm/`, and `ingestion/`
- Do not block the ingestion pipeline on LLM timeouts — enforce a per-chunk timeout and fall back on expiry

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing (mocked LLM service)
- [ ] `pytest --cov=ingestion tests/ingestion/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
