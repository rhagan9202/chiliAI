# Sprint 2026-28 B3 — Explainability Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM-backed evidence narratives with deterministic fallback, and real SHAP attribution of the linear risk scorer, persisted on evidence packs and served through the API contract (BL-048; analytics.13/.14 sprint slices).

**Architecture:** Two new seams inside `analytics/explainability` — `NarrativeGeneratorProtocol` (deterministic + LLM adapters) and `FeatureAttributorProtocol` (noop + SHAP adapters) — injected into `ExplainabilityService`, selected by two new `AnalyticsConfig` fields, wired in the worker coordinator. The persisted `EvidencePack` and `EvidencePackResponse` gain `narrative_sections` + `attribution`. Design: `docs/superpowers/specs/2026-07-23-sprint28-b3-explainability-design.md`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, shap/sklearn/numpy via the optional `[analytics]` extra (lazy imports), pytest.

## Global Constraints

- Run everything through the host venv: `backend/.venv/bin/pytest`, `backend/.venv/bin/pyright`, `backend/.venv/bin/ruff check --no-cache .` (bare `pyright`, no path arg, is the gate).
- Tests run against `chili_test` — never export `DATABASE_URL` pointing at the dev `chili` DB.
- No `Any`, no private `_helper` imports in tests (pyright `reportPrivateUsage` covers tests).
- SHAP-dependent tests: `@pytest.mark.integration` + `pytest.importorskip`.
- Generator/attributor **never raise** — degrade + WARNING log (pipeline is best-effort).
- After Task 2 (contract change): from repo root `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`, then `cd chili_app && npm run codegen:api`, commit regenerated files with the task. Frontend must stay `npm run build`-green.
- Commit messages end with the `(B3)` suffix convention, e.g. `feat(analytics): ... (B3)`.
- Backend imports root at `backend/` (e.g. `from analytics.explainability.models import ...`).

---

### Task 1: Config surface — `narrative_backend` + `attribution_backend`

**Files:**
- Modify: `backend/config/schema.py` (AnalyticsConfig, ~line 200)
- Test: `backend/tests/config/test_schema.py` (append)

**Interfaces:**
- Produces: `AnalyticsConfig.narrative_backend: Literal["deterministic", "llm"]` (default `"deterministic"`), `AnalyticsConfig.attribution_backend: Literal["none", "shap"]` (default `"none"`). Tasks 7 reads both.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/config/test_schema.py`):

```python
class TestAnalyticsExplainabilityBackends:
    def test_defaults_are_deterministic_and_none(self) -> None:
        config = AnalyticsConfig()
        assert config.narrative_backend == "deterministic"
        assert config.attribution_backend == "none"

    def test_accepts_llm_and_shap(self) -> None:
        config = AnalyticsConfig(narrative_backend="llm", attribution_backend="shap")
        assert config.narrative_backend == "llm"
        assert config.attribution_backend == "shap"

    def test_rejects_unknown_backends(self) -> None:
        with pytest.raises(ValidationError):
            AnalyticsConfig(narrative_backend="template")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            AnalyticsConfig(attribution_backend="lime")  # type: ignore[arg-type]
```

(Reuse the file's existing `pytest`/`ValidationError`/`AnalyticsConfig` imports; add any missing ones.)

- [ ] **Step 2: Run to verify they fail** — `backend/.venv/bin/pytest tests/config/test_schema.py -q -k ExplainabilityBackends` from `backend/`; expect `ValidationError`-free construction failures ("unexpected keyword"/validation errors).
- [ ] **Step 3: Implement** — add to `AnalyticsConfig` (keep existing fields/validator untouched):

```python
    narrative_backend: Literal["deterministic", "llm"] = "deterministic"
    attribution_backend: Literal["none", "shap"] = "none"
