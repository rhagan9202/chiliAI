# Frontend-Backend Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated OpenAPI types the authoritative frontend API contract, preserve runtime domain configurability, and add guardrails that block hand-written DTO drift.

**Architecture:** The backend remains the HTTP contract owner through explicit FastAPI/Pydantic request and response models. A backend export script writes a deterministic OpenAPI snapshot, the frontend generates `src/lib/api/schema.ts` from that snapshot, and `src/api/contracts.ts` becomes an alias layer over generated schemas. Runtime domain values remain data-driven through `/config/domain`; static types describe structure only.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, uv, React 19, TypeScript 5.9, Vite 8, TanStack Query, Vitest, openapi-typescript, GitHub Actions.

---

## File Map

- Create `tools/export_openapi.py`: CLI that exports backend OpenAPI without a running server.
- Create `tools/tests/test_export_openapi.py`: tests deterministic export behavior and required schemas.
- Modify `backend/api/contracts.py`: add missing frontend-facing config and stream DTOs.
- Modify `backend/api/routers/config.py`: add concrete response models for config endpoints.
- Modify `backend/api/routers/rag.py`: document JSON and SSE response shapes, preserve rich citations, and enforce RAG question length.
- Modify `backend/api/routers/investigation.py`: enforce configured search query length.
- Modify `backend/tests/api/test_app.py`: add OpenAPI completeness assertions.
- Modify `backend/tests/api/test_chat_router.py`: verify RAG length limit and stream citation shape.
- Modify `backend/tests/api/test_investigation_router.py`: verify search length limit.
- Modify `chili_app/package.json`: change `codegen:api` to read the checked-in OpenAPI snapshot and run a generated header step.
- Create `chili_app/scripts/ensure-generated-api-header.mjs`: deterministic generated-file header helper.
- Generate `chili_app/openapi.json`: committed OpenAPI snapshot.
- Generate `chili_app/src/lib/api/schema.ts`: committed generated TypeScript schema.
- Modify `chili_app/src/api/contracts.ts`: replace hand-written wire DTOs with generated schema aliases.
- Modify frontend API modules and components as required by generated types.
- Modify `chili_app/src/lib/ingestion/validateIngestion.ts`: align frontend record validation with backend constraints.
- Modify `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`: add validator parity cases.
- Create `scripts/contract_guardrails.py`: repository guardrail checks for generated-contract discipline.
- Create `tests/scripts/test_contract_guardrails.py`: tests for the guardrail script.
- Modify `.github/workflows/ci.yml`: add OpenAPI/codegen drift and guardrail checks.
- Modify `CLAUDE.md`, `.github/copilot-instructions.md`, `README.md`, `backend/README.md`, and `chili_app/README.md`: document the mandatory contract workflow.
- Modify `docs/architecture.md`: record the OpenAPI source-of-truth decision.

## Implementation Tasks

### Task 1: Backend OpenAPI Export CLI

**Files:**
- Create: `tools/export_openapi.py`
- Create: `tools/tests/test_export_openapi.py`

- [ ] **Step 1: Write failing tests for the export CLI**

Create `tools/tests/test_export_openapi.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "backend" / "config" / "defaults" / "medicare_fraud.yaml"


def test_export_openapi_writes_deterministic_schema(tmp_path: Path) -> None:
    first = tmp_path / "openapi-a.json"
    second = tmp_path / "openapi-b.json"

    command = [
        sys.executable,
        "-m",
        "tools.export_openapi",
        "--config",
        str(DEFAULT_CONFIG),
        "--output",
        str(first),
    ]
    subprocess.run(command, cwd=ROOT, check=True)

    command[-1] = str(second)
    subprocess.run(command, cwd=ROOT, check=True)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_export_openapi_contains_frontend_contract_schemas(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.export_openapi",
            "--config",
            str(DEFAULT_CONFIG),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )

    schema = json.loads(output.read_text(encoding="utf-8"))
    components = schema["components"]["schemas"]
    paths = schema["paths"]

    assert "ChatConversationResponse" in components
    assert "DomainConfig" in components
    assert "Relationship" in components
    assert "/chat/conversations/{conversation_id}/messages" in paths
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --project backend pytest tools/tests/test_export_openapi.py -q
```

Expected: FAIL because `tools.export_openapi` does not exist.

- [ ] **Step 3: Implement the export CLI**

Create `tools/export_openapi.py`:

```python
"""Export the backend OpenAPI schema without starting an HTTP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_CONFIG = BACKEND / "config" / "defaults" / "medicare_fraud.yaml"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Domain config path used while creating the FastAPI app.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="OpenAPI JSON output path.",
    )
    return parser.parse_args(argv)


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = args.config.resolve()
    output_path = args.output.resolve()

    if not config_path.is_file():
        _fail(f"Config file not found: {config_path}")

    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("CHILI_ENV", "local")
    os.environ["CHILI_CONFIG_PATH"] = str(config_path)

    from api.app import create_app

    schema = create_app().openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run export tests and verify they pass**

Run:

```bash
uv run --project backend pytest tools/tests/test_export_openapi.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add tools/export_openapi.py tools/tests/test_export_openapi.py
git commit -m "tooling: export backend openapi schema"
```

### Task 2: Backend OpenAPI Contract Completeness

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/config.py`
- Modify: `backend/api/routers/rag.py`
- Modify: `backend/tests/api/test_app.py`

