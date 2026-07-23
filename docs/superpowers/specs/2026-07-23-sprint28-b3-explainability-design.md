# Sprint 2026-28 B3 — Explainability Engine: LLM Narratives + Production SHAP (Design)

> Story: **BL-048 (B3)** · backlog slices: analytics.13 (LLM narrative), analytics.14 (SHAP wiring) · 5 SP
> Depends on: B2 merged (`feat/sprint-2026-28-b2-timeseries-anomalies` → prod)
> Authored 2026-07-23 against the approved sprint design note
> `docs/superpowers/specs/2026-07-16-sprint28-cms-fraud-workbench-design.md` §3.1 B3.

## 1. Current state (code-verified 2026-07-23)

- `ExplainabilityService.generate_from_context` (`backend/analytics/explainability/service.py:55`) builds the
  evidence pack from an `ExplanationContext`; the narrative is module-private `_build_narrative` — items grouped
  by `source_type`, bodies space-joined (`service.py:143-165`); `reasoning` = `_build_reasoning` space-join
  (`service.py:132-140`). The `TODO(production)` block at `service.py:31-34` is exactly this story.
- A **real SHAP adapter exists but is unwired**: `ShapExplainabilityContextSource`
  (`adapters/shap_adapter.py`) lazily imports `shap`, explains a model callable, and maps mean-|SHAP| to
  `ExplanationItem`s. It is keyed by preloaded `ShapAlertInput`s and is **not** reachable from the worker
  pipeline: `build_explainability_context_source` (`agent/coordinator.py:663-668`) ignores config and always
  returns `InMemoryExplainabilityContextSource`, and the pipeline bypasses context sources entirely via
  `build_explanation_context` (`coordinator.py:2337`).
- The worker explainability stage (`_run_explainability_stage`, `coordinator.py:2278`) runs after risk in
  Flow B, builds context from `graph.get_subgraph()` + risk factors, persists the pack best-effort, and emits
  the alert reference. Everything in the path is **synchronous** (`LlmService.generate` is sync too,
  `llm/service.py:30`).
- The **persisted** `EvidencePack` (`shared/types.py:134-148`) carries only `reasoning` (a string), subgraph
  ids, confidence, scores. The structured `ExplanationNarrative` and the evidence items exist only on the
  worker-side `ExplainabilityResponse` and are **discarded**; the API mapper
  (`api/dependencies.py:428-443`) serves `items`/`policy_citations` as empty. U2's "SHAP bars + LLM narrative
  in evidence viewer" therefore requires persisting both on the pack.
- Risk scoring is the heuristic `LinearScoringStrategy` (`analytics/risk/adapters/linear_strategy.py`):
  `contribution = min(1.0, value*weight/total_weight)`, `overall = min(1.0, Σ)` over the entity's
  `entity_derived_signals` rows (peerstats z-scores + B2 `timeseries_anomaly:*` signals). There is no trained
  model in the risk path; "production SHAP" attributes **this** scorer (the trained GNN later via the same
  seam, per the owner ruling).
- `AnalyticsConfig` (`config/schema.py:200-213`) has no narrative/attribution fields;
  `CapabilitiesConfig.explainability` exists (`schema.py:56`) but nothing reads it.
- `shap>=0.43` + `scikit-learn` + `numpy` ship in the optional `[analytics]` extra
  (`backend/pyproject.toml:60-66`); SHAP tests must stay `@pytest.mark.integration`-gated. LIME is not a
  dependency.

## 2. Rulings applied (from the approved sprint design, owner Q&A 2026-07-16)

1. **LLM narratives with template fallback** — LLM-generated evidence narratives; degrade to the current
   deterministic joiner when no LLM is configured, the call fails, or the output is unusable.
2. **Production SHAP now attributes `LinearScoringStrategy`** over the entity's `entity_derived_signals`
   feature vector; a trained GNN attributes through the same seam later (S1/BL-030). SHAP failure degrades to
   factor-only packs — never breaks the pipeline.
3. **Attribution becomes a first-class evidence-pack section** consumed by U2 (SHAP bars) and D1 (demo).
4. **Sprint-scoped slices of analytics.13/.14** (recorded for closeout reconciliation): analytics.13 is
   delivered without its analytics.16 composite-context prereq (the pipeline context is already real:
   subgraph + risk factors); analytics.14 is delivered as the *pipeline attributor* seam — the
   context-source DI literal (`in_memory|shap|lime`) and the LIME adapter are **not** built (LIME has no
   dependency and no sprint AC). The backlog stories get status/current-state updates at closeout, not
   silent closure.

