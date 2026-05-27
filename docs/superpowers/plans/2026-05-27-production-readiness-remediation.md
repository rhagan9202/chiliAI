# Production Readiness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the confirmed live-data bugs and production-readiness gaps by making analytics KB-scoped, workflow completion truthful, mutations safer, Redis Streams recoverable, frontend state clearer, and verification full-stack.

**Architecture:** Backend OpenAPI remains the HTTP contract source of truth, while feature modules keep domain logic behind protocols. The FastAPI gateway adapts public DTOs, the agent coordinator owns workflow state, and the frontend consumes generated schema aliases plus runtime domain config. Each task is independently testable and avoids broad rewrites.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, uv, Redis Streams, React 19, TypeScript 5.9, Vite, TanStack Query, Vitest, Playwright/Puppeteer, Docker Compose.

---

## File Map

- Modify `backend/api/contracts.py`: add analytics availability fields and optional analytics projection DTOs.
- Modify `backend/api/routers/analytics.py`: require `kb_id` on entity detail endpoints and translate missing analytics into typed responses.
- Modify `backend/api/dependencies.py`: add KB-scoped analytics detail dependency helpers and live overview helper.
- Modify `backend/api/state.py`: stop production analytics detail/overview routes from hard-coded `kb-1`.
- Modify `backend/tests/api/test_analytics_router.py`: add KB-scoped analytics detail and overview consistency tests.
- Modify `chili_app/src/api/analytics.ts`: include KB ID in detail query keys and URLs.
- Modify `chili_app/src/pages/InvestigationWorkbenchPage.tsx`: pass active KB ID into analytics hooks and render unavailable state.
- Modify `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: assert KB-scoped analytics calls and unavailable rendering.
- Modify `backend/agent/workflow_tracking.py`: track `kb.ready`, mark it terminal success, and add stale reconciliation.
- Modify `backend/tests/agent/test_workflow_tracking.py`: add zero-vector `kb.ready` and stale reconciliation tests.
- Modify `backend/api/_workflow_projection.py`: project zero-vector and reconciled workflow metadata for the UI.
- Modify `backend/ingestion/service.py`: persist publish-failure recovery markers.
- Create `backend/ingestion/recovery.py`: recovery marker model and helper.
- Modify `backend/tests/ingestion/test_service.py`: cover object-store success followed by publish failure.
- Modify `backend/api/routers/records.py`: guard push records with KB existence, cleanup, and busy checks.
- Modify `backend/records/service.py`: skip downstream event publish when no records are accepted.
- Modify `backend/tests/api/test_records_router.py`: add push missing/busy/pending cleanup tests.
- Modify `backend/tests/records/test_service.py`: add duplicate submission no-event test.
- Modify `backend/events/protocols.py`: add stale pending reclaim protocol.
- Modify `backend/events/adapters/redis_streams.py`: add `MAXLEN` trimming and stale pending reclaim.
- Modify `backend/events/adapters/in_memory.py`: add no-op reclaim compatible with protocol.
- Modify `backend/tests/events/test_redis_streams.py`: cover trimming args, reclaim, and DLQ metadata.
- Modify `chili_app/src/app/router.tsx`: redirect `/knowledgebases` to `/knowledge-bases`.
- Modify `chili_app/src/components/knowledgebase/KbDetailView.tsx`: remove stale link target.
- Modify `chili_app/src/components/layout/AppShell.tsx`: record role redirect notice.
- Modify `chili_app/src/stores/uiStore.ts`: store transient access notice.
- Modify `chili_app/src/components/layout/TopBar.tsx`: render access notice.
- Modify `chili_app/src/components/layout/layout.css`: add mobile shell layout constraints.
- Modify `chili_app/src/pages/pages.css`: add investigation/mobile overflow constraints.
- Modify `chili_app/src/api/realtime.ts`: invalidate baseline queries after long disconnect.
- Modify frontend tests under `chili_app/src/app/__tests__`, `chili_app/src/api/__tests__`, and `chili_app/src/pages/__tests__`.
- Create `scripts/smoke_production_readiness.sh`: full-stack live-data smoke covering normal and zero-entity workflows.
- Modify `.github/workflows/ci.yml`: add focused backend/frontend checks if the existing workflow does not already run them.
- Regenerate `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` after API contract changes.

## Task 1: KB-Scoped Analytics API

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/analytics.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/tests/api/test_analytics_router.py`

- [ ] **Step 1: Add failing analytics detail tests**

Append these tests to `backend/tests/api/test_analytics_router.py`:

```python
from api.contracts import AnalyticsOverviewResponse, EntityTimeseriesResponse, RiskScoreResponse
from api.dependencies import (
    get_analytics_overview_payload,
    get_risk_score_payload,
    get_timeseries_payload,
)


def test_detail_risk_score_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores/provider-1")

    assert response.status_code == 422


def test_detail_timeseries_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/timeseries/provider-1")

    assert response.status_code == 422


def test_detail_risk_score_is_kb_scoped() -> None:
    app = FastAPI()
    app.include_router(router)

    def risk_payload(entity_id: str, kb_id: str) -> RiskScoreResponse:
        assert entity_id == "provider-1"
        assert kb_id == "kb-live"
        return RiskScoreResponse(
            entity_id=entity_id,
            overall_score=0.0,
            risk_level="low",
            factors=[],
            availability_status="unavailable",
            unavailable_reason="No risk profile has been generated for this entity.",
        )

    app.dependency_overrides[get_risk_score_payload] = risk_payload
    test_client = TestClient(app)

    response = test_client.get(
        "/analytics/risk-scores/provider-1",
        params={"kb_id": "kb-live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-1"
    assert payload["availability_status"] == "unavailable"


def test_detail_timeseries_is_kb_scoped() -> None:
    app = FastAPI()
    app.include_router(router)

    def timeseries_payload(entity_id: str, kb_id: str) -> EntityTimeseriesResponse:
        assert entity_id == "provider-1"
        assert kb_id == "kb-live"
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name="normalized_alert_pressure",
            points=[],
            availability_status="unavailable",
            unavailable_reason="No time series has been generated for this entity.",
        )

    app.dependency_overrides[get_timeseries_payload] = timeseries_payload
    test_client = TestClient(app)

    response = test_client.get(
        "/analytics/timeseries/provider-1",
        params={"kb_id": "kb-live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-1"
    assert payload["availability_status"] == "unavailable"


def test_overview_payload_can_be_overridden_from_live_projection() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_analytics_overview_payload] = lambda: AnalyticsOverviewResponse(
        active_alerts=0,
        open_cases=0,
        entities_monitored=4,
        high_risk_entities=0,
    )
    test_client = TestClient(app)

    response = test_client.get("/analytics/overview")

    assert response.status_code == 200
    assert response.json() == {
        "active_alerts": 0,
        "open_cases": 0,
        "entities_monitored": 4,
        "high_risk_entities": 0,
    }
```