- [ ] **Step 1: Add failing OpenAPI completeness tests**

Append these tests to `backend/tests/api/test_app.py` inside `TestOpenApiSchema`:

```python
    def test_frontend_json_routes_have_response_schemas(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        paths = cast(dict[str, dict[str, dict[str, object]]], schema["paths"])

        required_operations: tuple[tuple[str, str], ...] = (
            ("/config/domain", "get"),
            ("/config/features", "get"),
            ("/chat/conversations/{conversation_id}/messages", "post"),
            ("/investigation/search", "get"),
            ("/investigation/entities/{entity_id}/neighborhood", "get"),
        )

        missing: list[str] = []
        for path, method in required_operations:
            operation = paths[path][method]
            responses = cast(dict[str, object], operation["responses"])
            success = cast(dict[str, object], responses["200"])
            content = cast(dict[str, object], success.get("content", {}))
            json_content = cast(dict[str, object], content.get("application/json", {}))
            if "schema" not in json_content:
                missing.append(f"{method.upper()} {path}")

        assert missing == []

    def test_domain_config_schema_includes_runtime_sections(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        components = cast(dict[str, dict[str, object]], schema["components"])
        schemas = cast(dict[str, dict[str, object]], components["schemas"])
        domain_config = schemas["DomainConfig"]
        properties = cast(dict[str, object], domain_config["properties"])

        assert {"capabilities", "validation", "records", "ui", "alerts"}.issubset(
            properties
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
CHILI_ENV=local CHILI_CONFIG_PATH=backend/config/defaults/medicare_fraud.yaml uv run --project backend pytest backend/tests/api/test_app.py::TestOpenApiSchema -q
```

Expected: FAIL because config routes and the chat message route do not expose complete JSON schemas.

- [ ] **Step 3: Add frontend-facing config and stream contracts**

In `backend/api/contracts.py`, add these models near the other frontend-facing contracts:

```python
from config.schema import CapabilitiesConfig, DomainConfig, UiRoleConfig


class DomainFeaturesResponse(BaseModel):
    """Feature flags and role/navigation metadata derived from DomainConfig."""

    capabilities: CapabilitiesConfig
    default_entity_type: str | None = None
    default_role: str | None = None
    enabled_pages: list[str] = Field(default_factory=lambda: cast(list[str], []))
    roles: dict[str, UiRoleConfig] = Field(default_factory=dict)


class DomainConfigSchemaResponse(BaseModel):
    """JSON Schema payload for the active domain config model."""

    schema_payload: dict[str, object] = Field(default_factory=dict, alias="schema")


class ChatStreamCitationResponse(BaseModel):
    """Citation payload emitted in the final RAG SSE event."""

    record_id: str
    content_id: str
    score: float
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None
    entity_id: str | None = None


class ChatStreamFinalEventResponse(BaseModel):
    """Final RAG SSE event payload."""

    token: str
    done: Literal[True]
    sources: list[str] = Field(default_factory=lambda: cast(list[str], []))
    citations: list[ChatStreamCitationResponse] = Field(
        default_factory=lambda: cast(list[ChatStreamCitationResponse], [])
    )
```

Also add these names to `__all__`.

- [ ] **Step 4: Add response models to config routes**

Modify `backend/api/routers/config.py`:

```python
from config.schema import DomainConfig
from api.contracts import DomainFeaturesResponse


@router.get(
    "/domain",
    response_model=DomainConfig,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_domain(
    config: DomainConfig = Depends(get_domain_config),
) -> DomainConfig:
    """Return the active domain configuration."""
    return config


@router.get(
    "/features",
    response_model=DomainFeaturesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_features(
    features: dict[str, object] = Depends(get_domain_config_features_payload),
) -> dict[str, object]:
    """Return feature flags and enabled page metadata for the frontend."""
    return features
```

Leave `/config/domain/schema` returning `dict[str, object]`; it is a JSON Schema document whose inner keys are dynamic.

- [ ] **Step 5: Add JSON and SSE response documentation to the chat message route**

Modify the `@router.post("/conversations/{conversation_id}/messages", ...)` decorator in `backend/api/routers/rag.py`:

```python
@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatConversationResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": ChatConversationResponse.model_json_schema()
                },
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "description": "Server-sent events carrying token chunks and a final citation event.",
                },
            }
        }
    },
    dependencies=[Depends(require_role("analyst"))],
)
```