## 3. Design

### 3.1 Config surface (new fields on `AnalyticsConfig`, `config/schema.py`)

```python
narrative_backend: Literal["deterministic", "llm"] = "deterministic"
attribution_backend: Literal["none", "shap"] = "none"
```

No cross-validation needed (both are self-contained). Domain packs: the CMS medicare pack and the housing
pack set `narrative_backend: llm` and `attribution_backend: shap` (the LLM path self-degrades when the
configured provider is `local`/unreachable; SHAP self-degrades when the `[analytics]` extra is absent —
worker images install it).

### 3.2 Narrative generation seam (analytics.13 slice)

New protocol in `analytics/explainability/protocols.py`:

```python
class NarrativeGeneratorProtocol(Protocol):
    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative: ...
```

- `DeterministicNarrativeGenerator` (`adapters/deterministic.py`) — extraction of today's
  `_build_narrative`/`_build_reasoning`/`_format_heading` (behavior-preserving; the service's module-private
  helpers move here and the old names keep thin delegating wrappers only if tests import them — they do not;
  tests exercise the service surface).
- `LlmNarrativeGenerator` (`adapters/llm_narrative.py`) — wraps `LlmServiceProtocol` (mirrors the RAG
  answer-generator pattern, `api/dependencies.py:1819-1827`): builds a `GenerateRequest` with a
  `PromptTemplate` (system prompt: fraud-analyst evidence narrator, grounded-in-items instruction; user
  prompt: alert headline, per-item `source_id`/`quote`/`rationale`/`score` lines, subgraph node/edge counts,
  score snapshot), `model_name`/`temperature`/`max_tokens` from `DomainConfig.llm`. Response parsing:
  markdown `## ` headings → `NarrativeSection`s (evidence_refs = the source_ids whose quote/rationale text
  appears in the section body; fallback: all selected ids); text before the first heading (or the whole
  completion when headings are absent) → `summary`. **Degrade rule:** on `LlmError`/empty completion/blank
  summary → return `self._fallback.summarize(...)` (an injected `DeterministicNarrativeGenerator`) and log
  at WARNING. Never raises.
- `ExplainabilityService.__init__` gains `narrative_generator: NarrativeGeneratorProtocol | None = None`
  (None → deterministic); `generate_from_context` dispatches through it.

### 3.3 Attribution seam (analytics.14 slice)

New protocol in `analytics/explainability/protocols.py`:

```python
class FeatureAttributorProtocol(Protocol):
    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]: ...
```

`ShapRiskAttributor` (`adapters/shap_attribution.py`):

- Input features are the risk-factor entries already snapshotted in `context.scores` (every key except
  `"overall"`), i.e. the `LinearScoringStrategy` contributions keyed by signal name, with the raw item
  scores from `context.explanation_items` (`source_type == "risk_factor"`). The attributor reconstructs the
  linear model surface as `predict(X) = min(1.0, Σ x_i)` over the per-feature contribution vector and runs
  `shap.Explainer` against a zero-baseline background (contribution space: 0 = signal absent). For this
  model SHAP values are exact per-feature marginal contributions — which is the point: the seam is real SHAP
  end-to-end so a trained model drops in later unchanged.
- Reuses `shap_adapter.py`'s lazy-import helper (promoted to a shared module-internal function if needed —
  no private cross-imports in tests).
- Output: `FeatureAttribution(feature_name, contribution, rationale)` sorted by |contribution| desc.
- **Degrade rule:** missing `shap`/numpy, no risk-factor items, or any exception → return `[]` and log at
  WARNING (factor-only pack). Never raises.
- `NoopFeatureAttributor` for `attribution_backend: none` (returns `[]`).

### 3.4 Evidence pack enrichment (shared types + API contract)

`shared/types.py` (generic platform types — both additions are domain-agnostic):

```python
class FeatureAttribution(BaseModel):
    feature_name: str
    contribution: float          # signed, model-space
    rationale: str = ""

class EvidenceNarrativeSection(BaseModel):
    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
```

`EvidencePack` gains `attribution: list[FeatureAttribution] = Field(default_factory=list)` and
`narrative_sections: list[EvidenceNarrativeSection] = Field(default_factory=list)` — optional-with-default,
so previously persisted object-store packs deserialize unchanged.