```

(`Literal` is already imported in `config/schema.py`; verify.)
- [ ] **Step 4: Run to verify pass** — same command; then `backend/.venv/bin/pytest tests/config -q` (whole package still green).
- [ ] **Step 5: Commit** — `feat(config): narrative_backend + attribution_backend analytics fields (B3)`

---

### Task 2: Evidence-pack enrichment — shared types, API contract, mapper, contract regen

**Files:**
- Modify: `backend/shared/types.py` (EvidencePack at ~line 134; add two models above it)
- Modify: `backend/api/contracts.py` (EvidencePackResponse at ~line 199; add two response models above it)
- Modify: `backend/api/dependencies.py` (`_evidence_pack_to_response`, ~line 428)
- Modify (generated): `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`
- Test: `backend/tests/shared/test_types.py`, `backend/tests/api/test_evidence_routes.py` (append; if the api evidence tests live elsewhere, `grep -rn "get_evidence_pack_payload\|evidence-packs" backend/tests/api --include='*.py'` and append to that file)

**Interfaces:**
- Produces (shared/types.py):

```python
class FeatureAttribution(BaseModel):
    feature_name: str
    contribution: float
    rationale: str = ""

class EvidenceNarrativeSection(BaseModel):
    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
```

  and on `EvidencePack`: `attribution: list[FeatureAttribution] = Field(default_factory=list)`, `narrative_sections: list[EvidenceNarrativeSection] = Field(default_factory=list)`. Add both class names to `shared/types.py` `__all__` if one exists.
- Produces (api/contracts.py): `FeatureAttributionResponse` (same three fields, `contribution: float` unconstrained/signed) and `NarrativeSectionResponse` (heading/body/evidence_refs), plus on `EvidencePackResponse`: `attribution: list[FeatureAttributionResponse] = Field(default_factory=lambda: cast(list[FeatureAttributionResponse], []))` and `narrative_sections: list[NarrativeSectionResponse] = Field(default_factory=lambda: cast(list[NarrativeSectionResponse], []))` (match the file's `cast` default idiom).
- Tasks 6 (service) and U2 (frontend) rely on these exact field names.

- [ ] **Step 1: Write failing tests.** In `backend/tests/shared/test_types.py` append:

```python
class TestEvidencePackEnrichment:
    def test_defaults_empty_for_legacy_payloads(self) -> None:
        pack = EvidencePack(
            id="ep-1", alert_id="a-1", reasoning="r", subgraph_nodes=["n1"],
            subgraph_edges=[], confidence=0.5,
        )
        assert pack.attribution == []
        assert pack.narrative_sections == []

    def test_round_trips_attribution_and_sections(self) -> None:
        pack = EvidencePack(
            id="ep-1", alert_id="a-1", reasoning="r", subgraph_nodes=["n1"],
            subgraph_edges=[], confidence=0.5,
            attribution=[FeatureAttribution(feature_name="claim_volume_z", contribution=-0.12)],
            narrative_sections=[EvidenceNarrativeSection(heading="Risk Factor", body="b", evidence_refs=["e1"])],
        )
        restored = EvidencePack.model_validate(pack.model_dump())
        assert restored.attribution[0].feature_name == "claim_volume_z"
        assert restored.attribution[0].contribution == -0.12
        assert restored.narrative_sections[0].heading == "Risk Factor"
```

  In the api evidence test file, extend the existing pack-fetch test (or add one following its fixture idiom) asserting the response JSON now carries `attribution` and `narrative_sections` echoing a repository pack that has them, and that a legacy pack (fields absent) serves `[]` for both.
- [ ] **Step 2: Run to verify fail** — `backend/.venv/bin/pytest tests/shared/test_types.py -q -k Enrichment` (import error on `FeatureAttribution`).
- [ ] **Step 3: Implement** shared types + contracts + mapper passthrough (`attribution=[FeatureAttributionResponse(**a.model_dump()) for a in pack.attribution]`-style explicit mapping, matching the mapper's existing explicit style; same for sections).
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/shared tests/api -q`; then regen contracts (repo root): `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json && cd chili_app && npm run codegen:api && npm run build`. All green; `git status` shows only the two generated files changed beyond your edits.
- [ ] **Step 5: Commit** — `feat(shared,api): evidence packs carry narrative sections + feature attribution; contract regen (B3)`

---

### Task 3: Narrative seam — protocol + `DeterministicNarrativeGenerator` + service dispatch