Import `ChatConversationResponse` is already present. Keep the `StreamingResponse` branch; FastAPI bypasses response-model serialization for `Response` subclasses.

- [ ] **Step 6: Run OpenAPI completeness tests**

Run:

```bash
CHILI_ENV=local CHILI_CONFIG_PATH=backend/config/defaults/medicare_fraud.yaml uv run --project backend pytest backend/tests/api/test_app.py::TestOpenApiSchema -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/api/contracts.py backend/api/routers/config.py backend/api/routers/rag.py backend/tests/api/test_app.py
git commit -m "test: require frontend openapi response schemas"
```

### Task 3: Route Validator Parity For Query Inputs

**Files:**
- Modify: `backend/api/routers/rag.py`
- Modify: `backend/api/routers/investigation.py`
- Modify: `backend/tests/api/test_chat_router.py`
- Modify: `backend/tests/api/test_investigation_router.py`

- [ ] **Step 1: Add failing route-level validation tests**

Add to `backend/tests/api/test_chat_router.py`:

```python
def test_send_message_rejects_configured_question_length() -> None:
    client = TestClient(create_app())
    conversation_id = _new_conversation_id(client)

    response = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"content": "x" * 5001},
    )

    assert response.status_code == 422
    assert "exceeds maximum" in response.json()["detail"]
```

Add to `backend/tests/api/test_investigation_router.py`:

```python
def test_search_rejects_configured_query_length(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "x" * 10001},
    )

    assert response.status_code == 422
    assert "exceeds maximum" in response.json()["detail"]
```