`EvidencePackResponse` (`api/contracts.py:199`) gains matching `attribution` + `narrative_sections` response
models; `_evidence_pack_to_response` (`api/dependencies.py:428`) passes them through. OpenAPI export +
`npm run codegen:api` regeneration is part of the story (CI contract-drift gate); U2 consumes the new fields.

`ExplainabilityService.generate_from_context` populates: `reasoning` = narrative.summary (LLM lead when the
LLM backend is active), `narrative_sections` from `ExplanationNarrative.sections`, `attribution` from the
attributor.

### 3.5 Worker wiring (`agent/coordinator.py`)

- `build_narrative_generator(config, llm_client)` → `LlmNarrativeGenerator(create_llm_service(llm_client,
  event_bus=...), fallback=DeterministicNarrativeGenerator(), llm_config=config.llm)` when
  `config.analytics.narrative_backend == "llm"`, else `DeterministicNarrativeGenerator()`.
- `build_feature_attributor(config)` → `ShapRiskAttributor()` when
  `config.analytics.attribution_backend == "shap"`, else `NoopFeatureAttributor()`.
- Both passed to `create_explainability_service(...)` at the existing assembly site
  (`coordinator.py:1091-1092`). `_run_explainability_stage` is otherwise unchanged (the service owns
  narrative + attribution composition). The stage keeps its existing error contract: generator/attributor
  never raise, so no new failure paths join `_publish_analysis_failed`.
- `capabilities.explainability` remains unread this sprint (the stage predates the flag and D1's demo packs
  enable it descriptively); recorded in backlog reconciliation rather than silently coupling Flow B to a
  flag no pack sets today.

### 3.6 No migration

Attribution + narrative sections embed in the object-store-persisted pack; no new table, no Alembic change.

## 4. Error handling

| Failure | Behavior |
|---|---|
| LLM misconfigured / provider error / empty or blank completion | WARNING log; deterministic narrative (pack still ships) |
| `shap` extra missing / no risk-factor items / attributor exception | WARNING log; `attribution=[]` (factor-only pack) |
| Both degrade | Pack identical to today's output plus empty new fields |
| Old persisted packs | Deserialize with default empty `attribution`/`narrative_sections` |

## 5. Out of scope

- LIME / permutation-importance adapters (no dependency, no sprint AC) — analytics.14 tail.
- `/analytics/explainability/{alert_id}` API route + `get_explainability_service` DI (analytics.15).
- Composite graph+RAG+risk context assembler (analytics.16).
- Trained-model attribution (S1/BL-030 — same seam, later).
- Any frontend rendering (U2 consumes the regenerated contract).

## 6. Testing & verification

- Unit: config fields; deterministic generator behavior-preservation (existing service tests keep passing
  unmodified); LLM generator (stub `LlmServiceProtocol`: structured completion → sections; error/empty →
  fallback; heading-less → single-summary narrative); SHAP attributor with monkeypatched loader (missing-shap
  degrade, exception degrade, sorted signed output); Noop attributor; service composition (pack carries
  sections + attribution; reasoning = summary); mapper passthrough; worker builders keyed by config.
- Integration (`-m integration`, `[analytics]` extra): real-SHAP attribution of a linear scorer — exact
  marginal contributions within tolerance.
- Gates: bare `pyright` 0 errors, `ruff check --no-cache .` clean, `pytest --cov` ≥85%, OpenAPI export +
  `npm run codegen:api` no-drift, `npm run build` green.
- Live (Task 9, controller): `make dev` + TN 1% CMS KB — worker logs show llm/shap backends active (or
  clean degrades), persisted packs carry narrative sections + attribution via
  `GET /evidence-packs/{id}`, workbench evidence viewer still renders (pre-U2 fields simply unused).

## 7. Backlog reconciliation at closeout

- analytics.13 → done (sprint-scoped slice): protocol + LLM/deterministic generators + config dispatch
  delivered; note analytics.16-composite-context non-dependency rationale.
- analytics.14 → in_progress/partial: SHAP wired via the pipeline attributor seam + config field;
  context-source DI literal and LIME adapter remain; correct its stale "(new) test_shap_adapter.py" claim
  (file already exists, 15 tests).
- analytics.17's stale `0002_evidence_pack_history.py` example noted (head is 0011; B3 adds no migration).
- Sprint doc + `docs/project/planning/backlog.md` BL-048 row updated.