- [ ] **Step 2: Run analytics tests and verify failure**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_analytics_router.py -q
```

Expected: FAIL because `availability_status` fields do not exist and detail dependencies do not receive `kb_id`.

- [ ] **Step 3: Extend analytics response contracts**

Modify `backend/api/contracts.py` so the analytics detail DTOs are:

```python
class RiskScoreResponse(BaseModel):
    """Risk summary for one entity."""

    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    factors: list[RiskFactorResponse] = Field(default_factory=lambda: cast(list[RiskFactorResponse], []))
    availability_status: Literal["available", "unavailable"] = "available"
    unavailable_reason: str | None = None


class EntityTimeseriesResponse(BaseModel):
    """Timeseries payload for entity trend charts."""

    entity_id: str
    metric_name: str
    points: list[EntityTimeseriesPointResponse] = Field(default_factory=lambda: cast(list[EntityTimeseriesPointResponse], []))
    availability_status: Literal["available", "unavailable"] = "available"
    unavailable_reason: str | None = None
```

- [ ] **Step 4: Make analytics detail dependencies KB-scoped**

Replace the detail helpers in `backend/api/dependencies.py` with:

```python
def get_risk_score_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(..., min_length=1, description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> RiskScoreResponse:
    """Return a KB-scoped risk-score payload."""
    return state.get_risk_score(entity_id, knowledge_base_id=kb_id)


def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(..., min_length=1, description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> EntityTimeseriesResponse:
    """Return a KB-scoped timeseries payload."""
    return state.get_timeseries(entity_id, knowledge_base_id=kb_id)
```

Ensure `Query` is imported from `fastapi` in `backend/api/dependencies.py`.

- [ ] **Step 5: Adapt ApiState methods without hard-coded KB scope**

Modify `backend/api/state.py` so the method signatures and missing-data handling are:

```python
    def get_risk_score(self, entity_id: str, *, knowledge_base_id: str | None = None) -> RiskScoreResponse:
        kb_id = knowledge_base_id or self._knowledge_base_id
        try:
            response = self._risk_service.assess(
                RiskAssessmentRequest(knowledge_base_id=kb_id, entity_id=entity_id)
            )
        except Exception:
            return RiskScoreResponse(
                entity_id=entity_id,
                overall_score=0.0,
                risk_level="low",
                factors=[],
                availability_status="unavailable",
                unavailable_reason="No risk profile has been generated for this entity.",
            )
        return RiskScoreResponse(
            entity_id=response.entity_id,
            overall_score=response.overall_score,
            risk_level=_normalize_risk_level(response.risk_level, response.overall_score),
            factors=[
                RiskFactorResponse(
                    factor_name=factor.factor_name,
                    contribution=factor.contribution,
                    rationale=factor.rationale,
                )
                for factor in response.factors
            ],
            availability_status="available",
            unavailable_reason=None,
        )

    def get_timeseries(self, entity_id: str, *, knowledge_base_id: str | None = None) -> EntityTimeseriesResponse:
        kb_id = knowledge_base_id or self._knowledge_base_id
        try:
            series = self._timeseries_source.load_series(
                knowledge_base_id=kb_id,
                entity_id=entity_id,
                metric_name="normalized_alert_pressure",
            )
            analysis = self._timeseries_service.analyze(
                TimeseriesAnalysisRequest(
                    knowledge_base_id=kb_id,
                    entity_id=entity_id,
                    metric_name=series.metric_name,
                    baseline_window=3,
                    min_history=5,
                    z_threshold=2.0,
                )
            )
        except Exception:
            return EntityTimeseriesResponse(
                entity_id=entity_id,
                metric_name="normalized_alert_pressure",
                points=[],
                availability_status="unavailable",
                unavailable_reason="No time series has been generated for this entity.",
            )
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name=series.metric_name,
            points=[
                EntityTimeseriesPointResponse(
                    timestamp=point.timestamp,
                    value=point.value,
                    label=point.label,
                    is_anomaly=point.timestamp in analysis.anomaly_timestamps,
                )
                for point in series.points
            ],
            availability_status="available",
            unavailable_reason=None,
        )
```

Use the existing `series.observations` and `analysis.anomalies` fields shown in `backend/api/state.py`: each point maps `observation.observed_at` to `timestamp`, `observation.value` to `value`, `observation.observed_at.strftime("%b %d")` to `label`, and membership in `{anomaly.observed_at for anomaly in analysis.anomalies}` to `is_anomaly`.

- [ ] **Step 6: Keep analytics routes thin**

`backend/api/routers/analytics.py` can keep the current detail routes because the dependency now owns `kb_id` validation:

```python
@router.get(
    "/risk-scores/{entity_id}",
    response_model=RiskScoreResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_risk_score(
    payload: RiskScoreResponse = Depends(get_risk_score_payload),
) -> RiskScoreResponse:
    """Return the risk score breakdown for one entity."""
    return payload


@router.get(
    "/timeseries/{entity_id}",
    response_model=EntityTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_entity_timeseries(
    payload: EntityTimeseriesResponse = Depends(get_timeseries_payload),
) -> EntityTimeseriesResponse:
    """Return chartable time-series points for one entity."""
    return payload
```

- [ ] **Step 7: Run focused backend tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_analytics_router.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit analytics API changes**

Run:

```bash
git add backend/api/contracts.py backend/api/routers/analytics.py backend/api/dependencies.py backend/api/state.py backend/tests/api/test_analytics_router.py
git commit -m "fix: scope analytics detail endpoints by knowledge base"
```

## Task 2: Frontend Analytics Scope And Unavailable State

**Files:**
- Modify: `chili_app/src/api/analytics.ts`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

- [ ] **Step 1: Add failing frontend test for KB-scoped analytics hooks**

In `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`, extend the analytics mock:

```ts
const analyticsCalls = vi.hoisted(() => ({
  risk: [] as Array<[string | null, string | null]>,
  timeseries: [] as Array<[string | null, string | null]>,
}))

vi.mock('../../api/analytics', () => ({
  useRiskScore: (knowledgeBaseId: string | null, entityId: string | null) => {
    analyticsCalls.risk.push([knowledgeBaseId, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        entity_id: entityId ?? '',
        overall_score: 0,
        risk_level: 'low',
        factors: [],
        availability_status: 'unavailable',
        unavailable_reason: 'No risk profile has been generated for this entity.',
      },
    }
  },
  useTimeseries: (knowledgeBaseId: string | null, entityId: string | null) => {
    analyticsCalls.timeseries.push([knowledgeBaseId, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        entity_id: entityId ?? '',
        metric_name: 'normalized_alert_pressure',
        points: [],
        availability_status: 'unavailable',
        unavailable_reason: 'No time series has been generated for this entity.',
      },
    }
  },
}))
```

Add this assertion test:

```ts
it('passes active knowledge base scope into analytics queries', () => {
  const provider: RuntimeEntity = {
    id: 'provider-204',
    type: 'provider',
    properties: { npi: '1234567890' },
    metadata: {},
    created_at: '2026-05-10T00:00:00Z',
    updated_at: null,
    version: 1,
  }
  mocks.knowledgeBases = [
    {
      id: 'kb-live',
      name: 'Live Fraud KB',
      description: 'Live KB',
      status: 'ready',
      document_count: 1,
      entity_count: 1,
      relationship_count: 0,
      created_at: '2026-05-10T00:00:00Z',
    },
  ]
  mocks.selectedEntity = provider
  mocks.routeEntityId = 'provider-204'
  analyticsCalls.risk = []
  analyticsCalls.timeseries = []

  render(<InvestigationWorkbenchPage />)

  expect(analyticsCalls.risk.at(-1)).toEqual(['kb-live', 'provider-204'])
  expect(analyticsCalls.timeseries.at(-1)).toEqual(['kb-live', 'provider-204'])
  expect(screen.getByText(/No risk profile has been generated/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run frontend page test and verify failure**

Run:

```bash
pnpm --dir chili_app test -- src/pages/__tests__/InvestigationWorkbenchPage.test.tsx --run
```

Expected: FAIL because `useRiskScore` and `useTimeseries` currently accept only `entityId`.

- [ ] **Step 3: Update analytics API wrapper**

Replace `chili_app/src/api/analytics.ts` detail helpers with:

```ts
export function riskScoreQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'risk-score', knowledgeBaseId ?? 'missing', entityId ?? 'missing'] as const
}

export function timeseriesQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'timeseries', knowledgeBaseId ?? 'missing', entityId ?? 'missing'] as const
}

export function getRiskScore(knowledgeBaseId: string, entityId: string): Promise<RiskScoreResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId })
  return apiFetch<RiskScoreResponse>(`/analytics/risk-scores/${encodeURIComponent(entityId)}?${params}`)
}

export function getTimeseries(knowledgeBaseId: string, entityId: string): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId })
  return apiFetch<TimeseriesResponse>(`/analytics/timeseries/${encodeURIComponent(entityId)}?${params}`)
}

export function useRiskScore(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: riskScoreQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getRiskScore(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}

export function useTimeseries(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: timeseriesQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getTimeseries(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}
```

- [ ] **Step 4: Pass KB ID from Investigation Workbench**

In `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, replace:

```ts
const riskQuery = useRiskScore(selectedEntityId)
const timeseriesQuery = useTimeseries(selectedEntityId)
```

with:

```ts
const riskQuery = useRiskScore(activeKnowledgeBaseId, selectedEntityId)
const timeseriesQuery = useTimeseries(activeKnowledgeBaseId, selectedEntityId)
```

Add unavailable message rendering near the existing risk empty state:

```tsx
const riskUnavailableReason =
  riskScore?.availability_status === 'unavailable' ? riskScore.unavailable_reason : null
```

Then replace the current no-risk `EmptyState` branch with:

```tsx
<EmptyState
  description={riskUnavailableReason ?? 'Risk scoring is unavailable until an entity is selected and analytics respond.'}
  title="No risk score"
/>
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
pnpm --dir chili_app test -- src/pages/__tests__/InvestigationWorkbenchPage.test.tsx --run
```

Expected: PASS.

- [ ] **Step 6: Commit frontend analytics scope changes**

Run:

```bash
git add chili_app/src/api/analytics.ts chili_app/src/pages/InvestigationWorkbenchPage.tsx chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx
git commit -m "fix: pass knowledge base scope to investigation analytics"
```

## Task 3: Workflow kb.ready Completion And Reconciliation

**Files:**
- Modify: `backend/agent/workflow_tracking.py`
- Modify: `backend/api/_workflow_projection.py`
- Modify: `backend/tests/agent/test_workflow_tracking.py`

- [ ] **Step 1: Add failing workflow tests**

Update imports in `backend/tests/agent/test_workflow_tracking.py`:

```python
from datetime import timedelta

from events.types import (
    AgentWorkflowStartedEvent,
    DocumentFailureReference,
    DocumentReference,
    DocumentsFailedEvent,
    DocumentsUploadedEvent,
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    RecordsIngestedEvent,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from shared.utils import utc_now
```

Append:

```python
def test_tracker_marks_kb_ready_event_terminal_for_zero_vector_workflow() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-ready",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="ready"),
                    WorkflowStepState(step_name="monitoring"),
                ],
                metadata={"correlation_id": "corr-ready"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)
    event = KnowledgeBaseReadyEvent(
        correlation_id="corr-ready",
        knowledge_bases=[
            KnowledgeBaseReadyReference(
                knowledge_base_id="kb-1",
                entity_count=0,
                relationship_count=0,
                vector_count=0,
            )
        ],
    )

    assert tracker.begin_event(event) is True
    tracker.complete_event(event)

    run = run_store.get_run("workflow-ready")
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.steps[0].status is WorkflowStepStatus.COMPLETED
    assert run.metadata["last_event_type"] == "kb.ready"
    assert run.metadata["entity_count"] == 0
    assert run.metadata["vector_count"] == 0


def test_reconcile_stale_runs_marks_old_running_workflow_failed() -> None:
    old_time = utc_now() - timedelta(hours=3)
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-stale",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="vector_index", status=WorkflowStepStatus.RUNNING)],
                updated_at=old_time,
                metadata={"correlation_id": "corr-stale"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 1
    run = run_store.get_run("workflow-stale")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.metadata["reason"] == "stale_workflow_reconciled"
```

- [ ] **Step 2: Run workflow tests and verify failure**

Run:

```bash
uv run --project backend pytest backend/tests/agent/test_workflow_tracking.py -q
```

Expected: FAIL because `kb.ready` is untracked and `reconcile_stale_runs` does not exist.

- [ ] **Step 3: Track kb.ready and terminal success**

Modify `backend/agent/workflow_tracking.py` imports to include:

```python
    KnowledgeBaseReadyEvent,
```

Update constants:

```python
_STEP_BY_EVENT_TYPE: dict[str, str] = {
    "documents.uploaded": "parse",
    "documents.parsed": "chunk",
    "documents.failed": "parse",
    "records.ingested": "records_ingest",
    "documents.chunked": "extract",
    "entities.extracted": "validate",
    "entities.validated": "graph_build",
    "graph.updated": "embed",
    "embeddings.complete": "vector_index",
    "vectors.indexed": "ready",
    "kb.ready": "ready",
    "risk.scored": "monitoring",
}

_TERMINAL_SUCCESS_EVENT_TYPES: frozenset[str] = frozenset(
    {"vectors.indexed", "kb.ready", "risk.scored", "records.ingested"}
)
```

In `complete_event`, after `metadata["last_event_type"] = event.event_type`, add:

```python
        metadata.update(_summary_metadata_for_event(event))
```

Add helper functions near `_knowledge_base_id_for_event`:

```python
def _summary_metadata_for_event(event: AnyEvent) -> dict[str, MetadataValue]:
    if isinstance(event, KnowledgeBaseReadyEvent) and event.knowledge_bases:
        first = event.knowledge_bases[0]
        return {
            "entity_count": first.entity_count,
            "relationship_count": first.relationship_count,
            "vector_count": first.vector_count,
        }
    return {}
```

Update `_knowledge_base_id_for_event` to include:

```python
    if isinstance(event, KnowledgeBaseReadyEvent) and event.knowledge_bases:
        return event.knowledge_bases[0].knowledge_base_id
```

- [ ] **Step 4: Add stale reconciliation method**

Add this method to `WorkflowEventTracker`:

```python
    def reconcile_stale_runs(self, *, max_age_seconds: int) -> int:
        """Mark old queued/running runs failed so UI and busy checks do not hang."""
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than 0.")
        cutoff = utc_now().timestamp() - max_age_seconds
        reconciled = 0
        for status in (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING):
            for run in self._run_store.list_runs(status=status, limit=1000):
                if run.updated_at.timestamp() >= cutoff:
                    continue
                metadata = dict(run.metadata)
                metadata["reason"] = "stale_workflow_reconciled"
                self._run_store.update_run(
                    run.workflow_id,
                    WorkflowRunUpdate(
                        status=WorkflowRunStatus.FAILED,
                        metadata=metadata,
                        updated_at=utc_now(),
                    ),
                )
                reconciled += 1
        return reconciled
```

- [ ] **Step 5: Run workflow tests**

Run:

```bash
uv run --project backend pytest backend/tests/agent/test_workflow_tracking.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit workflow tracking changes**

Run:

```bash
git add backend/agent/workflow_tracking.py backend/api/_workflow_projection.py backend/tests/agent/test_workflow_tracking.py
git commit -m "fix: complete workflows on knowledge base ready events"
```

## Task 4: Records Push Guards And Duplicate Event Suppression

**Files:**
- Modify: `backend/api/routers/records.py`
- Modify: `backend/records/service.py`
- Modify: `backend/tests/api/test_records_router.py`
- Modify: `backend/tests/records/test_service.py`

- [ ] **Step 1: Add failing records router tests**

Append to `backend/tests/api/test_records_router.py`:

```python
def test_push_records_rejects_missing_knowledge_base(client: TestClient) -> None:
    response = client.post(
        "/records/missing-kb/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c-missing",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 404


def test_push_records_rejects_busy_knowledge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient as TC
    from api.app import create_app
    from api.dependencies import get_raw_record_store, get_workflow_tracker

    class BusyTracker:
        def is_busy(self, knowledge_base_id: str) -> bool:
            return knowledge_base_id == "kb-1"

    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
    app = create_app()
    app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
    app.dependency_overrides[get_workflow_tracker] = lambda: BusyTracker()
    test_client = TC(app)

    response = test_client.post(
        "/records/kb-1/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c-busy",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 409
```

- [ ] **Step 2: Add failing duplicate records service test**

Append to `backend/tests/records/test_service.py`:

```python
def test_register_records_does_not_publish_event_when_no_new_records() -> None:
    store = InMemoryRawRecordStore()
    event_bus = InMemoryEventBus()
    service = create_records_service(
        store,
        event_bus=event_bus,
        records_config=_records_config(),
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[
            {
                "claim_id": "claim-1",
                "amount": "100",
            }
        ],
        source_type="api_push",
        source_ref=None,
    )

    first = service.register_records("kb-1", submission)
    second = service.register_records("kb-1", submission)

    assert first.accepted_count == 1
    assert second.accepted_count == 0
    assert [event.event_type for event in event_bus.published_events] == ["records.ingested"]
```

This test uses `_records_config`, `InMemoryRawRecordStore`, `InMemoryEventBus`, `create_records_service`, and `RecordSubmission`, which are already imported in `backend/tests/records/test_service.py`.

- [ ] **Step 3: Run records tests and verify failure**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_records_router.py backend/tests/records/test_service.py -q
```

Expected: FAIL because push does not check KB/busy state and service publishes an event for zero accepted records.

- [ ] **Step 4: Guard records push route**

Modify `backend/api/routers/records.py` `push_records` signature:

```python
async def push_records(
    knowledge_base_id: str,
    payload: RecordPushRequest,
    service: RecordsServiceProtocol = Depends(get_records_service),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
) -> RecordIngestReceipt:
```

Add the guard block at the start of `push_records`:

```python
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' was not found.",
        )
    if existing_kb.pending_cleanup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Knowledge base '{knowledge_base_id}' has pending cleanup; cannot mutate until resolved.",
        )
    try:
        ensure_kb_idle(knowledge_base_id, tracker=workflow_tracker)
    except KbBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
```

- [ ] **Step 5: Suppress zero-accepted records events**

Modify `backend/records/service.py`:

```python
        accepted = self._store.persist(raw_records)
        if accepted > 0:
            self._event_bus.publish(
                RecordsIngestedEvent(
                    correlation_id=correlation_id,
                    knowledge_base_id=knowledge_base_id,
                    feed_name=feed.name,
                    record_type=feed.record_type,
                    record_count=accepted,
                )
            )
        return RecordIngestReceipt(
            knowledge_base_id=knowledge_base_id,
            feed_name=feed.name,
            record_type=feed.record_type,
            correlation_id=correlation_id,
            accepted_count=accepted,
        )
```

- [ ] **Step 6: Run records tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_records_router.py backend/tests/records/test_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit records guard changes**

Run:

```bash
git add backend/api/routers/records.py backend/records/service.py backend/tests/api/test_records_router.py backend/tests/records/test_service.py
git commit -m "fix: guard records push mutations"
```

## Task 5: Ingestion Publish-Failure Recovery Marker

**Files:**
- Create: `backend/ingestion/recovery.py`
- Modify: `backend/ingestion/service.py`
- Modify: `backend/tests/ingestion/test_service.py`

- [ ] **Step 1: Add failing ingestion recovery test**

Append to `backend/tests/ingestion/test_service.py`:

```python
import pytest

from ingestion.recovery import InMemoryIngestionRecoveryStore


class FailingPublishBus:
    def publish(self, event):
        raise RuntimeError("redis unavailable")

    def ensure_consumer_group(self, event_types, *, consumer_group):
        return None

    def consume(self, event_types, *, consumer_group=None, consumer_name=None, limit=1, block_ms=None):
        return []

    def ack(self, deliveries):
        return None

    def publish_to_dlq(self, event, error_info):
        return None


def test_register_documents_records_recovery_marker_when_publish_fails() -> None:
    recovery_store = InMemoryIngestionRecoveryStore()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=FailingPublishBus(),
        recovery_store=recovery_store,
    )

    with pytest.raises(RuntimeError, match="redis unavailable"):
        service.register_documents(
            "kb-1",
            [
                DocumentSubmission(
                    filename="claim.txt",
                    content=b"claim body",
                    content_type="text/plain",
                    document_format=DocumentFormat.TEXT,
                )
            ],
        )

    markers = recovery_store.list_markers()
    assert len(markers) == 1
    assert markers[0].knowledge_base_id == "kb-1"
    assert markers[0].source_document_id.startswith("doc-sha256-")
    assert markers[0].event_type == "documents.uploaded"
    assert "redis unavailable" in markers[0].failure_reason
```

- [ ] **Step 2: Run ingestion tests and verify failure**

Run:

```bash
uv run --project backend pytest backend/tests/ingestion/test_service.py -q
```

Expected: FAIL because `ingestion.recovery` and `recovery_store` do not exist.

- [ ] **Step 3: Add recovery marker model and in-memory store**

Create `backend/ingestion/recovery.py`:

```python
"""Recovery markers for ingestion writes that succeeded before event publication failed."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import generate_id, utc_now


class IngestionRecoveryMarker(BaseModel):
    marker_id: str = Field(default_factory=generate_id)
    knowledge_base_id: str
    source_document_id: str
    storage_key: str | None
    content_hash: str | None
    event_type: str
    failure_reason: str
    created_at: datetime = Field(default_factory=utc_now)


class InMemoryIngestionRecoveryStore:
    def __init__(self) -> None:
        self._markers: list[IngestionRecoveryMarker] = []

    def add_marker(self, marker: IngestionRecoveryMarker) -> None:
        self._markers.append(marker)

    def list_markers(self) -> list[IngestionRecoveryMarker]:
        return list(self._markers)


__all__ = ["IngestionRecoveryMarker", "InMemoryIngestionRecoveryStore"]
```

- [ ] **Step 4: Wire recovery store into ingestion service**

Modify `backend/ingestion/service.py` imports:

```python
from ingestion.recovery import IngestionRecoveryMarker, InMemoryIngestionRecoveryStore
```

Modify `IngestionService.__init__`:

```python
    def __init__(
        self,
        parser_orchestrator: ParserOrchestrator,
        *,
        object_store: ObjectStoreProtocol,
        event_bus: EventBus,
        recovery_store: InMemoryIngestionRecoveryStore | None = None,
    ) -> None:
        self._parser_orchestrator = parser_orchestrator
        self._object_store = object_store
        self._event_bus = event_bus
        self._recovery_store = recovery_store
```

Replace the publish block in `register_documents`:

```python
        if document_references:
            event = DocumentsUploadedEvent(documents=document_references)
            try:
                self._event_bus.publish(event)
            except Exception as exc:
                if self._recovery_store is not None:
                    for reference in document_references:
                        self._recovery_store.add_marker(
                            IngestionRecoveryMarker(
                                knowledge_base_id=reference.knowledge_base_id,
                                source_document_id=reference.source_document_id,
                                storage_key=reference.storage_key,
                                content_hash=next(
                                    (
                                        receipt.source_document_id.removeprefix("doc-sha256-")
                                        for receipt in receipts
                                        if receipt.source_document_id == reference.source_document_id
                                    ),
                                    None,
                                ),
                                event_type=event.event_type,
                                failure_reason=str(exc),
                            )
                        )
                raise
        return receipts
```

- [ ] **Step 5: Run ingestion tests**

Run:

```bash
uv run --project backend pytest backend/tests/ingestion/test_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit ingestion recovery marker**

Run:

```bash
git add backend/ingestion/recovery.py backend/ingestion/service.py backend/tests/ingestion/test_service.py
git commit -m "feat: record ingestion publish recovery markers"
```

## Task 6: Redis Streams Trim And Stale Pending Reclaim

**Files:**
- Modify: `backend/events/protocols.py`
- Modify: `backend/events/adapters/redis_streams.py`
- Modify: `backend/events/adapters/in_memory.py`
- Modify: `backend/tests/events/test_redis_streams.py`

- [ ] **Step 1: Add failing Redis adapter tests**

Extend `FakeRedis` in `backend/tests/events/test_redis_streams.py`:

```python
        self.xadd_calls: list[dict[str, object]] = []
        self.pending_response: list[dict[str, object]] = []
        self.autoclaim_response = ("0-0", [])
```

Replace `xadd` with:

```python
    def xadd(self, stream: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = False) -> str:
        self.xadd_calls.append(
            {"stream": stream, "fields": fields, "maxlen": maxlen, "approximate": approximate}
        )
        stream_messages = self.streams.setdefault(stream, [])
        message_id = f"{len(stream_messages) + 1}-0"
        stream_messages.append((message_id, fields))
        return message_id
```

Add methods:

```python
    def xpending_range(self, stream: str, groupname: str, min: str, max: str, count: int):
        del stream, groupname, min, max, count
        return self.pending_response

    def xautoclaim(self, stream: str, groupname: str, consumername: str, min_idle_time: int, start_id: str, count: int):
        del stream, groupname, consumername, min_idle_time, start_id, count
        return self.autoclaim_response
```

Append tests:

```python
def test_redis_streams_publish_uses_configured_maxlen() -> None:
    client = FakeRedis()
    event_bus = RedisStreamsEventBus(
        redis_url="redis://unused",
        stream_name_resolver=lambda event_type: f"chili.{event_type}",
        stream_maxlen=1000,
        client=client,  # pyright: ignore[reportArgumentType]
    )
    event = DocumentsUploadedEvent(
        documents=[DocumentReference(knowledge_base_id="kb-1", source_document_id="doc-1")]
    )

    event_bus.publish(event)

    assert client.xadd_calls[0]["maxlen"] == 1000
    assert client.xadd_calls[0]["approximate"] is True


def test_redis_streams_reclaims_stale_pending_messages() -> None:
    client = FakeRedis()
    event = DocumentsUploadedEvent(
        documents=[DocumentReference(knowledge_base_id="kb-1", source_document_id="doc-1")]
    )
    encoded_id = client.xadd("chili.documents.uploaded", {"event_type": "documents.uploaded", "payload": event.model_dump_json()})
    client.autoclaim_response = (
        "0-0",
        [(encoded_id, client.streams["chili.documents.uploaded"][0][1])],
    )
    event_bus = RedisStreamsEventBus(
        redis_url="redis://unused",
        stream_name_resolver=lambda event_type: f"chili.{event_type}",
        client=client,  # pyright: ignore[reportArgumentType]
    )

    deliveries = event_bus.reclaim_stale_pending(
        ["documents.uploaded"],
        consumer_group="workers",
        consumer_name="worker-2",
        min_idle_ms=60000,
        limit=10,
    )

    assert len(deliveries) == 1
    assert deliveries[0].event.event_type == "documents.uploaded"
```

- [ ] **Step 2: Run Redis tests and verify failure**

Run:

```bash
uv run --project backend pytest backend/tests/events/test_redis_streams.py -q
```

Expected: FAIL because constructor `stream_maxlen` and `reclaim_stale_pending` do not exist.

- [ ] **Step 3: Extend EventBus protocol**

In `backend/events/protocols.py`, add:

```python
    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]: ...
```

- [ ] **Step 4: Implement Redis trimming and reclaim**

Modify `RedisStreamsEventBus.__init__`:

```python
        stream_maxlen: int | None = None,
```

Set:

```python
        self._stream_maxlen = stream_maxlen
```

Modify `publish`:

```python
            self._client.xadd(
                stream,
                encode_event(event),
                maxlen=self._stream_maxlen,
                approximate=self._stream_maxlen is not None,
            ),
```

Add method:

```python
    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]:
        deliveries: list[EventDelivery] = []
        for event_type in event_types:
            stream = self._stream_name_resolver(event_type)
            response = self._client.xautoclaim(
                stream,
                consumer_group,
                consumer_name,
                min_idle_ms,
                "0-0",
                count=limit,
            )
            messages = response[1] if isinstance(response, tuple) else []
            for message_id, payload in messages:
                deliveries.append(
                    EventDelivery(
                        event=decode_event(payload),
                        event_id=_decode_redis_string(message_id),
                        stream=stream,
                        consumer_group=consumer_group,
                    )
                )
        return deliveries
```

- [ ] **Step 5: Add in-memory no-op reclaim**

In `backend/events/adapters/in_memory.py`, add:

```python
    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]:
        del event_types, consumer_group, consumer_name, min_idle_ms, limit
        return []
```

- [ ] **Step 6: Run events tests**

Run:

```bash
uv run --project backend pytest backend/tests/events/test_redis_streams.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Redis recovery slice**

Run:

```bash
git add backend/events/protocols.py backend/events/adapters/redis_streams.py backend/events/adapters/in_memory.py backend/tests/events/test_redis_streams.py
git commit -m "feat: reclaim stale redis stream deliveries"
```

## Task 7: Frontend Routing, Role Notice, Mobile Layout, And Realtime Reconnect

**Files:**
- Modify: `chili_app/src/app/router.tsx`
- Modify: `chili_app/src/components/knowledgebase/KbDetailView.tsx`
- Modify: `chili_app/src/components/layout/AppShell.tsx`
- Modify: `chili_app/src/components/layout/TopBar.tsx`
- Modify: `chili_app/src/components/layout/layout.css`
- Modify: `chili_app/src/stores/uiStore.ts`
- Modify: `chili_app/src/pages/pages.css`
- Modify: `chili_app/src/api/realtime.ts`
- Modify frontend tests.

- [ ] **Step 1: Add route and copy tests**

Add `chili_app/src/app/__tests__/router-routes.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'

import { router } from '../router'

describe('router canonical knowledge base routes', () => {
  it('registers a redirect for stale /knowledgebases path', () => {
    const root = router.routes.find((route) => route.path === '/')
    const childPaths = root?.children?.map((route) => route.path)

    expect(childPaths).toContain('knowledge-bases')
    expect(childPaths).toContain('knowledgebases')
  })
})
```

Add `chili_app/src/pages/__tests__/AnalystCopy.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'

import fs from 'node:fs'
import path from 'node:path'

const pagesDir = path.resolve(__dirname, '..')

describe('analyst-facing copy', () => {
  it('does not describe live pages as seeded or demo', () => {
    const pageFiles = fs.readdirSync(pagesDir).filter((file) => file.endsWith('.tsx'))
    const combined = pageFiles
      .map((file) => fs.readFileSync(path.join(pagesDir, file), 'utf8'))
      .join('\n')

    expect(combined).not.toMatch(/seeded investigation graph|seeded RAG service|demo read model/i)
  })
})
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```bash
pnpm --dir chili_app test -- src/app/__tests__/router-routes.test.tsx src/pages/__tests__/AnalystCopy.test.tsx --run
```

Expected: FAIL because `/knowledgebases` route is absent and seeded copy remains.

- [ ] **Step 3: Redirect stale route**

In `chili_app/src/app/router.tsx`, add this child route immediately after `knowledge-bases`:

```tsx
{ path: 'knowledgebases', element: <Navigate to="/knowledge-bases" replace /> },
```

In `chili_app/src/components/knowledgebase/KbDetailView.tsx`, replace:

```tsx
<Link to="/knowledgebases">← All knowledge bases</Link>
```

with:

```tsx
<Link to="/knowledge-bases">All knowledge bases</Link>
```

- [ ] **Step 4: Add role redirect notice state**

In `chili_app/src/stores/uiStore.ts`, add fields to the store type:

```ts
accessNotice: string | null
setAccessNotice: (message: string | null) => void
```

Add initial state and setter in the store body:

```ts
accessNotice: null,
setAccessNotice: (message) => set({ accessNotice: message }),
```

In `chili_app/src/components/layout/AppShell.tsx`, read the setter:

```ts
const setAccessNotice = useUiStore((state) => state.setAccessNotice)
```

Before returning `<Navigate replace to={landingRoute} />`, set the notice:

```tsx
  if (!domainConfigQuery.isLoading && !domainFeaturesQuery.isLoading && !routeAllowed) {
    setAccessNotice('Selected role cannot access that page.')
    return <Navigate replace to={landingRoute} />
  }
```

In `chili_app/src/components/layout/TopBar.tsx`, render:

```tsx
const accessNotice = useUiStore((state) => state.accessNotice)
const setAccessNotice = useUiStore((state) => state.setAccessNotice)
```

Place this inside the topbar:

```tsx
{accessNotice ? (
  <button
    className="app-topbar__notice"
    onClick={() => setAccessNotice(null)}
    type="button"
  >
    {accessNotice}
  </button>
) : null}
```

- [ ] **Step 5: Add mobile layout constraints**

Append to `chili_app/src/components/layout/layout.css`:

```css
@media (max-width: 900px) {
  .app-shell,
  .app-shell--ai-closed {
    display: block;
    min-width: 0;
  }

  .app-sidebar {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    overflow-x: auto;
    gap: 12px;
    padding: 12px;
  }

  .app-sidebar__nav {
    flex-direction: row;
    min-width: max-content;
  }

  .app-shell__main {
    min-width: 0;
    padding: 16px;
  }

  .ai-panel {
    display: none;
  }

  .app-topbar {
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .app-topbar__search {
    width: 100%;
  }

  .app-topbar__notice {
    min-height: 34px;
    padding: 0 10px;
    color: var(--c-text);
    background: rgba(251, 191, 36, 0.12);
    border: 1px solid rgba(251, 191, 36, 0.32);
    border-radius: 8px;
  }
}
```

Append to `chili_app/src/pages/pages.css`:

```css
@media (max-width: 760px) {
  .page-grid,
  .metric-stack,
  .investigation-graph-canvas,
  .chart-shell {
    min-width: 0;
    max-width: 100%;
  }

  .investigation-graph-canvas {
    height: 340px;
    overflow: hidden;
  }

  .page-actions-inline,
  .metric-row {
    min-width: 0;
    flex-wrap: wrap;
  }
}
```

- [ ] **Step 6: Add realtime baseline invalidation after long disconnect**

In `chili_app/src/api/realtime.ts`, add:

```ts
const BASELINE_RECONNECT_INVALIDATE_MS = 60000
```

Track disconnect time:

```ts
let disconnectedAt: number | null = null
```

Add helper inside `useEffect`:

```ts
const invalidateBaseline = () => {
  void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
  void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
  void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
}
```

In `eventSource.onopen`, add:

```ts
if (disconnectedAt !== null && Date.now() - disconnectedAt >= BASELINE_RECONNECT_INVALIDATE_MS) {
  invalidateBaseline()
}
disconnectedAt = null
```

In `eventSource.onerror`, before scheduling reconnect, add:

```ts
if (disconnectedAt === null) {
  disconnectedAt = Date.now()
}
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
pnpm --dir chili_app test -- src/app/__tests__/router-routes.test.tsx src/pages/__tests__/AnalystCopy.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx --run
pnpm --dir chili_app build
```

Expected: PASS.

- [ ] **Step 8: Commit frontend UX changes**

Run:

```bash
git add chili_app/src/app/router.tsx chili_app/src/components/knowledgebase/KbDetailView.tsx chili_app/src/components/layout/AppShell.tsx chili_app/src/components/layout/TopBar.tsx chili_app/src/components/layout/layout.css chili_app/src/stores/uiStore.ts chili_app/src/pages/pages.css chili_app/src/api/realtime.ts chili_app/src/app/__tests__/router-routes.test.tsx chili_app/src/pages/__tests__/AnalystCopy.test.tsx
git commit -m "fix: clarify frontend live workflow state"
```

## Task 8: Contract Regeneration And Full-Stack Smoke Gate

**Files:**
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Create: `scripts/smoke_production_readiness.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `chili_app/src/api/contracts.ts` if generated aliases need new analytics fields.

- [ ] **Step 1: Regenerate backend OpenAPI snapshot**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
```

Expected: `chili_app/openapi.json` changes include `availability_status`, `unavailable_reason`, and `kb_id` query parameters on analytics detail routes.

- [ ] **Step 2: Regenerate frontend schema**

Run:

```bash
pnpm --dir chili_app codegen:api
```

Expected: `chili_app/src/lib/api/schema.ts` changes include the updated analytics response fields.

- [ ] **Step 3: Add full-stack smoke script**

Create `scripts/smoke_production_readiness.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:5173}"

normal_output="$(API_BASE_URL="$API_BASE_URL" APP_BASE_URL="$APP_BASE_URL" bash scripts/smoke_graph_workflow.sh)"
printf '%s\n' "$normal_output"

kb_id="$(printf '%s\n' "$normal_output" | awk -F= '/knowledge_base_id=/{print $2}' | tail -n 1)"
entity_id="$(printf '%s\n' "$normal_output" | awk -F= '/entity_id=/{print $2}' | tail -n 1)"

if [[ -z "$kb_id" || -z "$entity_id" ]]; then
  echo "smoke_graph_workflow.sh did not report knowledge_base_id and entity_id" >&2
  exit 1
fi

risk_status="$(curl -sS -o /tmp/chiliai-risk.json -w '%{http_code}' "$API_BASE_URL/analytics/risk-scores/$entity_id?kb_id=$kb_id")"
timeseries_status="$(curl -sS -o /tmp/chiliai-timeseries.json -w '%{http_code}' "$API_BASE_URL/analytics/timeseries/$entity_id?kb_id=$kb_id")"

if [[ "$risk_status" != "200" ]]; then
  echo "risk detail returned HTTP $risk_status" >&2
  cat /tmp/chiliai-risk.json >&2
  exit 1
fi

if [[ "$timeseries_status" != "200" ]]; then
  echo "timeseries detail returned HTTP $timeseries_status" >&2
  cat /tmp/chiliai-timeseries.json >&2
  exit 1
fi

empty_kb_json="$(curl -sS -X POST "$API_BASE_URL/knowledgebases" -H 'content-type: application/json' -d '{"name":"Zero entity smoke","description":"Document with no extractable entities"}')"
empty_kb_id="$(printf '%s' "$empty_kb_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

printf 'plain prose without configured entity markers\n' >/tmp/chiliai-zero-entity.txt
curl -sS -X POST "$API_BASE_URL/knowledgebases/$empty_kb_id/documents" -F "file=@/tmp/chiliai-zero-entity.txt;type=text/plain" >/tmp/chiliai-zero-upload.json

deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  workflows="$(curl -sS "$API_BASE_URL/workflows?knowledge_base_id=$empty_kb_id&limit=10")"
  status="$(printf '%s' "$workflows" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["items"][0]["status"] if data["items"] else "")')"
  if [[ "$status" == "completed" ]]; then
    echo "zero entity workflow completed"
    exit 0
  fi
  if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
    echo "zero entity workflow reached unexpected status $status" >&2
    printf '%s\n' "$workflows" >&2
    exit 1
  fi
  sleep 2
done

echo "zero entity workflow did not complete within timeout" >&2
curl -sS "$API_BASE_URL/workflows?knowledge_base_id=$empty_kb_id&limit=10" >&2
exit 1
```

Make it executable:

```bash
chmod +x scripts/smoke_production_readiness.sh
```

- [ ] **Step 4: Add CI commands if absent**

If `.github/workflows/ci.yml` does not already run these exact checks, add steps to the backend/frontend jobs:

```yaml
- name: Backend production-readiness regression tests
  run: |
    uv run --project backend pytest \
      backend/tests/api/test_analytics_router.py \
      backend/tests/agent/test_workflow_tracking.py \
      backend/tests/api/test_records_router.py \
      backend/tests/records/test_service.py \
      backend/tests/events/test_redis_streams.py \
      backend/tests/ingestion/test_service.py -q

- name: Frontend production-readiness regression tests
  run: |
    pnpm --dir chili_app test -- \
      src/pages/__tests__/InvestigationWorkbenchPage.test.tsx \
      src/app/__tests__/router-routes.test.tsx \
      src/pages/__tests__/AnalystCopy.test.tsx --run
```

- [ ] **Step 5: Run final verification**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_analytics_router.py backend/tests/agent/test_workflow_tracking.py backend/tests/api/test_records_router.py backend/tests/records/test_service.py backend/tests/events/test_redis_streams.py backend/tests/ingestion/test_service.py -q
pnpm --dir chili_app test -- src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/app/__tests__/router-routes.test.tsx src/pages/__tests__/AnalystCopy.test.tsx --run
pnpm --dir chili_app build
```

Expected: PASS.

With the dev stack running, run:

```bash
API_BASE_URL=http://127.0.0.1:8000 APP_BASE_URL=http://127.0.0.1:5173 scripts/smoke_production_readiness.sh
```

Expected: PASS with `zero entity workflow completed`.

- [ ] **Step 6: Commit contract and smoke gate**

Run:

```bash
git add chili_app/openapi.json chili_app/src/lib/api/schema.ts scripts/smoke_production_readiness.sh .github/workflows/ci.yml chili_app/src/api/contracts.ts
git commit -m "test: add production readiness smoke gate"
```

## Self-Review Checklist

- Spec coverage: Tasks cover analytics, workflow, records, ingestion, Redis Streams, frontend UX, realtime state, contracts, CI, and E2E smoke.
- Placeholder scan: The plan contains no deferred-work markers or incomplete sections.
- Type consistency: New analytics fields are present in backend contracts first, then frontend generated schema and API usage.
- Boundary consistency: Feature logic stays in modules, HTTP adaptation stays in API routers/dependencies, workflow logic stays in agent tracking, and frontend consumes API wrappers.