If `test_investigation_router.py` uses a named client fixture with a seeded KB, place the test beside the existing search validation tests and use that fixture name.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py::test_send_message_rejects_configured_question_length backend/tests/api/test_investigation_router.py::test_search_rejects_configured_query_length -q
```

Expected: FAIL because the routes do not call `validate_query_length()`.

- [ ] **Step 3: Wire query length validation into chat messages**

In `backend/api/routers/rag.py`, import the validation helper:

```python
from shared.validation import validate_query_length
```

Inside `add_message()`, before the non-streaming branch, add:

```python
    validation = domain_config.validation or ValidationConfig()
    try:
        cleaned_content = validate_query_length(
            payload.content,
            validation.max_rag_question_length,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    payload = payload.model_copy(update={"content": cleaned_content})
```

Also import `ValidationConfig` from `config.schema`.

- [ ] **Step 4: Wire query length validation into investigation search**

In `backend/api/routers/investigation.py`, import:

```python
from shared.validation import validate_query_length
```

Inside `search_entities()`, before `resolve_kb_scope(...)`, add:

```python
    validation = domain_config.validation or ValidationConfig()
    try:
        cleaned_query = validate_query_length(q, validation.max_query_length)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
```

Pass `cleaned_query` to `graph_service.search_entities(...)`. Also import `ValidationConfig` from `config.schema`.

- [ ] **Step 5: Run focused validation tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py::test_send_message_rejects_configured_question_length backend/tests/api/test_investigation_router.py::test_search_rejects_configured_query_length -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/api/routers/rag.py backend/api/routers/investigation.py backend/tests/api/test_chat_router.py backend/tests/api/test_investigation_router.py
git commit -m "fix: enforce configured query length limits"
```

### Task 4: RAG Streaming Citation Contract

**Files:**
- Modify: `backend/api/routers/rag.py`
- Modify: `backend/tests/api/test_chat_router.py`

- [ ] **Step 1: Add failing stream citation test**

Add to `backend/tests/api/test_chat_router.py`:

```python
def test_stream_message_final_event_citations_match_contract() -> None:
    client = TestClient(create_app())
    conversation_id = _new_conversation_id(client)

    with client.stream(
        "POST",
        f"/chat/conversations/{conversation_id}/messages",
        params={"stream": "true"},
        json={"content": "Tell me more"},
    ) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes()).decode("utf-8")

    events = _parse_sse_events(body)
    final_event = events[-1]
    assert final_event["done"] is True
    for citation in final_event["citations"]:
        assert {
            "record_id",
            "content_id",
            "score",
            "snippet",
            "document_id",
            "chunk_index",
            "highlight",
            "entity_id",
        }.issubset(citation)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py::test_stream_message_final_event_citations_match_contract -q
```

Expected: FAIL because SSE citations omit `entity_id`.

- [ ] **Step 3: Add `entity_id` to stream citation payload**

Modify `_chunk_to_payload()` in `backend/api/routers/rag.py`:

```python
        payload["citations"] = [
            {
                "record_id": citation.record_id,
                "content_id": citation.content_id,
                "score": citation.score,
                "snippet": citation.snippet,
                "document_id": citation.document_id,
                "chunk_index": citation.chunk_index,
                "highlight": citation.highlight,
                "entity_id": None,
            }
            for citation in chunk.citations
        ]
```

Use `None` until `rag.service_models.RagCitation` grows a real `entity_id` field. This makes the stream shape agree with the nullable frontend/backend API citation contract.

- [ ] **Step 4: Run focused stream tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_chat_router.py::test_stream_message_returns_sse_with_done_sentinel backend/tests/api/test_chat_router.py::test_stream_message_final_event_citations_match_contract -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/api/routers/rag.py backend/tests/api/test_chat_router.py
git commit -m "fix: align rag stream citation shape"
```

### Task 5: Offline Frontend Codegen Workflow

**Files:**
- Modify: `chili_app/package.json`
- Create: `chili_app/scripts/ensure-generated-api-header.mjs`
- Generate: `chili_app/openapi.json`
- Generate: `chili_app/src/lib/api/schema.ts`

- [ ] **Step 1: Add generated header helper**

Create `chili_app/scripts/ensure-generated-api-header.mjs`:

```javascript
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const target = resolve(process.cwd(), 'src/lib/api/schema.ts')
const header = `// Generated from backend OpenAPI. Do not edit by hand.
// Run: npm run codegen:api

`

const current = readFileSync(target, 'utf8')
const withoutExistingHeader = current.replace(
  /^\/\/ Generated from backend OpenAPI\. Do not edit by hand\.\n\/\/ Run: npm run codegen:api\n\n/,
  '',
)
writeFileSync(target, `${header}${withoutExistingHeader}`, 'utf8')
```

- [ ] **Step 2: Update frontend codegen script**

Modify `chili_app/package.json`:

```json
"codegen:api": "openapi-typescript ./openapi.json --output src/lib/api/schema.ts && node scripts/ensure-generated-api-header.mjs"
```

- [ ] **Step 3: Export OpenAPI snapshot**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
```

Expected: `chili_app/openapi.json` is created with deterministic JSON.

- [ ] **Step 4: Generate frontend schema**

Run:

```bash
cd chili_app
npm run codegen:api
```

Expected: `src/lib/api/schema.ts` is created and starts with the generated-file header.

- [ ] **Step 5: Verify generated artifacts are stable**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
cd ..
git diff -- chili_app/openapi.json chili_app/src/lib/api/schema.ts
```

Expected: the diff only contains the first generated snapshot and generated TypeScript schema.

- [ ] **Step 6: Commit Task 5**

```bash
git add chili_app/package.json chili_app/scripts/ensure-generated-api-header.mjs chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "build: generate frontend api schema from openapi"
```

### Task 6: Replace Hand-Written Frontend Wire DTOs With Generated Aliases

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Modify: frontend files that fail typecheck after alias replacement

- [ ] **Step 1: Replace `contracts.ts` with generated aliases**

Rewrite `chili_app/src/api/contracts.ts` with this structure, adjusting names only if `schema.ts` generated different component keys:

```typescript
import type { components } from '../lib/api/schema'

type Schemas = components['schemas']

export type ApiEnvelope = Schemas['ApiEnvelope']
export type PageInfo = Schemas['PageInfo']

export type AlertSeverity = Schemas['AlertListItem']['severity']
export type AlertStatus = Schemas['AlertListItem']['status']
export type AlertListItem = Schemas['AlertListItem']
export type AlertListResponse = Schemas['AlertListResponse']
export type AlertDetailResponse = Schemas['AlertDetailResponse']

export type PolicyCitation = Schemas['PolicyCitation']
export type PolicyGapStatus = Schemas['PolicyGapSummaryResponse']['status']
export type PolicyTrendPointResponse = Schemas['PolicyTrendPointResponse']
export type PolicyGapSummaryResponse = Schemas['PolicyGapSummaryResponse']
export type PolicyGapListResponse = Schemas['PolicyGapListResponse']
export type PolicyGapDetailResponse = Schemas['PolicyGapDetailResponse']
export type PolicyGapCaseListResponse = Schemas['PolicyGapCaseListResponse']
export type PolicyBriefCreateRequest = Schemas['PolicyBriefCreateRequest']
export type PolicyBriefResponse = Schemas['PolicyBriefResponse']

export type RealtimeSnapshotResponse = Schemas['RealtimeSnapshotResponse']

export type GraphNodeResponse = Schemas['GraphNodeResponse']
export type GraphEdgeResponse = Schemas['GraphEdgeResponse']
export type GraphEntityDetailResponse = Schemas['GraphEntityDetailResponse']

export type RuntimeEntity = Schemas['Entity']
export type RuntimeRelationship = Schemas['Relationship']
export type InvestigationEntityDetailResponse = Schemas['EntityDetailResponse']
export type InvestigationNeighborhoodResponse = Schemas['NeighborhoodResponse']
export type InvestigationEntitySearchResponse = Schemas['EntitySearchResponse']

export type EvidenceItemResponse = Schemas['EvidenceItemResponse']
export type EvidencePackResponse = Schemas['EvidencePackResponse']

export type CaseStatus = Schemas['CaseSummaryResponse']['status']
export type CasePriority = Schemas['CaseSummaryResponse']['priority']
export type FeedbackLabel = Schemas['AnalystFeedbackResponse']['label']
export type EvidenceAdequacy = Schemas['AnalystFeedbackResponse']['evidence_adequacy']
export type CaseSummaryResponse = Schemas['CaseSummaryResponse']
export type CaseListResponse = Schemas['CaseListResponse']
export type AnalystFeedbackResponse = Schemas['AnalystFeedbackResponse']
export type CaseDetailResponse = Schemas['CaseDetailResponse']
export type CaseCreateRequest = Schemas['CaseCreateRequest']
export type CaseUpdateRequest = Schemas['CaseUpdateRequest']
export type CaseFeedbackCreateRequest = Schemas['CaseFeedbackCreateRequest']

export type ChatCitationResponse = Schemas['ChatCitationResponse']
export type ChatMessageResponse = Schemas['ChatMessageResponse']
export type ChatConversationResponse = Schemas['ChatConversationResponse']
export type ChatConversationCreateRequest = Schemas['ChatConversationCreateRequest']
export type ChatMessageCreateRequest = Schemas['ChatMessageCreateRequest']

export type KnowledgeBaseStatus = Schemas['KnowledgeBase']['status']
export type KnowledgeBaseSummaryResponse = Schemas['KnowledgeBase']
export type KnowledgeBaseListResponse = Schemas['KbListResponse']
export type KnowledgeBaseDocumentResponse = Schemas['DocumentSummary']
export type KnowledgeBaseDocumentListResponse = Schemas['DocumentListResponse']
export type KnowledgeBaseCreateRequest = Schemas['CreateKbRequest']
export type DocumentReceiptResponse = Schemas['DocumentReceipt']
export type DocumentRegistrationResponse = Schemas['DocumentRegistrationResponse']
export type IngestionStatus = Schemas['DocumentSummary']['status']

export type DomainConfig = Schemas['DomainConfig']
export type DomainFeatures = Schemas['DomainFeaturesResponse']
export type DomainCapabilities = Schemas['CapabilitiesConfig']
export type DomainPropertyDefinition = Schemas['PropertyDefinition']
export type DomainEntityDefinition = Schemas['EntityDefinition']
export type DomainRelationshipDefinition = Schemas['RelationshipDefinition']
export type DomainRoleConfig = Schemas['UiRoleConfig']
export type DomainUiConfig = Schemas['UiConfig']
export type DomainNavigationPage = Schemas['UiNavigationPageConfig']
export type ValidationConfig = Schemas['ValidationConfig']
export type RecordFeedConfig = Schemas['RecordFeedConfig']
export type RecordEntityMapping = Schemas['RecordEntityMapping']
export type RecordRelationshipMapping = Schemas['RecordRelationshipMapping']
export type RecordObservationMapping = Schemas['RecordObservationMapping']
export type RecordsConfig = Schemas['RecordsConfig']
export type DomainConfigSchema = Record<string, unknown>

export type RecordPushRequest = Schemas['RecordPushRequest']
export type RecordIngestReceipt = Schemas['RecordIngestReceipt']

export type WorkflowRunResponse = Schemas['WorkflowRunResponse']
export type WorkflowRunListResponse = Schemas['WorkflowRunListResponse']

export type RiskFactorResponse = Schemas['RiskFactorResponse']
export type RiskScoreResponse = Schemas['RiskScoreResponse']
export type TimeseriesPointResponse = Schemas['EntityTimeseriesPointResponse']
export type TimeseriesResponse = Schemas['EntityTimeseriesResponse']
export type AnalyticsOverviewResponse = Schemas['AnalyticsOverviewResponse']
```

- [ ] **Step 2: Run frontend typecheck and capture failures**

Run:

```bash
cd chili_app
npx tsc --noEmit
```

Expected: FAIL on frontend code that assumed narrower hand-written shapes.

- [ ] **Step 3: Fix relationship metadata adapter**

In `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, ensure `toSubgraphResult()` preserves relationship metadata:

```typescript
    edges: relationships.map((r): ApiRelationship => ({
      id: r.id,
      type: r.type,
      source_id: r.source_id,
      target_id: r.target_id,
      properties: r.properties,
      metadata: r.metadata,
      created_at: r.created_at,
      updated_at: r.updated_at,
      version: r.version,
      weight: r.weight,
    })),
```

If `ApiRelationship` from `src/types/api.ts` lacks `metadata`, update that UI type or migrate `GraphCanvas` types to generated aliases in the same file.

- [ ] **Step 4: Fix generated optional/default fields at call sites**

For every TypeScript error caused by generated optional/default fields, normalize at API boundary or component boundary. Example for arrays:

```typescript
const messages = conversation.messages ?? []
```

Do not use `as any`. If the backend always returns the field because a Pydantic default exists, prefer a type alias helper in `contracts.ts` only when it composes the generated schema without changing wire fields:

```typescript
export type ChatMessageResponse = Schemas['ChatMessageResponse'] & {
  citation_ids: NonNullable<Schemas['ChatMessageResponse']['citation_ids']>
  citations: NonNullable<Schemas['ChatMessageResponse']['citations']>
}
```

Use this helper pattern sparingly and only for defaults known to be emitted by FastAPI.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd chili_app
npx tsc --noEmit
npm run lint
npm run test:run
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add chili_app/src/api/contracts.ts chili_app/src
git commit -m "refactor: alias frontend contracts to generated openapi types"
```

### Task 7: Frontend Record Validator Parity

**Files:**
- Modify: `chili_app/src/lib/ingestion/validateIngestion.ts`
- Modify: `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`

- [ ] **Step 1: Add failing parity tests**

Add cases to `validateIngestion.test.ts`:

```typescript
it('validates enum values and numeric bounds from record schema', () => {
  const boundedFeed: RecordFeedConfig = {
    ...feed,
    record_schema: {
      ...feed.record_schema,
      claim_type: {
        type: 'enum',
        display: 'Claim Type',
        required: true,
        enum_values: ['inpatient', 'outpatient'],
      },
      anomaly_score: {
        type: 'decimal',
        display: 'Anomaly Score',
        required: true,
        min_value: 0,
        max_value: 1,
      },
    },
  }

  const issues = validateRecordRows(boundedFeed, [
    {
      claim_id: 'c1',
      provider_npi: '1234567890',
      billed_amount: '99.50',
      service_date: '2026-01-15',
      anomaly_score: '1.5',
      claim_type: 'other',
    },
  ])

  expect(issues.map((issue) => issue.message)).toEqual([
    'Row 1 field Claim Type must be one of inpatient, outpatient.',
    'Row 1 field Anomaly Score must be <= 1.',
  ])
})

it('validates string min and max length from record schema', () => {
  const lengthFeed: RecordFeedConfig = {
    ...feed,
    record_schema: {
      ...feed.record_schema,
      claim_id: {
        type: 'string',
        display: 'Claim ID',
        required: true,
        min_length: 3,
        max_length: 6,
      },
    },
  }

  expect(validateRecordRows(lengthFeed, [{ claim_id: 'c', provider_npi: '1234567890', billed_amount: '1', service_date: '2026-01-15', anomaly_score: '0.1' }])).toMatchObject([
    { message: 'Row 1 field Claim ID must have length >= 3.' },
  ])

  expect(validateRecordRows(lengthFeed, [{ claim_id: 'claim-100', provider_npi: '1234567890', billed_amount: '1', service_date: '2026-01-15', anomaly_score: '0.1' }])).toMatchObject([
    { message: 'Row 1 field Claim ID must have length <= 6.' },
  ])
})
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd chili_app
npm run test:run -- src/lib/ingestion/__tests__/validateIngestion.test.ts
```

Expected: FAIL because frontend validator does not enforce enum/range/length constraints.

- [ ] **Step 3: Implement missing parity checks**

In `validatePrimitive()` in `validateIngestion.ts`, after type checks and before pattern checks, add:

```typescript
  if (definition.type === 'enum') {
    const values = definition.enum_values ?? []
    if (!values.includes(String(value))) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-enum`,
          `Row ${rowNumber} field ${display} must be one of ${values.join(', ')}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }

  if (definition.type === 'decimal' || definition.type === 'integer') {
    const parsed = numericValue(value)
    if (parsed !== null && definition.min_value !== undefined && definition.min_value !== null && parsed < definition.min_value) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-min`,
          `Row ${rowNumber} field ${display} must be >= ${definition.min_value}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
    if (parsed !== null && definition.max_value !== undefined && definition.max_value !== null && parsed > definition.max_value) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-max`,
          `Row ${rowNumber} field ${display} must be <= ${definition.max_value}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }

  if (['string', 'list', 'nested'].includes(definition.type)) {
    const length = Array.isArray(value)
      ? value.length
      : value && typeof value === 'object'
        ? Object.keys(value).length
        : String(value).length
    if (definition.min_length !== undefined && definition.min_length !== null && length < definition.min_length) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-min-length`,
          `Row ${rowNumber} field ${display} must have length >= ${definition.min_length}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
    if (definition.max_length !== undefined && definition.max_length !== null && length > definition.max_length) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-max-length`,
          `Row ${rowNumber} field ${display} must have length <= ${definition.max_length}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
cd chili_app
npm run test:run -- src/lib/ingestion/__tests__/validateIngestion.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add chili_app/src/lib/ingestion/validateIngestion.ts chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts
git commit -m "fix: align frontend record validation with backend schema"
```

### Task 8: Static Contract Guardrail Script

**Files:**
- Create: `scripts/contract_guardrails.py`
- Create: `tests/scripts/test_contract_guardrails.py`

- [ ] **Step 1: Write guardrail tests**

Create `tests/scripts/test_contract_guardrails.py`:

```python
from __future__ import annotations

from pathlib import Path

from scripts.contract_guardrails import check_paths


def test_guardrail_rejects_manual_contract_type(tmp_path: Path) -> None:
    app = tmp_path / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    contracts.parent.mkdir(parents=True)
    contracts.write_text("export type FooResponse = { id: string }\n", encoding="utf-8")
    schema = app / "src" / "lib" / "api" / "schema.ts"
    schema.parent.mkdir(parents=True)
    schema.write_text("// Generated from backend OpenAPI. Do not edit by hand.\n// Run: npm run codegen:api\n", encoding="utf-8")

    errors = check_paths(tmp_path)

    assert any("manual exported DTO" in error for error in errors)


def test_guardrail_accepts_generated_alias_contract(tmp_path: Path) -> None:
    app = tmp_path / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    contracts.parent.mkdir(parents=True)
    contracts.write_text(
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Schemas['FooResponse']\n",
        encoding="utf-8",
    )
    schema = app / "src" / "lib" / "api" / "schema.ts"
    schema.parent.mkdir(parents=True)
    schema.write_text("// Generated from backend OpenAPI. Do not edit by hand.\n// Run: npm run codegen:api\n", encoding="utf-8")

    assert check_paths(tmp_path) == []


def test_guardrail_rejects_direct_schema_import_outside_contracts(tmp_path: Path) -> None:
    app = tmp_path / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    contracts.parent.mkdir(parents=True)
    contracts.write_text(
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Schemas['FooResponse']\n",
        encoding="utf-8",
    )
    schema = app / "src" / "lib" / "api" / "schema.ts"
    schema.parent.mkdir(parents=True)
    schema.write_text("// Generated from backend OpenAPI. Do not edit by hand.\n// Run: npm run codegen:api\n", encoding="utf-8")
    offender = app / "src" / "pages" / "Bad.ts"
    offender.parent.mkdir(parents=True)
    offender.write_text("import type { components } from '../lib/api/schema'\n", encoding="utf-8")

    errors = check_paths(tmp_path)

    assert any("direct generated schema import" in error for error in errors)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --project backend pytest tests/scripts/test_contract_guardrails.py -q
```

Expected: FAIL because `scripts.contract_guardrails` does not exist.

- [ ] **Step 3: Implement guardrail script**

Create `scripts/contract_guardrails.py`:

```python
"""Static guardrails for frontend/backend contract alignment."""

from __future__ import annotations

import re
import sys
from pathlib import Path


GENERATED_HEADER = (
    "// Generated from backend OpenAPI. Do not edit by hand.\n"
    "// Run: npm run codegen:api\n"
)
MANUAL_EXPORT_RE = re.compile(r"^\s*export\s+(?:type|interface)\s+\w+(?:\s*=\s*\{|\s*\{)", re.MULTILINE)
ALLOWED_ALIAS_RE = re.compile(r"^\s*export\s+type\s+\w+\s*=\s*(?:Schemas\[|NonNullable<|Record<|components\[)", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_paths(root: Path) -> list[str]:
    errors: list[str] = []
    app = root / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    schema = app / "src" / "lib" / "api" / "schema.ts"

    schema_text = _read(schema)
    if not schema_text.startswith(GENERATED_HEADER):
        errors.append(f"{schema}: missing generated OpenAPI header")

    contracts_text = _read(contracts)
    for match in MANUAL_EXPORT_RE.finditer(contracts_text):
        line = contracts_text.count("\n", 0, match.start()) + 1
        line_text = contracts_text.splitlines()[line - 1]
        if not ALLOWED_ALIAS_RE.match(line_text):
            errors.append(f"{contracts}:{line}: manual exported DTO is forbidden")

    for path in (app / "src").rglob("*.ts*"):
        if path == contracts:
            continue
        text = _read(path)
        if "lib/api/schema" in text:
            errors.append(f"{path}: direct generated schema import is forbidden")
        if "as any" in text or "Record<string, any>" in text:
            errors.append(f"{path}: any-based API contract escape hatch is forbidden")
        if path.parts[-2:] != ("api", "contracts.ts") and "src/types/api" in text:
            errors.append(f"{path}: src/types/api must not be used for wire contracts")

    return errors


def main() -> int:
    root = Path.cwd()
    errors = check_paths(root)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run guardrail tests**

Run:

```bash
uv run --project backend pytest tests/scripts/test_contract_guardrails.py -q
```

Expected: PASS.

- [ ] **Step 5: Run guardrail against current repo**

Run:

```bash
uv run --project backend python scripts/contract_guardrails.py
```

Expected: PASS after Tasks 5 and 6 are complete.

- [ ] **Step 6: Commit Task 8**

```bash
git add scripts/contract_guardrails.py tests/scripts/test_contract_guardrails.py
git commit -m "tooling: enforce generated api contract guardrails"
```

### Task 9: CI Drift Gate And Docs Guardrails

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `CLAUDE.md`
- Modify: `.github/copilot-instructions.md`
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `chili_app/README.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Add CI codegen drift check**

In `.github/workflows/ci.yml`, add a job after `backend` and before `frontend`:

```yaml
  api-contracts:
    name: API contracts (OpenAPI + frontend schema drift)
    runs-on: ubuntu-latest
    needs: backend
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install backend dev dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e "backend[dev]"

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install frontend dependencies
        working-directory: chili_app
        run: npm ci --legacy-peer-deps || npm install --legacy-peer-deps

      - name: Export OpenAPI and regenerate frontend schema
        run: |
          uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
          cd chili_app
          npm run codegen:api

      - name: Check generated contract drift
        run: git diff --exit-code -- chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts

      - name: Run contract guardrails
        run: uv run --project backend python scripts/contract_guardrails.py
```

If CI does not have `uv`, replace the two `uv run --project backend ...` commands with:

```bash
python -m tools.export_openapi --output chili_app/openapi.json
python scripts/contract_guardrails.py
```

after installing backend editable dependencies.

- [ ] **Step 2: Add contract rules to `CLAUDE.md`**

Add this subsection under "Architecture: Hard Rules":

```markdown
### 5. Frontend API contracts are generated from backend OpenAPI
Backend FastAPI OpenAPI is the source of truth for HTTP request/response shapes. Frontend code must import API DTOs from `chili_app/src/api/contracts.ts`, which aliases generated types from `chili_app/src/lib/api/schema.ts`. Do not hand-write frontend wire DTOs, do not edit generated schema files, and do not patch type failures with `as any`. When a frontend-consumed backend route changes, update the Pydantic request/response model, export OpenAPI, run `npm run codegen:api`, then update UI adapters.
```

- [ ] **Step 3: Add contract rules to `.github/copilot-instructions.md`**

Add this bullet under "Architecture Guardrails":

```markdown
- Frontend HTTP DTOs are generated from backend OpenAPI. Use `chili_app/src/api/contracts.ts` aliases for API shapes; do not hand-write `*Request` or `*Response` wire types in frontend code. Domain configuration remains runtime data: do not hardcode domain entity names, relationship names, record fields, or capability values.
```

- [ ] **Step 4: Update README command docs**

In root `README.md`, add this section:

````markdown
### API Contract Codegen

Backend OpenAPI is the source of truth for frontend API DTOs.

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

Commit both `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` when backend API contracts change.
````

In `backend/README.md`, add the export command under development commands. In `chili_app/README.md`, update `npm run codegen:api` to state that it reads `openapi.json`, not a live server.

- [ ] **Step 5: Update architecture contract section**

In `docs/architecture.md`, update the frontend API client section to state:

```markdown
The FastAPI OpenAPI document is the source of truth for frontend HTTP contracts. The frontend commits a generated schema at `chili_app/src/lib/api/schema.ts`; `chili_app/src/api/contracts.ts` only aliases generated schemas and may not define hand-written wire DTOs. Domain configuration remains runtime data: generated types describe the config structure, while entity names, relationship names, property names, record fields, and capabilities are read from `/config/domain`.
```

- [ ] **Step 6: Run docs and guardrail verification**

Run:

```bash
uv run --project backend python scripts/contract_guardrails.py
git diff --check
```

Expected: PASS.

- [ ] **Step 7: Commit Task 9**

```bash
git add .github/workflows/ci.yml CLAUDE.md .github/copilot-instructions.md README.md backend/README.md chili_app/README.md docs/architecture.md
git commit -m "docs: document generated api contract workflow"
```

### Task 10: Final Verification Sweep

**Files:**
- No new files; this task verifies all changes.

- [ ] **Step 1: Regenerate contracts from scratch**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
cd ..
git diff --exit-code -- chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts
```

Expected: PASS with no diff.

- [ ] **Step 2: Run backend focused tests**

Run:

```bash
uv run --project backend pytest \
  tools/tests/test_export_openapi.py \
  tests/scripts/test_contract_guardrails.py \
  backend/tests/api/test_app.py::TestOpenApiSchema \
  backend/tests/api/test_chat_router.py \
  backend/tests/api/test_investigation_router.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests and checks**

Run:

```bash
cd chili_app
npx tsc --noEmit
npm run lint
npm run test:run -- src/lib/ingestion/__tests__/validateIngestion.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run guardrail script**

Run:

```bash
uv run --project backend python scripts/contract_guardrails.py
```

Expected: PASS.

- [ ] **Step 5: Confirm final git state**

```bash
git status --short
```

Expected: only intentional changes from the completed tasks are present; no
untracked generated artifacts or accidental manual edits remain.
