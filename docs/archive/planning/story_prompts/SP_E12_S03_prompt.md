# Story E12-S03: Extraction confidence threshold filtering in DocumentResultValidator

## Story
As a platform developer, I want the `DocumentResultValidator` to filter out extraction candidates below a configurable confidence threshold so that low-quality extractions do not propagate to the graph.

## Acceptance Criteria
1. `ingestion/validator.py` adds a `confidence_threshold: float = 0.3` parameter to the validator (constructor-injectable and config-driven).
2. `CandidateEntity` and `CandidateRelationship` items with `confidence < confidence_threshold` are removed from the `ExtractionResult` before validation continues; the count of filtered items is captured in `ValidationReport.warnings`.
3. The threshold is surfaced in `config/schema.py` under `IngestionConfig` as `min_extraction_confidence: float = 0.3`.
4. The validator reads the threshold from the `IngestionConfig` when the validator is constructed via `create_validator(config: IngestionConfig)`.
5. Unit tests cover: all items above threshold (nothing filtered), items below threshold (filtered and warned), threshold at boundary (inclusive), and empty result after filtering.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/ingestion/validator.py` — add `confidence_threshold` parameter and filtering logic
- `backend/config/schema.py` — add `min_extraction_confidence` to `IngestionConfig`
- `backend/tests/ingestion/test_validator.py` — add threshold filtering tests

## Reference Files to Read First
- `backend/ingestion/validator.py` — current `DocumentResultValidator` and `ValidationReport`
- `backend/ingestion/models.py` — `ExtractionResult`, `CandidateEntity`, `CandidateRelationship`
- `backend/config/schema.py` — current `IngestionConfig`
- `backend/tests/ingestion/test_validator.py` — existing validator tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Filtering must occur before entity/relationship cross-reference checks to avoid false referential errors
- `confidence_threshold` must be in `[0.0, 1.0]`; validate with Pydantic `Field(ge=0.0, le=1.0)`
- The `ValidationReport` must record the number of items filtered, not just a boolean

## What NOT To Do
- Do not hard-code `0.3` — the default lives in `IngestionConfig`, not in the validator class body
- Do not filter items from the original `ExtractionResult`; produce a new `ExtractionResult` with filtered lists
- Do not change the `ValidationReport` model to remove existing fields

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=ingestion tests/ingestion/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