**Files:**
- Modify: `backend/analytics/explainability/protocols.py`
- Create: `backend/analytics/explainability/adapters/deterministic.py`
- Modify: `backend/analytics/explainability/service.py`
- Test: create `backend/tests/analytics/explainability/test_deterministic_generator.py`; `backend/tests/analytics/explainability/test_service.py` must pass **unmodified** (behavior preservation gate)

**Interfaces:**
- Produces (`protocols.py`):

```python
class NarrativeGeneratorProtocol(Protocol):
    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative: ...
```

- Produces (`adapters/deterministic.py`): `class DeterministicNarrativeGenerator` implementing the protocol with today's exact `_build_narrative` semantics (group by `source_type` in first-seen order; body = space-joined rationales; heading = `source_type.replace("_", " ").strip().title()`; summary = space-joined rationales of ALL items in selection order).
- Produces (`service.py`): `ExplainabilityService.__init__(self, context_source, *, event_bus, narrative_generator: NarrativeGeneratorProtocol | None = None)`; `create_explainability_service` gains the same keyword. `generate_from_context` calls `self._narrative_generator.summarize(context=context, items=selected_items)`. Module-private `_build_narrative`/`_build_reasoning`/`_format_heading` move into the adapter (delete from service.py; nothing else imports them — verify with grep).
- Task 4 subclasses nothing — it implements the same protocol; Task 6 passes `narrative_generator` through `create_explainability_service`.

- [ ] **Step 1: Write failing tests** (`test_deterministic_generator.py`):

```python
from analytics.explainability.adapters.deterministic import DeterministicNarrativeGenerator
from analytics.explainability.models import (
    ExplanationContext, ExplanationItem, ExplanationSubgraph,
)
from shared.types import Alert
from datetime import datetime, timezone


def _context(items: list[ExplanationItem]) -> ExplanationContext:
    return ExplanationContext(
        knowledge_base_id="kb-1",
        alert=Alert(
            id="a-1", entity_type="provider", entity_id="p-1", severity="high",
            title="t", reasoning="r", created_at=datetime.now(tz=timezone.utc),
        ),
        explanation_items=items,
        subgraph=ExplanationSubgraph(node_ids=["p-1"]),
        confidence=0.8,
        scores={"overall": 0.8},
    )


def _item(source_type: str, rationale: str, score: float = 0.5) -> ExplanationItem:
    return ExplanationItem(
        source_id=f"src-{rationale}", source_type=source_type,
        quote="q", rationale=rationale, score=score,
    )


class TestDeterministicNarrativeGenerator:
    def test_groups_by_source_type_in_first_seen_order(self) -> None:
        items = [_item("risk_factor", "one"), _item("peer", "two"), _item("risk_factor", "three")]
        narrative = DeterministicNarrativeGenerator().summarize(context=_context(items), items=items)
        assert [s.heading for s in narrative.sections] == ["Risk Factor", "Peer"]
        assert narrative.sections[0].body == "one three"
        assert narrative.sections[0].evidence_refs == ["src-one", "src-three"]

    def test_summary_is_space_joined_rationales(self) -> None:
        items = [_item("risk_factor", "one"), _item("peer", "two")]
        narrative = DeterministicNarrativeGenerator().summarize(context=_context(items), items=items)
        assert narrative.summary == "one two"
```

