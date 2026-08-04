# SAFE-CMS-013 Versioned Fraud Playbooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add domain-pack-authored, DB-published, versioned fraud playbooks that can guide alerts, evidence, cases, and the PI 4 workflow runway without hardcoding CMS behavior in shared code.

**Architecture:** Add a domain-neutral playbook catalog to `DomainConfig`, validate references to typologies/features/policies, then publish immutable snapshots into Postgres by domain name and version. Use KB-scoped APIs for access control while storing historical playbook refs on generated alerts/evidence metadata and first-class case snapshots. The first frontend slice renders compact badges/details and a management surface for list, publish, import, and export.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Alembic/Postgres JSONB, React/TypeScript, React Query, OpenAPI codegen, Vitest.

---

## Source Documents

- Surge source: `docs/superpowers/plans/2026-07-30-cms-fraud-ai-safe-agile-20-sprint-surge.md`
- PI 4 ADR: `docs/superpowers/specs/2026-08-04-safe-cms-pi4-playbooks-workflows-adr.md`
- Prior dependency: `docs/superpowers/plans/2026-08-03-safe-cms-012-identity-resolution.md`
- Backlog row: `docs/project/planning/backlog.md`

## File Structure

- `backend/config/schema.py` - Add config-authored playbook schema and cross-reference validation.
- `backend/config/defaults/medicare_fraud.yaml` - Seed CMS playbooks and connect typology `playbook_ids`.
- `backend/tests/config/test_schema.py` - Schema validation and negative reference tests.
- `backend/tests/config/test_loader.py` - Medicare pack seed coverage.
- `backend/playbooks/models.py` - Domain-neutral playbook runtime and persistence models.
- `backend/playbooks/repository.py` - Repository protocol and page type.
- `backend/playbooks/service.py` - Publication, lookup, export, and import logic.
- `backend/playbooks/adapters/in_memory.py` - Local/test repository.
- `backend/playbooks/adapters/postgres.py` - Postgres repository.
- `backend/database/migrations/versions/0019_fraud_playbooks.py` - Snapshot table and case `playbook_ref`.
- `backend/database/migrations/snapshots/head.sql` - Refreshed migration snapshot.
- `backend/tests/playbooks/` - Unit and adapter tests.
- `backend/tests/database/test_fraud_playbooks_migration.py` - Migration assertions.
- `backend/api/contracts.py` - Request/response contracts.
- `backend/api/dependencies.py` - Playbook repository/service dependencies.
- `backend/api/routers/playbooks.py` - KB-scoped playbook API.
- `backend/api/app.py` - Router registration.
- `backend/tests/api/test_playbooks_router.py` - Route, auth, RBAC, and export/import tests.
- `backend/cases/models.py` and case adapters/routers/tests - Persist and expose case playbook snapshots.
- `backend/monitoring/models.py` and alert history adapters/tests - Preserve alert playbook refs through `generation_metadata`.
- `backend/analytics/explainability/models.py` and evidence tests - Preserve playbook refs through lineage/provenance metadata.
- `chili_app/src/api/playbooks.ts` - Frontend API client and hooks.
- `chili_app/src/api/contracts.ts` - Frontend contract aliases.
- `chili_app/src/components/playbooks/PlaybookBadge.tsx` - Compact status/version badge.
- `chili_app/src/components/playbooks/PlaybookDetailPanel.tsx` - Detail renderer.
- `chili_app/src/pages/PlaybookManagerPage.tsx` - Management surface if no existing admin page can host it cleanly.
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` and `CaseManagementPage.tsx` - First badge/detail placements.
- `chili_app/src/**/__tests__/*playbook*.test.tsx` - Focused frontend tests.
- `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` - Regenerated contracts.
- `docs/project/planning/backlog.md` - Closeout status update only after all acceptance criteria pass.

---

## Task 1: Domain Config Playbook Catalog

**Files:**
- Modify: `backend/config/schema.py`
- Modify: `backend/config/defaults/medicare_fraud.yaml`
- Modify: `backend/tests/config/test_schema.py`
- Modify: `backend/tests/config/test_loader.py`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [x] **Step 1: Write failing schema tests**

Add these tests to `backend/tests/config/test_schema.py`:

```python
def test_playbooks_and_typology_refs_round_trip() -> None:
    payload = _minimal_domain_payload()
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing Spike",
            "entity_types": ["provider"],
            "feature_ids": ["billing_outlier"],
            "policy_rule_ids": [],
            "playbook_ids": ["provider_billing_spike_review"],
        }
    ]
    payload["feature_catalog"] = {
        "version": "cms-features-v1",
        "features": [
            {
                "id": "billing_outlier",
                "label": "Billing outlier",
                "entity_types": ["provider"],
                "typology_ids": ["billing_spike"],
            }
        ],
    }
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [
            {
                "id": "provider_billing_spike_review",
                "version": "v1",
                "title": "Provider billing spike review",
                "summary": "Review a provider whose billing pattern moved outside baseline.",
                "status": "draft",
                "typology_ids": ["billing_spike"],
                "feature_ids": ["billing_outlier"],
                "policy_rule_ids": [],
                "evidence_requirements": [
                    {
                        "id": "billing_trend",
                        "label": "Billing trend",
                        "description": "Compare current billing to historical and peer baselines.",
                        "source_types": ["risk_projection", "timeseries"],
                        "required": True,
                    }
                ],
                "workflow_steps": [
                    {
                        "id": "review_risk",
                        "label": "Review risk projection",
                        "capability_ref": "analytics.risk_projection.read",
                        "input_refs": ["entity_id", "knowledge_base_id"],
                        "output_refs": ["risk_summary"],
                        "requires_human_approval": False,
                    }
                ],
                "rag_prompts": [
                    {
                        "id": "billing_context",
                        "model_ref": "default",
                        "prompt_version": "v1",
                        "system_prompt": "Answer with cited evidence only.",
                        "user_prompt": "Summarize the billing spike evidence for {entity_id}.",
                    }
                ],
                "decision_guidance": ["Open a case when billing spike evidence is corroborated."],
                "export_tags": ["cms", "billing"],
            }
        ],
    }

    config = DomainConfig(**payload)

    assert config.playbooks.version == "cms-playbooks-v1"
    playbook = config.playbooks.items[0]
    assert playbook.id == "provider_billing_spike_review"
    assert playbook.evidence_requirements[0].source_types == ["risk_projection", "timeseries"]
    assert config.typologies[0].playbook_ids == ["provider_billing_spike_review"]


def test_typology_rejects_unknown_playbook_reference() -> None:
    payload = _minimal_domain_payload()
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing Spike",
            "entity_types": ["provider"],
            "feature_ids": [],
            "policy_rule_ids": [],
            "playbook_ids": ["missing_playbook"],
        }
    ]

    with pytest.raises(ValueError, match="unknown playbook_id 'missing_playbook'"):
        DomainConfig(**payload)


def test_playbook_rejects_unknown_references() -> None:
    payload = _minimal_domain_payload()
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [
            {
                "id": "bad_review",
                "version": "v1",
                "title": "Bad Review",
                "summary": "Bad refs",
                "typology_ids": ["missing_typology"],
                "feature_ids": ["missing_feature"],
                "policy_rule_ids": ["missing_pack.missing_rule"],
                "evidence_requirements": [],
                "workflow_steps": [],
                "rag_prompts": [],
                "decision_guidance": [],
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        DomainConfig(**payload)

    message = str(exc_info.value)
    assert "Playbook 'bad_review' references unknown typology_id 'missing_typology'" in message
    assert "Playbook 'bad_review' references unknown feature_id 'missing_feature'" in message
    assert "Playbook 'bad_review' references unknown policy_rule_id 'missing_pack.missing_rule'" in message
```

Add this test to `backend/tests/config/test_loader.py`:

```python
def test_medicare_fraud_pack_declares_seed_playbooks() -> None:
    cfg = load_config(DEFAULTS_DIR / "medicare_fraud.yaml")

    playbook_ids = {playbook.id for playbook in cfg.playbooks.items}
    assert playbook_ids >= {
        "provider_billing_spike_review",
        "peer_outlier_provider_review",
        "identity_mismatch_review",
    }
    referenced = {
        playbook_id
        for typology in cfg.typologies
        for playbook_id in typology.playbook_ids
    }
    assert referenced <= playbook_ids
```

- [x] **Step 2: Run schema tests to verify RED**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml \
  backend/.venv/bin/python -m pytest \
  backend/tests/config/test_schema.py::test_playbooks_and_typology_refs_round_trip \
  backend/tests/config/test_schema.py::test_typology_rejects_unknown_playbook_reference \
  backend/tests/config/test_schema.py::test_playbook_rejects_unknown_references \
  backend/tests/config/test_loader.py::test_medicare_fraud_pack_declares_seed_playbooks -q
```

Expected: FAIL because `DomainConfig` has no `playbooks` field and no playbook reference validation.

- [x] **Step 3: Add schema models**

Add these classes before `DomainConfig` in `backend/config/schema.py`:

```python
PlaybookStatusConfigValue = Literal["draft", "published", "retired"]


class PlaybookEvidenceRequirementConfig(BaseModel):
    """One evidence item a playbook expects before a decision."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    source_types: list[str] = Field(default_factory=list)
    required: bool = True


class PlaybookWorkflowStepConfig(BaseModel):
    """Data-only workflow template step consumed by SAFE-CMS-014."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class PlaybookRagPromptConfig(BaseModel):
    """Prompt template metadata tied to a fraud playbook."""

    id: str = Field(min_length=1)
    model_ref: str = Field(default="default", min_length=1)
    prompt_version: str = Field(default="v1", min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)


class FraudPlaybookConfig(BaseModel):
    """A versioned fraud investigation playbook authored in a domain pack."""

    id: str = Field(min_length=1)
    version: str = Field(default="v1", min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    status: PlaybookStatusConfigValue = "draft"
    typology_ids: list[str] = Field(default_factory=list)
    feature_ids: list[str] = Field(default_factory=list)
    policy_rule_ids: list[str] = Field(default_factory=list)
    evidence_requirements: list[PlaybookEvidenceRequirementConfig] = Field(default_factory=list)
    workflow_steps: list[PlaybookWorkflowStepConfig] = Field(default_factory=list)
    rag_prompts: list[PlaybookRagPromptConfig] = Field(default_factory=list)
    decision_guidance: list[str] = Field(default_factory=list)
    export_tags: list[str] = Field(default_factory=list)


class FraudPlaybookCatalogConfig(BaseModel):
    """Versioned collection of domain-pack-authored fraud playbooks."""

    version: str = Field(default="v1", min_length=1)
    items: list[FraudPlaybookConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_playbook_versions(self) -> FraudPlaybookCatalogConfig:
        pairs = [(item.id, item.version) for item in self.items]
        if len(set(pairs)) != len(pairs):
            raise ValueError("FraudPlaybookCatalogConfig playbook id/version pairs must be unique.")
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("FraudPlaybookCatalogConfig playbook ids must be unique per catalog.")
        return self
```

Add this field to `DomainConfig`:

```python
playbooks: FraudPlaybookCatalogConfig = Field(default_factory=FraudPlaybookCatalogConfig)
```

- [x] **Step 4: Add cross-reference validation**

Extend `DomainConfig._validate_cross_references` after `policy_rule_ids` is built:

```python
playbook_ids = {playbook.id for playbook in self.playbooks.items}
```

Add this validation loop after feature and typology validation:

```python
for playbook in self.playbooks.items:
    for typology_id in playbook.typology_ids:
        if typology_id not in typology_ids:
            errors.append(
                f"Playbook '{playbook.id}' references unknown typology_id "
                f"'{typology_id}'."
            )
    for feature_id in playbook.feature_ids:
        if feature_id not in feature_ids:
            errors.append(
                f"Playbook '{playbook.id}' references unknown feature_id "
                f"'{feature_id}'."
            )
    for policy_rule_id in playbook.policy_rule_ids:
        if policy_rule_id not in policy_rule_ids:
            errors.append(
                f"Playbook '{playbook.id}' references unknown policy_rule_id "
                f"'{policy_rule_id}'."
            )

for typology in self.typologies:
    for playbook_id in typology.playbook_ids:
        if playbook_id not in playbook_ids:
            errors.append(
                f"Typology '{typology.id}' references unknown playbook_id "
                f"'{playbook_id}'."
            )
```

- [x] **Step 5: Seed Medicare playbooks**

Add `playbooks:` near the feature/typology sections in `backend/config/defaults/medicare_fraud.yaml`:

```yaml
playbooks:
  version: cms-playbooks-v1
  items:
    - id: provider_billing_spike_review
      version: v1
      title: Provider billing spike review
      summary: Review provider billing acceleration against baseline, peers, policy, and supporting records.
      status: draft
      typology_ids: [billing_spike]
      feature_ids: [provider_billing_outlier_score, provider_claim_volume_growth]
      policy_rule_ids: []
      evidence_requirements:
        - id: risk_projection
          label: Risk projection
          description: Current risk score, score age, and top contributing features.
          source_types: [risk_projection, feature_value]
          required: true
        - id: peer_context
          label: Peer context
          description: Peer cohort distribution and z-score summary.
          source_types: [peer_analysis]
          required: true
      workflow_steps:
        - id: review_risk_projection
          label: Review risk projection
          capability_ref: analytics.risk_projection.read
          input_refs: [knowledge_base_id, entity_id]
          output_refs: [risk_summary]
          requires_human_approval: false
      rag_prompts:
        - id: billing_spike_context
          model_ref: default
          prompt_version: v1
          system_prompt: Answer with cited evidence only.
          user_prompt: Summarize the billing spike evidence for {entity_id}.
      decision_guidance:
        - Open or attach a case when billing acceleration is corroborated by source records and peer context.
      export_tags: [cms, billing, provider]
    - id: peer_outlier_provider_review
      version: v1
      title: Peer outlier provider review
      summary: Review provider behavior against configured peer cohorts.
      status: draft
      typology_ids: [peer_outlier]
      feature_ids: [provider_peer_zscore]
      policy_rule_ids: []
      evidence_requirements:
        - id: peer_distribution
          label: Peer distribution
          description: Cohort membership, distribution, entity value, z-score, and percentile.
          source_types: [peer_analysis]
          required: true
      workflow_steps:
        - id: gather_peer_context
          label: Gather peer context
          capability_ref: analytics.peer_analysis.read
          input_refs: [knowledge_base_id, entity_id]
          output_refs: [peer_summary]
          requires_human_approval: false
      rag_prompts:
        - id: peer_outlier_context
          model_ref: default
          prompt_version: v1
          system_prompt: Answer with cited evidence only.
          user_prompt: Explain why {entity_id} is an outlier compared with peers.
      decision_guidance:
        - Escalate only when the peer cohort is large enough and supporting evidence is available.
      export_tags: [cms, peer, provider]
    - id: identity_mismatch_review
      version: v1
      title: Identity mismatch review
      summary: Review source identities and merge or split history before relying on the canonical entity.
      status: draft
      typology_ids: [identity_mismatch]
      feature_ids: [identity_link_confidence]
      policy_rule_ids: []
      evidence_requirements:
        - id: identity_links
          label: Identity links
          description: Canonical and source identity links with confidence and review state.
          source_types: [identity_link]
          required: true
      workflow_steps:
        - id: inspect_identity_links
          label: Inspect identity links
          capability_ref: identity.canonical.read
          input_refs: [knowledge_base_id, entity_id]
          output_refs: [identity_summary]
          requires_human_approval: false
      rag_prompts:
        - id: identity_context
          model_ref: default
          prompt_version: v1
          system_prompt: Answer with cited evidence only.
          user_prompt: Summarize identity-link evidence and unresolved review states for {entity_id}.
      decision_guidance:
        - Do not treat a low-confidence identity merge as decisive until a steward review is complete.
      export_tags: [cms, identity]
```

Update relevant `typologies:` entries to include these `playbook_ids`.

- [x] **Step 6: Run schema tests to verify GREEN**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml \
  backend/.venv/bin/python -m pytest \
  backend/tests/config/test_schema.py::test_playbooks_and_typology_refs_round_trip \
  backend/tests/config/test_schema.py::test_typology_rejects_unknown_playbook_reference \
  backend/tests/config/test_schema.py::test_playbook_rejects_unknown_references \
  backend/tests/config/test_loader.py::test_medicare_fraud_pack_declares_seed_playbooks -q
```

Expected: PASS.

- [x] **Step 7: Run quality checks**

Run:

```bash
uv run --project backend ruff check backend/config/schema.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py
uv run --project backend pyright backend/config/schema.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py
```

Expected: ruff passes and pyright reports 0 errors.

- [x] **Step 8: Commit Task 1**

Run:

```bash
git add backend/config/schema.py backend/config/defaults/medicare_fraud.yaml backend/tests/config/test_schema.py backend/tests/config/test_loader.py docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Add SAFE-CMS-013 playbook config schema"
```

---

## Task 2: Playbook Domain Service

**Files:**
- Create: `backend/playbooks/__init__.py`
- Create: `backend/playbooks/models.py`
- Create: `backend/playbooks/repository.py`
- Create: `backend/playbooks/service.py`
- Create: `backend/playbooks/adapters/__init__.py`
- Create: `backend/playbooks/adapters/in_memory.py`
- Create: `backend/tests/playbooks/test_service.py`
- Create: `backend/tests/playbooks/test_in_memory.py`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/playbooks/test_service.py`:

```python
from __future__ import annotations

import pytest

from config.loader import load_config
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookImportArtifact, PlaybookPublishRequest
from playbooks.service import PlaybookService


def _service() -> PlaybookService:
    return PlaybookService(
        repository=InMemoryPlaybookRepository(),
        domain_config=load_config(),
    )


def test_list_seed_playbooks_returns_config_authored_definitions() -> None:
    service = _service()

    page = service.list_seed_playbooks(domain_name="medicare_fraud", limit=50, offset=0)

    assert page.total >= 3
    assert {item.id for item in page.items} >= {
        "provider_billing_spike_review",
        "peer_outlier_provider_review",
        "identity_mismatch_review",
    }


def test_publish_seed_playbook_creates_immutable_snapshot() -> None:
    service = _service()

    first = service.publish_seed_playbook(
        PlaybookPublishRequest(
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )
    second = service.publish_seed_playbook(
        PlaybookPublishRequest(
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.status == "published"
    assert first.definition.id == "provider_billing_spike_review"


def test_import_export_round_trips_playbooks() -> None:
    service = _service()
    service.publish_seed_playbook(
        PlaybookPublishRequest(
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )

    artifact = service.export_domain_playbooks(domain_name="medicare_fraud")
    imported = service.import_playbooks(
        PlaybookImportArtifact.model_validate_json(artifact.model_dump_json()),
        actor_user_id="admin-2",
    )

    assert imported.domain_name == "medicare_fraud"
    assert imported.imported_count >= 1


def test_publish_unknown_seed_playbook_raises_key_error() -> None:
    service = _service()

    with pytest.raises(KeyError):
        service.publish_seed_playbook(
            PlaybookPublishRequest(
                domain_name="medicare_fraud",
                playbook_id="missing",
                version="v1",
                actor_user_id="admin-1",
            )
        )
```

- [ ] **Step 2: Run service tests to verify RED**

Run:

```bash
uv run --project backend pytest backend/tests/playbooks/test_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'playbooks'`.

- [ ] **Step 3: Add playbook models**

Create `backend/playbooks/models.py`:

```python
"""Domain-neutral fraud playbook models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from config.schema import FraudPlaybookConfig
from shared.utils import utc_now

PlaybookStatus = Literal["draft", "published", "retired"]
PlaybookSnapshotSource = Literal["domain_config", "api_import", "api_publish"]


class PlaybookSnapshot(BaseModel):
    """Immutable published playbook version."""

    snapshot_id: str
    domain_name: str = Field(min_length=1)
    playbook_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: PlaybookStatus = "published"
    definition: FraudPlaybookConfig
    source: PlaybookSnapshotSource = "domain_config"
    published_by: str = Field(min_length=1)
    published_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PlaybookPage(BaseModel):
    """One page of playbook definitions or snapshots."""

    items: list[FraudPlaybookConfig] = Field(default_factory=lambda: cast(list[FraudPlaybookConfig], []))
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PlaybookSnapshotPage(BaseModel):
    """One page of published playbook snapshots."""

    items: list[PlaybookSnapshot] = Field(default_factory=lambda: cast(list[PlaybookSnapshot], []))
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PlaybookPublishRequest(BaseModel):
    """Request to publish a config-authored seed playbook."""

    domain_name: str = Field(min_length=1)
    playbook_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    actor_user_id: str = Field(min_length=1)


class PlaybookImportArtifact(BaseModel):
    """Portable domain-pack artifact containing validated playbooks."""

    schema_version: str = "playbooks.v1"
    domain_name: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    playbooks: list[FraudPlaybookConfig] = Field(default_factory=lambda: cast(list[FraudPlaybookConfig], []))


class PlaybookImportResult(BaseModel):
    """Import result summary."""

    domain_name: str
    imported_count: int = Field(ge=0)
    snapshot_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class PlaybookRef(BaseModel):
    """Historical reference to a playbook version."""

    playbook_id: str = Field(min_length=1)
    playbook_version: str = Field(min_length=1)
    title: str = ""
```

- [ ] **Step 4: Add repository protocol and in-memory adapter**

Create `backend/playbooks/repository.py`:

```python
"""Playbook repository boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from playbooks.models import PlaybookSnapshot, PlaybookSnapshotPage


@runtime_checkable
class PlaybookRepository(Protocol):
    """Store immutable published playbook snapshots."""

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot: ...

    def get_snapshot(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> PlaybookSnapshot | None: ...

    def list_snapshots(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookSnapshotPage: ...
```

Create `backend/playbooks/adapters/in_memory.py`:

```python
"""In-memory playbook repository."""

from __future__ import annotations

from playbooks.models import PlaybookSnapshot, PlaybookSnapshotPage

__all__ = ["InMemoryPlaybookRepository"]


class InMemoryPlaybookRepository:
    """Dict-backed playbook snapshot repository for tests and local development."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str, str], PlaybookSnapshot] = {}

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot:
        key = (snapshot.domain_name, snapshot.playbook_id, snapshot.version)
        self._snapshots[key] = snapshot.model_copy(deep=True)
        return snapshot.model_copy(deep=True)

    def get_snapshot(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> PlaybookSnapshot | None:
        snapshot = self._snapshots.get((domain_name, playbook_id, version))
        return snapshot.model_copy(deep=True) if snapshot is not None else None

    def list_snapshots(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookSnapshotPage:
        items = [
            snapshot.model_copy(deep=True)
            for snapshot in self._snapshots.values()
            if snapshot.domain_name == domain_name
        ]
        items.sort(key=lambda item: (item.playbook_id, item.version))
        return PlaybookSnapshotPage(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )
```

- [ ] **Step 5: Add service**

Create `backend/playbooks/service.py`:

```python
"""Playbook publication, export, and import service."""

from __future__ import annotations

from config.schema import DomainConfig, FraudPlaybookConfig
from playbooks.models import (
    PlaybookImportArtifact,
    PlaybookImportResult,
    PlaybookPage,
    PlaybookPublishRequest,
    PlaybookSnapshot,
)
from playbooks.repository import PlaybookRepository
from shared.utils import utc_now


class PlaybookService:
    """Coordinate config-authored playbooks with published snapshots."""

    def __init__(self, *, repository: PlaybookRepository, domain_config: DomainConfig) -> None:
        self._repository = repository
        self._domain_config = domain_config

    def list_seed_playbooks(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookPage:
        self._require_active_domain(domain_name)
        items = [item.model_copy(deep=True) for item in self._domain_config.playbooks.items]
        return PlaybookPage(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )

    def publish_seed_playbook(self, request: PlaybookPublishRequest) -> PlaybookSnapshot:
        seed = self._seed_by_id(request.domain_name, request.playbook_id, request.version)
        existing = self._repository.get_snapshot(
            domain_name=request.domain_name,
            playbook_id=request.playbook_id,
            version=request.version,
        )
        if existing is not None:
            return existing
        now = utc_now()
        snapshot = PlaybookSnapshot(
            snapshot_id=f"{request.domain_name}:{request.playbook_id}:{request.version}",
            domain_name=request.domain_name,
            playbook_id=request.playbook_id,
            version=request.version,
            status="published",
            definition=seed.model_copy(update={"status": "published"}, deep=True),
            source="domain_config",
            published_by=request.actor_user_id,
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        return self._repository.upsert_snapshot(snapshot)

    def export_domain_playbooks(self, *, domain_name: str) -> PlaybookImportArtifact:
        self._require_active_domain(domain_name)
        snapshots = self._repository.list_snapshots(domain_name=domain_name, limit=500, offset=0)
        definitions = [snapshot.definition.model_copy(deep=True) for snapshot in snapshots.items]
        if not definitions:
            definitions = [item.model_copy(deep=True) for item in self._domain_config.playbooks.items]
        return PlaybookImportArtifact(
            domain_name=domain_name,
            catalog_version=self._domain_config.playbooks.version,
            playbooks=definitions,
        )

    def import_playbooks(
        self, artifact: PlaybookImportArtifact, *, actor_user_id: str
    ) -> PlaybookImportResult:
        self._require_active_domain(artifact.domain_name)
        snapshot_ids: list[str] = []
        for playbook in artifact.playbooks:
            request = PlaybookPublishRequest(
                domain_name=artifact.domain_name,
                playbook_id=playbook.id,
                version=playbook.version,
                actor_user_id=actor_user_id,
            )
            snapshot = self.publish_seed_playbook(request)
            snapshot_ids.append(snapshot.snapshot_id)
        return PlaybookImportResult(
            domain_name=artifact.domain_name,
            imported_count=len(snapshot_ids),
            snapshot_ids=snapshot_ids,
        )

    def _require_active_domain(self, domain_name: str) -> None:
        if self._domain_config.domain.name != domain_name:
            raise KeyError(domain_name)

    def _seed_by_id(
        self, domain_name: str, playbook_id: str, version: str
    ) -> FraudPlaybookConfig:
        self._require_active_domain(domain_name)
        for playbook in self._domain_config.playbooks.items:
            if playbook.id == playbook_id and playbook.version == version:
                return playbook.model_copy(deep=True)
        raise KeyError(f"{playbook_id}:{version}")
```

Create `backend/playbooks/__init__.py` and `backend/playbooks/adapters/__init__.py` with exports.

- [ ] **Step 6: Run service tests to verify GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/playbooks/test_service.py -q
uv run --project backend pytest backend/tests/playbooks/test_in_memory.py -q
```

Expected: PASS.

- [ ] **Step 7: Run quality checks**

Run:

```bash
uv run --project backend ruff check backend/playbooks backend/tests/playbooks
uv run --project backend pyright backend/playbooks backend/tests/playbooks
```

Expected: ruff passes and pyright reports 0 errors.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add backend/playbooks backend/tests/playbooks docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Add SAFE-CMS-013 playbook service"
```

---

## Task 3: Postgres Snapshot Persistence

**Files:**
- Create: `backend/playbooks/adapters/postgres.py`
- Create: `backend/database/migrations/versions/0019_fraud_playbooks.py`
- Modify: `backend/database/migrations/snapshots/head.sql`
- Create: `backend/tests/playbooks/test_postgres.py`
- Create: `backend/tests/database/test_fraud_playbooks_migration.py`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [ ] **Step 1: Write failing migration and Postgres tests**

Create `backend/tests/database/test_fraud_playbooks_migration.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_fraud_playbooks_migration_declares_snapshot_table() -> None:
    migration = Path("backend/database/migrations/versions/0019_fraud_playbooks.py").read_text()

    assert "CREATE TABLE IF NOT EXISTS fraud_playbook_snapshots" in migration
    assert "PRIMARY KEY (domain_name, playbook_id, version)" in migration
    assert "ALTER TABLE cases ADD COLUMN IF NOT EXISTS playbook_ref jsonb" in migration
```

Create `backend/tests/playbooks/test_postgres.py` with a test using the existing Postgres connection fixture pattern from `backend/tests/analytics/test_identity_resolution_postgres.py`:

```python
def test_postgres_playbook_repository_round_trips_snapshot(postgres_connection_provider) -> None:
    repository = PostgresPlaybookRepository(postgres_connection_provider)
    snapshot = _snapshot()

    repository.upsert_snapshot(snapshot)
    stored = repository.get_snapshot(
        domain_name="medicare_fraud",
        playbook_id="provider_billing_spike_review",
        version="v1",
    )

    assert stored == snapshot
    page = repository.list_snapshots(domain_name="medicare_fraud", limit=10, offset=0)
    assert page.total == 1
    assert page.items[0].definition.id == "provider_billing_spike_review"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --project backend pytest backend/tests/database/test_fraud_playbooks_migration.py backend/tests/playbooks/test_postgres.py -q
```

Expected: FAIL because migration and `PostgresPlaybookRepository` do not exist.

- [ ] **Step 3: Add migration**

Create `backend/database/migrations/versions/0019_fraud_playbooks.py`:

```python
"""Add fraud playbook snapshots.

Revision ID: 0019_fraud_playbooks
Revises: 0018_identity_links
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision: str = "0019_fraud_playbooks"
down_revision: str | None = "0018_identity_links"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fraud_playbook_snapshots (
            domain_name text NOT NULL,
            playbook_id text NOT NULL,
            version text NOT NULL,
            status text NOT NULL,
            definition jsonb NOT NULL,
            source text NOT NULL,
            published_by text NOT NULL,
            published_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT pk_fraud_playbook_snapshots
                PRIMARY KEY (domain_name, playbook_id, version),
            CONSTRAINT ck_fraud_playbook_snapshots_status CHECK (
                status IN ('draft', 'published', 'retired')
            ),
            CONSTRAINT ck_fraud_playbook_snapshots_source CHECK (
                source IN ('domain_config', 'api_import', 'api_publish')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fraud_playbook_snapshots_domain_status
        ON fraud_playbook_snapshots (domain_name, status, updated_at DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE cases
        ADD COLUMN IF NOT EXISTS playbook_ref jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS playbook_ref")
    op.execute("DROP INDEX IF EXISTS ix_fraud_playbook_snapshots_domain_status")
    op.execute("DROP TABLE IF EXISTS fraud_playbook_snapshots")
```

- [ ] **Step 4: Add Postgres adapter**

Create `backend/playbooks/adapters/postgres.py` using JSONB serialization like existing adapters:

```python
"""Postgres-backed playbook snapshot repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from config.schema import FraudPlaybookConfig
from database.protocols import ConnectionProvider, Row
from playbooks.models import PlaybookSnapshot, PlaybookSnapshotPage

__all__ = ["PostgresPlaybookRepository"]


class PostgresPlaybookRepository:
    """Store playbook snapshots in ``fraud_playbook_snapshots``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot:
        with self._provider.connection() as conn:
            conn.execute(
                """
                INSERT INTO fraud_playbook_snapshots (
                    domain_name, playbook_id, version, status, definition,
                    source, published_by, published_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (domain_name, playbook_id, version) DO UPDATE SET
                    status = EXCLUDED.status,
                    definition = EXCLUDED.definition,
                    source = EXCLUDED.source,
                    published_by = EXCLUDED.published_by,
                    published_at = EXCLUDED.published_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    snapshot.domain_name,
                    snapshot.playbook_id,
                    snapshot.version,
                    snapshot.status,
                    snapshot.definition.model_dump_json(),
                    snapshot.source,
                    snapshot.published_by,
                    snapshot.published_at,
                    snapshot.created_at,
                    snapshot.updated_at,
                ),
            )
            conn.commit()
        return snapshot.model_copy(deep=True)

    def get_snapshot(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> PlaybookSnapshot | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                """
                SELECT domain_name, playbook_id, version, status, definition,
                       source, published_by, published_at, created_at, updated_at
                FROM fraud_playbook_snapshots
                WHERE domain_name = %s AND playbook_id = %s AND version = %s
                """,
                (domain_name, playbook_id, version),
            ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def list_snapshots(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookSnapshotPage:
        with self._provider.connection() as conn:
            count_row = conn.execute(
                "SELECT count(*) FROM fraud_playbook_snapshots WHERE domain_name = %s",
                (domain_name,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT domain_name, playbook_id, version, status, definition,
                       source, published_by, published_at, created_at, updated_at
                FROM fraud_playbook_snapshots
                WHERE domain_name = %s
                ORDER BY playbook_id ASC, version ASC
                LIMIT %s OFFSET %s
                """,
                (domain_name, limit, offset),
            ).fetchall()
        return PlaybookSnapshotPage(
            items=[_row_to_snapshot(row) for row in rows],
            total=cast(int, count_row[0]) if count_row is not None else 0,
            limit=limit,
            offset=offset,
        )


def _row_to_snapshot(row: Row) -> PlaybookSnapshot:
    raw_definition = row[4]
    definition_payload = (
        json.loads(raw_definition)
        if isinstance(raw_definition, str)
        else raw_definition
    )
    return PlaybookSnapshot(
        snapshot_id=f"{row[0]}:{row[1]}:{row[2]}",
        domain_name=cast(str, row[0]),
        playbook_id=cast(str, row[1]),
        version=cast(str, row[2]),
        status=cast("str", row[3]),
        definition=FraudPlaybookConfig.model_validate(definition_payload),
        source=cast("str", row[5]),
        published_by=cast(str, row[6]),
        published_at=cast(datetime, row[7]),
        created_at=cast(datetime, row[8]),
        updated_at=cast(datetime, row[9]),
    )
```

- [ ] **Step 5: Refresh and verify migration snapshot**

Run:

```bash
scripts/ci_migration_check.sh --update-snapshot
scripts/ci_migration_check.sh
```

Expected: both commands pass; `backend/database/migrations/snapshots/head.sql` includes `fraud_playbook_snapshots` and `cases.playbook_ref`.

- [ ] **Step 6: Run adapter tests to verify GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/database/test_fraud_playbooks_migration.py backend/tests/playbooks/test_postgres.py -q
uv run --project backend ruff check backend/playbooks/adapters/postgres.py backend/tests/playbooks/test_postgres.py backend/tests/database/test_fraud_playbooks_migration.py
uv run --project backend pyright backend/playbooks/adapters/postgres.py backend/tests/playbooks/test_postgres.py backend/tests/database/test_fraud_playbooks_migration.py
```

Expected: pytest passes, ruff passes, pyright reports 0 errors.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add backend/playbooks/adapters/postgres.py backend/database/migrations/versions/0019_fraud_playbooks.py backend/database/migrations/snapshots/head.sql backend/tests/playbooks/test_postgres.py backend/tests/database/test_fraud_playbooks_migration.py docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Persist SAFE-CMS-013 playbook snapshots"
```

---

## Task 4: KB-Scoped Playbook API

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Create: `backend/api/routers/playbooks.py`
- Modify: `backend/api/app.py`
- Create: `backend/tests/api/test_playbooks_router.py`
- Modify: `backend/tests/api/test_app.py`
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/api/test_playbooks_router.py` with tests for:

```python
def test_list_playbooks_returns_seed_and_published_versions() -> None: ...
def test_publish_playbook_requires_admin_and_uses_authenticated_actor() -> None: ...
def test_playbook_routes_hide_unauthorized_kb() -> None: ...
def test_export_import_round_trips_domain_artifact() -> None: ...
```

Use the auth-enabled pattern from `backend/tests/api/test_identity_router.py` and the KB entitlement pattern from `backend/api/routers/score_runs.py`.

- [ ] **Step 2: Run API tests to verify RED**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_playbooks_router.py -q
```

Expected: FAIL because the router and API dependencies do not exist.

- [ ] **Step 3: Add API contracts**

Add response/request models in `backend/api/contracts.py`:

```python
class PlaybookEvidenceRequirementResponse(BaseModel): ...
class PlaybookWorkflowStepResponse(BaseModel): ...
class PlaybookRagPromptResponse(BaseModel): ...
class PlaybookResponse(BaseModel): ...
class PlaybookListResponse(BaseModel): ...
class PlaybookSnapshotResponse(BaseModel): ...
class PlaybookPublishRequestPayload(BaseModel):
    version: str = Field(default="v1", min_length=1)
class PlaybookImportRequestPayload(BaseModel):
    artifact: dict[str, object]
class PlaybookImportResponse(BaseModel): ...
class PlaybookExportResponse(BaseModel):
    artifact: dict[str, object]
```

Map `FraudPlaybookConfig` fields directly and keep prompts visible only as configured strings; redact no secrets because no secret fields are allowed.

- [ ] **Step 4: Add dependencies and router**

Add `get_playbook_repository()` and `get_playbook_service()` in `backend/api/dependencies.py`, using Postgres when `get_connection_provider()` is available and `InMemoryPlaybookRepository` otherwise.

Create `backend/api/routers/playbooks.py`:

```python
router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/playbooks",
    tags=["playbooks"],
)
```

Endpoints:

- `GET ""` with viewer role.
- `GET "/{playbook_id}/versions/{version}"` with viewer role.
- `POST "/{playbook_id}/publish"` with admin role.
- `POST "/import"` with admin role.
- `GET "/export"` with viewer role.

Each endpoint must:

1. Load the KB from `get_knowledge_base_repository`.
2. Apply `user.knowledge_base_ids` entitlement checks.
3. Resolve `domain_name = kb.domain_name or domain_config.domain.name`.
4. Return 404 for missing/inaccessible KB or missing playbook.

- [ ] **Step 5: Register router and OpenAPI guards**

Modify `backend/api/app.py` to include `playbooks_router`.

Modify `backend/tests/api/test_app.py` expected paths and tags:

```python
"/knowledgebases/{knowledge_base_id}/playbooks",
"/knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/versions/{version}",
"/knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/publish",
"/knowledgebases/{knowledge_base_id}/playbooks/import",
"/knowledgebases/{knowledge_base_id}/playbooks/export",
```

Expected tag: `"playbooks"`.

- [ ] **Step 6: Run API tests to verify GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_playbooks_router.py backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_lists_all_required_paths backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_tags_cover_all_routers -q
uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/playbooks.py backend/tests/api/test_playbooks_router.py backend/tests/api/test_app.py
uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/playbooks.py backend/tests/api/test_playbooks_router.py backend/tests/api/test_app.py
```

Expected: pytest passes, ruff passes, pyright reports 0 errors.

- [ ] **Step 7: Regenerate contracts**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
npm run codegen:api --prefix chili_app
```

Expected: generated schema includes `Playbook*` response/request models and playbook paths.

- [ ] **Step 8: Commit Task 4**

Run:

```bash
git add backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/playbooks.py backend/tests/api/test_playbooks_router.py backend/tests/api/test_app.py chili_app/openapi.json chili_app/src/lib/api/schema.ts docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Expose SAFE-CMS-013 playbook API"
```

---

## Task 5: Historical Playbook References

**Files:**
- Modify: `backend/cases/models.py`
- Modify: case Postgres/in-memory adapters and router mappers.
- Modify: `backend/monitoring/models.py`
- Modify: alert history adapters/mappers where `generation_metadata` is persisted.
- Modify: `backend/analytics/explainability/models.py`
- Modify: evidence generation/provenance tests.
- Modify: `backend/tests/api/test_cases_router.py` or current case router tests.
- Modify: `backend/tests/monitoring/test_postgres_alert_history.py`
- Modify: `backend/tests/analytics/explainability/test_service.py`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [ ] **Step 1: Write failing historical snapshot tests**

Add focused tests proving:

```python
def test_case_preserves_playbook_ref_snapshot() -> None: ...
def test_alert_history_preserves_playbook_ref_in_generation_metadata() -> None: ...
def test_evidence_provenance_records_playbook_ref_metadata() -> None: ...
def test_new_playbook_version_does_not_rewrite_existing_case_ref() -> None: ...
```

Expected fields:

```python
{"playbook_id": "provider_billing_spike_review", "playbook_version": "v1", "title": "Provider billing spike review"}
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_cases_router.py backend/tests/monitoring/test_postgres_alert_history.py backend/tests/analytics/explainability/test_service.py -q
```

Expected: FAIL where `Case` has no `playbook_ref` and provenance/metadata mappers do not assert the snapshot.

- [ ] **Step 3: Add model and mapper support**

Add to `backend/cases/models.py`:

```python
from playbooks.models import PlaybookRef

class Case(BaseModel):
    ...
    playbook_ref: PlaybookRef | None = None
```

Add `playbook_ref` to case persistence adapters and API responses. Store it as JSON in the new `cases.playbook_ref` column for Postgres and as the Pydantic field in memory.

For alerts and evidence:

- Keep alert `generation_metadata["playbook_ref"]` as JSON-safe metadata.
- Add evidence provenance `metadata["playbook_ref"]` when explanation lineage includes playbook context.

- [ ] **Step 4: Run historical snapshot tests to verify GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_cases_router.py backend/tests/monitoring/test_postgres_alert_history.py backend/tests/analytics/explainability/test_service.py -q
uv run --project backend ruff check backend/cases backend/monitoring backend/analytics/explainability backend/tests/api/test_cases_router.py backend/tests/monitoring/test_postgres_alert_history.py backend/tests/analytics/explainability/test_service.py
uv run --project backend pyright backend/cases backend/monitoring backend/analytics/explainability backend/tests/api/test_cases_router.py backend/tests/monitoring/test_postgres_alert_history.py backend/tests/analytics/explainability/test_service.py
```

Expected: pytest passes, ruff passes, pyright reports 0 errors.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add backend/cases backend/monitoring backend/analytics/explainability backend/tests/api/test_cases_router.py backend/tests/monitoring/test_postgres_alert_history.py backend/tests/analytics/explainability/test_service.py docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Preserve SAFE-CMS-013 playbook history"
```

---

## Task 6: Frontend Playbook Surfaces

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Create: `chili_app/src/api/playbooks.ts`
- Create: `chili_app/src/api/__tests__/playbooks.test.ts`
- Create: `chili_app/src/components/playbooks/PlaybookBadge.tsx`
- Create: `chili_app/src/components/playbooks/PlaybookDetailPanel.tsx`
- Create: `chili_app/src/components/playbooks/__tests__/PlaybookBadge.test.tsx`
- Create: `chili_app/src/components/playbooks/__tests__/PlaybookDetailPanel.test.tsx`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: relevant page tests.
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`

- [ ] **Step 1: Write failing frontend tests**

Create API helper tests:

```ts
it('serializes playbook list by knowledge base', async () => {
  apiFetchMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })

  await listPlaybooks('kb-live')

  expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-live/playbooks?limit=50&offset=0')
})
```

Create component tests asserting:

- `PlaybookBadge` shows title, version, and status.
- `PlaybookDetailPanel` shows evidence requirements, workflow steps, RAG prompt labels, and decision guidance.
- Investigation/case pages render a playbook badge when API data or case `playbook_ref` is present.

- [ ] **Step 2: Run frontend tests to verify RED**

Run:

```bash
npm run test:run --prefix chili_app -- \
  src/api/__tests__/playbooks.test.ts \
  src/components/playbooks/__tests__/PlaybookBadge.test.tsx \
  src/components/playbooks/__tests__/PlaybookDetailPanel.test.tsx \
  src/pages/__tests__/InvestigationWorkbenchPage.test.tsx \
  src/pages/__tests__/CaseManagementPage.test.tsx
```

Expected: FAIL because API helpers and components do not exist.

- [ ] **Step 3: Add API helper and contract aliases**

Create `chili_app/src/api/playbooks.ts`:

```ts
import { useQuery } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  PlaybookExportResponse,
  PlaybookImportRequestPayload,
  PlaybookImportResponse,
  PlaybookListResponse,
  PlaybookPublishRequestPayload,
  PlaybookSnapshotResponse,
} from './contracts'

export function playbooksQueryKey(knowledgeBaseId: string | null) {
  return ['playbooks', knowledgeBaseId ?? 'missing'] as const
}

export function listPlaybooks(
  knowledgeBaseId: string,
  limit = 50,
  offset = 0,
): Promise<PlaybookListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return apiFetch<PlaybookListResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks?${params}`,
  )
}

export function publishPlaybook(
  knowledgeBaseId: string,
  playbookId: string,
  payload: PlaybookPublishRequestPayload,
): Promise<PlaybookSnapshotResponse> {
  return apiPost(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/${encodeURIComponent(playbookId)}/publish`,
    payload,
  )
}

export function importPlaybooks(
  knowledgeBaseId: string,
  payload: PlaybookImportRequestPayload,
): Promise<PlaybookImportResponse> {
  return apiPost(`/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/import`, payload)
}

export function exportPlaybooks(knowledgeBaseId: string): Promise<PlaybookExportResponse> {
  return apiFetch(`/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/export`)
}

export function usePlaybooks(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: playbooksQueryKey(knowledgeBaseId),
    queryFn: () => listPlaybooks(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}
```

Add generated schema aliases in `chili_app/src/api/contracts.ts`.

- [ ] **Step 4: Add components and page placements**

Create compact components using existing `Card`, `Chip`, `EmptyState`, and `metric-stack` patterns.

`PlaybookBadge` props:

```ts
type PlaybookBadgeProps = {
  title: string
  version: string
  status?: string
}
```

`PlaybookDetailPanel` props:

```ts
type PlaybookDetailPanelProps = {
  playbook: PlaybookResponse | null
  isLoading?: boolean
  isError?: boolean
}
```

Wire badges into:

- `InvestigationWorkbenchPage` near cockpit context when the selected alert/case has a playbook ref.
- `CaseManagementPage` in the active case detail/dossier header.

- [ ] **Step 5: Run frontend tests to verify GREEN**

Run:

```bash
npm run test:run --prefix chili_app -- \
  src/api/__tests__/playbooks.test.ts \
  src/components/playbooks/__tests__/PlaybookBadge.test.tsx \
  src/components/playbooks/__tests__/PlaybookDetailPanel.test.tsx \
  src/pages/__tests__/InvestigationWorkbenchPage.test.tsx \
  src/pages/__tests__/CaseManagementPage.test.tsx
npx eslint --prefix chili_app src/api/playbooks.ts src/components/playbooks src/pages/InvestigationWorkbenchPage.tsx src/pages/CaseManagementPage.tsx
pnpm --dir chili_app build
```

Expected: tests pass, scoped lint passes, build passes with the existing bundle-size warning if still present.

- [ ] **Step 6: Commit Task 6**

Run:

```bash
git add chili_app/src/api/contracts.ts chili_app/src/api/playbooks.ts chili_app/src/api/__tests__/playbooks.test.ts chili_app/src/components/playbooks chili_app/src/pages/InvestigationWorkbenchPage.tsx chili_app/src/pages/CaseManagementPage.tsx chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx chili_app/src/pages/__tests__/CaseManagementPage.test.tsx docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Surface SAFE-CMS-013 playbooks"
```

---

## Task 7: Management Export/Import and Backlog Closeout

**Files:**
- Modify: `docs/project/planning/backlog.md`
- Modify: `docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md`
- Add or modify frontend management page tests from Task 6 if management actions were split.

- [ ] **Step 1: Run full focused verification**

Run:

```bash
uv run --project backend pytest \
  backend/tests/config/test_schema.py \
  backend/tests/config/test_loader.py \
  backend/tests/playbooks \
  backend/tests/database/test_fraud_playbooks_migration.py \
  backend/tests/api/test_playbooks_router.py
uv run --project backend ruff check backend/config/schema.py backend/playbooks backend/api/routers/playbooks.py backend/api/contracts.py backend/api/dependencies.py backend/tests/config backend/tests/playbooks backend/tests/api/test_playbooks_router.py
uv run --project backend pyright backend/config/schema.py backend/playbooks backend/api/routers/playbooks.py backend/api/contracts.py backend/api/dependencies.py backend/tests/config backend/tests/playbooks backend/tests/api/test_playbooks_router.py
scripts/ci_migration_check.sh
npm run test:run --prefix chili_app -- \
  src/api/__tests__/playbooks.test.ts \
  src/components/playbooks/__tests__/PlaybookBadge.test.tsx \
  src/components/playbooks/__tests__/PlaybookDetailPanel.test.tsx \
  src/pages/__tests__/InvestigationWorkbenchPage.test.tsx \
  src/pages/__tests__/CaseManagementPage.test.tsx
pnpm --dir chili_app build
git diff --check
```

Expected: all checks pass; build may retain the existing Vite chunk-size warning.

- [ ] **Step 2: Request code review**

Use Superpowers `requesting-code-review` against the full SAFE-CMS-013 diff. Ask the reviewer to focus on:

- Playbook config validation and cross-reference correctness.
- Immutability of published snapshots.
- KB entitlement checks on playbook APIs.
- Historical case/alert/evidence playbook version preservation.
- Frontend rendering and no CMS literals in shared components.

- [ ] **Step 3: Apply review feedback and rerun focused checks**

For every accepted finding:

1. Write or adjust a failing regression test.
2. Implement the fix.
3. Rerun the relevant focused tests.
4. Rerun the full focused verification command group from Step 1.

- [ ] **Step 4: Update backlog only after review approval**

Change the first SAFE-CMS-013 row in `docs/project/planning/backlog.md` from:

```markdown
planned — depends on typology and provenance models
```

to:

```markdown
done — versioned fraud playbook config, publication snapshots, KB-scoped API, historical playbook refs, export/import, and cockpit/case UI completed with review gates 2026-08-04
```

Change the formalization row from:

```markdown
Needs PI 4 workflow/playbook ADR.
```

to:

```markdown
Implemented 2026-08-04: PI 4 ADR, config-authored seed playbooks, DB-published immutable snapshots, historical alert/evidence/case refs, KB-scoped API, export/import, and frontend playbook surfaces.
```

- [ ] **Step 5: Commit closeout**

Run:

```bash
git add docs/project/planning/backlog.md docs/superpowers/plans/2026-08-04-safe-cms-013-versioned-fraud-playbooks.md
git commit -m "Close SAFE-CMS-013 playbook plan"
```

---

## Review Gates

- Review after Task 1 before adding service/persistence.
- Review after Task 4 before historical refs and frontend work.
- Review after Task 6 before backlog closeout.

## Definition Of Done

- CMS playbooks validate at config load and non-CMS packs can omit them.
- Published playbook snapshots are immutable by domain/playbook/version.
- Alerts, evidence, and cases preserve playbook ID/version at creation or promotion time.
- New playbook versions do not mutate historical case meaning.
- APIs are KB-scoped, RBAC-checked, and included in OpenAPI/codegen.
- Frontend surfaces show playbook title/version/status and detail without hardcoded CMS behavior.
- Export/import round-trip works for the Medicare playbook artifact.
- Backlog changes only after review approval and all focused verification passes.

## Self-Review Notes

- Spec coverage: The tasks cover schema validation, config seeding, publication persistence, API, historical refs, UI, export/import, and backlog closeout from the SAFE-CMS-013 source sprint.
- Placeholder scan: This plan contains no open placeholder markers and every code-changing task includes concrete test commands and code shapes.
- Type consistency: `playbook_id`, `version`, `domain_name`, `PlaybookSnapshot`, `PlaybookImportArtifact`, and `PlaybookRef` names are consistent across backend, API, and frontend tasks.