- [ ] **Step 2: Run to verify fail** — `backend/.venv/bin/pytest tests/analytics/explainability/test_deterministic_generator.py -q` (ModuleNotFoundError).
- [ ] **Step 3: Implement** adapter + protocol + service dispatch. `Sequence` from `collections.abc`; keep the service's selection (`_select_items`) where it is.
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/analytics/explainability -q` — **including `test_service.py` untouched** (if any service test fails, the extraction changed behavior: fix the adapter, not the test).
- [ ] **Step 5: Commit** — `refactor(analytics): narrative generation behind NarrativeGeneratorProtocol; deterministic adapter (B3)`

---

### Task 4: `LlmNarrativeGenerator`

**Files:**
- Create: `backend/analytics/explainability/adapters/llm_narrative.py`
- Test: create `backend/tests/analytics/explainability/test_llm_narrative_generator.py`

**Interfaces:**
- Consumes: `NarrativeGeneratorProtocol`, `DeterministicNarrativeGenerator` (Task 3); `llm.protocols.LlmServiceProtocol`, `llm.service_models.GenerateRequest/PromptTemplate/CompletionResponse`; `llm.exceptions.LlmError` (verify the base class name in `backend/llm/exceptions.py` — use the module's actual base error).
- Produces:

```python
class LlmNarrativeGenerator:
    def __init__(
        self,
        llm_service: LlmServiceProtocol,
        *,
        fallback: NarrativeGeneratorProtocol,
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> None: ...
    def summarize(self, *, context, items) -> ExplanationNarrative: ...
```

  Task 7 constructs it with values from `DomainConfig.llm` (`config.llm.model`, `temperature`, `max_tokens`, defaulting via `LlmConfig()` when `config.llm is None`).

**Behavior contract (encode in tests):**
1. Builds `GenerateRequest(knowledge_base_id=context.knowledge_base_id, model_name=..., temperature=..., max_tokens=..., messages=[], prompt_template=PromptTemplate(system_prompt=<analyst instruction>, user_prompt=<rendered evidence block>))`. The user prompt must contain, for every item: `source_id`, `quote`, `rationale`, and `score` formatted to two decimals; plus the alert title and the `context.scores` snapshot. System prompt instructs: markdown output, `## `-headed sections, ground every claim in the listed evidence, open with a 1–3 sentence summary paragraph before the first heading, no fabricated identifiers.
2. Parses the completion: text before the first `## ` (stripped) → `summary`; each `## Heading\nbody...` block → `NarrativeSection(heading=<heading text stripped>, body=<block body stripped, newlines collapsed to spaces>, evidence_refs=<source_ids of items whose source_id or quote appears verbatim in the block, else all selected item ids>)`.
3. No `## ` headings at all → `ExplanationNarrative(summary=<whole completion stripped>, sections=[])` — still LLM-authored, acceptable.
4. Degrades to `fallback.summarize(...)` (WARNING log via module `logging.getLogger(__name__)`) when: the service raises the llm base error, raises any unexpected exception, or the completion strips to `""`.
5. Never raises.

- [ ] **Step 1: Write failing tests** — stub service:

```python
class _StubLlmService:
    def __init__(self, completion: str | None = None, error: Exception | None = None) -> None:
        self._completion = completion
        self._error = error
        self.requests: list[GenerateRequest] = []

    def generate(self, request: GenerateRequest) -> CompletionResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._completion is not None
        return CompletionResponse(
            request_id="req-1", completion=self._completion,
            provider="stub", model_name=request.model_name,
        )

    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""
```

  Tests: structured completion (`"Summary line.\n\n## Billing Pattern\nDetail about src-one.\n\n## Network\nOther."`) → summary `"Summary line."`, two sections, first section's `evidence_refs == ["src-one"]` when an item has `source_id="src-one"` and its id appears in the block; heading-less completion → summary-only narrative; provider error → fallback narrative (equals `DeterministicNarrativeGenerator` output); empty completion → fallback; prompt content includes item rationale + `0.50`-formatted score + alert title; generator sends `model_name`/`temperature`/`max_tokens` it was constructed with.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** (`re` for heading split: `re.split(r"^## ", text, flags=re.MULTILINE)`).
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/analytics/explainability -q`.
- [ ] **Step 5: Commit** — `feat(analytics): LLM narrative generator with deterministic fallback (B3)`

---

### Task 5: Attribution seam — protocol + `NoopFeatureAttributor` + `ShapRiskAttributor`

**Files:**
- Modify: `backend/analytics/explainability/protocols.py` (add `FeatureAttributorProtocol`)
- Create: `backend/analytics/explainability/adapters/shap_attribution.py` (both attributors live here)
- Test: create `backend/tests/analytics/explainability/test_shap_attribution.py`

**Interfaces:**
- Produces (`protocols.py`):

```python
class FeatureAttributorProtocol(Protocol):
    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]: ...
```

  (`FeatureAttribution` from `shared.types`, Task 2.)
- Produces (`shap_attribution.py`): `class NoopFeatureAttributor` (returns `[]`); `class ShapRiskAttributor` with public `__init__(self) -> None` and the behavior below. Task 7 constructs both by config.

**Behavior contract:**
1. Features: pairs from `context.scores` excluding key `"overall"`, ordered by key for determinism → vector `x` of contributions.
2. No features → `[]` (WARNING).
3. Model: `predict(X) = numpy.minimum(1.0, X.sum(axis=1))` — the `LinearScoringStrategy` composite in contribution space. Background/baseline: single zero row. Run `shap.Explainer(predict, background)(x_row)`; per-feature SHAP values → `FeatureAttribution(feature_name=key, contribution=float(value), rationale=f"SHAP attribution of the linear risk composite for {key}.")`, sorted by `abs(contribution)` descending.
4. `shap`/`numpy` import failure (lazy import inside `attribute`), or any exception from the explainer → `[]` + WARNING. Never raises.
5. Unit tests monkeypatch the module's loader seam so they run without the `[analytics]` extra: expose the lazy import as a module-level function `def _load_shap_and_numpy() -> tuple[ModuleType, ModuleType]` and monkeypatch **via the public class hook** `ShapRiskAttributor(loader=...)` — add an optional `loader: Callable[[], tuple[ModuleType, ModuleType]] | None = None` init parameter so tests never touch privates (pyright `reportPrivateUsage` covers tests).
6. Integration test (`@pytest.mark.integration`, `pytest.importorskip("shap")`, `pytest.importorskip("numpy")`): for `scores={"a": 0.3, "b": 0.2, "overall": 0.5}` the SHAP attributions sum to `predict(x) - predict(0) = 0.5` within `1e-3`, and each `contribution` is positive.

- [ ] **Step 1: Write failing tests** — unit: no-features degrade; loader-raises degrade (fake loader raising ImportError); happy path with a **fake shap module** (loader returns a stub whose `Explainer(fn, bg)` returns an object whose `__call__(X).values` is a numpy-like nested list — use plain lists + a tiny fake to avoid numpy in unit scope); sorted-by-magnitude assertion; plus the integration test above.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/analytics/explainability -q` and, extras installed, `backend/.venv/bin/pytest tests/analytics/explainability/test_shap_attribution.py -q -m integration`.
- [ ] **Step 5: Commit** — `feat(analytics): SHAP feature attributor over the linear risk composite (B3)`

---

### Task 6: Service composition — packs carry narrative sections + attribution

**Files:**
- Modify: `backend/analytics/explainability/service.py`
- Test: append to `backend/tests/analytics/explainability/test_service.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: `ExplainabilityService.__init__(self, context_source, *, event_bus, narrative_generator=None, feature_attributor: FeatureAttributorProtocol | None = None)`; `create_explainability_service` mirrors both keywords. `generate_from_context` now: `narrative = generator.summarize(...)`; `attribution = attributor.attribute(context=context)` (Noop default when None); pack fields `reasoning=narrative.summary`, `narrative_sections=[EvidenceNarrativeSection(heading=s.heading, body=s.body, evidence_refs=list(s.evidence_refs)) for s in narrative.sections]`, `attribution=attribution`.

- [ ] **Step 1: Write failing tests** — with stub generator (fixed 2-section narrative) and stub attributor (one `FeatureAttribution`): pack carries both, `reasoning == narrative.summary`; default construction (no kwargs) keeps legacy behavior (existing tests already pin it) and `pack.attribution == []`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/analytics/explainability -q`.
- [ ] **Step 5: Commit** — `feat(analytics): evidence packs compose injected narrative + attribution (B3)`

---

### Task 7: Worker wiring + domain packs

**Files:**
- Modify: `backend/agent/coordinator.py` (builders near `build_explainability_context_source` ~line 663; assembly site ~line 1091)
- Modify: `backend/config/defaults/medicare_fraud.yaml` (or the CMS pack actually carrying the `analytics:`/`capabilities:` blocks — `grep -l "peer_stats" backend/config/defaults/*.yaml` and edit those same packs), `backend/config/defaults/af_housing.yaml` (same check)
- Test: append to `backend/tests/agent/test_coordinator.py` (or the coordinator-wiring test file — `grep -rn "build_explainability_context_source" backend/tests` and co-locate), plus the pack-validation test file that loads default YAMLs (`grep -rn "defaults" backend/tests/config --include='*.py'`)

**Interfaces:**
- Consumes: Tasks 1, 3–6; `create_llm_service` from `llm.service`; worker `llm_client` + `event_bus` already in scope at the assembly site.
- Produces:

```python
def build_narrative_generator(
    config: DomainConfig, llm_client: LlmClientProtocol, *, event_bus: EventBus
) -> NarrativeGeneratorProtocol: ...
def build_feature_attributor(config: DomainConfig) -> FeatureAttributorProtocol: ...
```

  `build_narrative_generator`: `"llm"` → `LlmNarrativeGenerator(create_llm_service(llm_client, event_bus=event_bus), fallback=DeterministicNarrativeGenerator(), model_name=llm_config.model, temperature=llm_config.temperature, max_tokens=llm_config.max_tokens)` where `llm_config = config.llm or LlmConfig()`; else `DeterministicNarrativeGenerator()`. `build_feature_attributor`: `"shap"` → `ShapRiskAttributor()`; else `NoopFeatureAttributor()`. Both threaded into `create_explainability_service(...)` at the assembly site.

- [ ] **Step 1: Write failing tests** — builder dispatch by config value (construct minimal `DomainConfig` fixtures as the existing coordinator tests do); pack YAML test: loading each default pack still validates and the CMS + housing packs expose `narrative_backend == "llm"`, `attribution_backend == "shap"`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** builders, assembly threading, and YAML edits (`analytics:` blocks gain the two keys in CMS + housing packs only).
- [ ] **Step 4: Run to verify pass** — `backend/.venv/bin/pytest tests/agent tests/config -q`.
- [ ] **Step 5: Commit** — `feat(agent,config): explainability narrative/attribution backends wired from domain config (B3)`

---

### Task 8: Full gates, docs, backlog reconciliation

**Files:**
- Modify: `backend/analytics/explainability/` module docs/README if present (`ls backend/analytics/explainability/README.md`), `backend/README.md` (Current State explainability line), `docs/wiki/modules/` explainability/agent pages (grep for stale claims), `docs/backlog/analytics.md` (analytics.13 → done sprint-slice; analytics.14 → in_progress with delivered/remaining noted; fix its stale "(new) test_shap_adapter.py" claim; note analytics.17's stale migration filename), `docs/backlog/README.md` (regenerate rollup if the repo has a generator — check `scripts/` for the backlog tool; else hand-edit counts), `docs/project/planning/backlog.md` BL-048 row, `docs/project/planning/sprints/2026-28.md` progress entry.

- [ ] **Step 1:** Full gates from `backend/`: `backend/.venv/bin/pytest --cov` (≥85%, all green), `backend/.venv/bin/pyright` (0 errors), `backend/.venv/bin/ruff check --no-cache .`; repo root: OpenAPI export + `npm run codegen:api` (no drift) + `cd chili_app && npm run build && npm run lint`.
- [ ] **Step 2:** `backend/.venv/bin/python scripts/backlog_consistency.py` (repo root) green after backlog edits.
- [ ] **Step 3:** Docs edits above; verify no other README/instruction file mentions the old narrative joiner as current behavior (`grep -rn "space-join\|template joining" docs/ backend/README.md`).
- [ ] **Step 4: Commit** — `docs(analytics,backlog,sprints): B3 explainability closeout reconciliation (B3)`

---

### Task 9: Live verification — RESERVED FOR THE CONTROLLER

Run in the main session (Docker stays out of subagents): `make dev`; ingest/reuse the TN 1% CMS KB; confirm worker logs show the LLM narrative path (or clean WARNING degrade with the local provider) and SHAP attribution rows on new packs; `GET /evidence-packs/{id}?knowledge_base_id=...` returns non-empty `narrative_sections` and `attribution` for a fresh alert; workbench evidence viewer renders unchanged (new fields unused pre-U2); KB-delete cascade still purges packs.
