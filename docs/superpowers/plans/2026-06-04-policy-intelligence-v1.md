# Policy Intelligence v1 Implementation Plan (BL-011)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the seeded "policy gap" surface with a real, durable, KB-scoped **Policy Item** vertical — domain-configured rule packs → worker-generated items → analyst triage (accept/reject/defer/escalate-to-case).

**Architecture:** A new `backend/policy/` module mirrors `backend/cases/` exactly (models · `adapters/protocols.py` · in-memory + Postgres adapters · service · `exceptions.py`), plus a pure `policy/evaluation.py` rule evaluator. Rule *definitions* live in `DomainConfig.policy_rules` (config-driven, generic). The worker folds rule evaluation into the existing `handle_records_ingested` stage (reusing the per-KB metrics throttle) and upserts items idempotently by natural key `(knowledge_base_id, rule_id, target_ref)`. The API gateway exposes `/policy/items` + triage; escalate-to-case is orchestrated in `api/dependencies.py` (the only layer allowed to depend on both `PolicyService` and `CaseService`). The frontend `PolicyIntelligencePage` is rebuilt around the item queue.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · psycopg 3 / Alembic / TimescaleDB · Redis Streams · React 19 + TS + Vite + TanStack Query · Vitest · Playwright.

**Spec:** [docs/superpowers/specs/2026-06-04-policy-intelligence-v1-design.md](../specs/2026-06-04-policy-intelligence-v1-design.md)

---

## Conventions used throughout this plan

- **Backend test/typecheck/lint (host venv — fast path, per dev-environment notes):** run from `backend/`:
  - `cd backend && .venv/bin/pytest -q -m "not integration" <path>`
  - `cd backend && .venv/bin/pyright` (bare — the real gate; covers included `tests/**`)
  - `cd backend && .venv/bin/ruff check --no-cache .` (cache dir is not writable in the sandbox)
- **Integration tests** (live TimescaleDB) run inside the API container: `docker exec chiliai-api-1 sh -c "python -m pytest -q -m integration <path>"` — **run these from the main session** (Docker prompts stall inside subagents).
- **Frontend:** from `chili_app/`: `npx vitest run <path>`, `npm run lint`, `npm run build`.
- **Codegen (after any frontend-consumed Pydantic change):** from repo root `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`, then `cd chili_app && npm run codegen:api`. **Run from the main session.**
- **Playwright e2e:** `make test-e2e` from the **main session** (brings up the full stack).
- House style: `from __future__ import annotations`; `Literal` unions (not `StrEnum`) for status fields (matches `cases/models.py`); `Field(default_factory=lambda: cast(list[T], []))` for list defaults; `utc_now`/`generate_id` from `shared.utils`.

## Deviations from the spec (intentional, recorded here)

- **D-ESCALATE-IMPL:** escalate-to-case uses an **additive** `CaseService.create(..., timeline=...)` parameter plus a policy-origin timeline event, orchestrated in `api/dependencies.py` — instead of generalizing the alert `promote` payload. This keeps `policy/` fully decoupled from `cases/` and touches **zero** of the existing alert→case promote path (no regression surface).
- **D-EVAL-IMPL:** rule evaluation is **folded into `handle_records_ingested`** (evaluating the freshly-stored entities + throttled graph metrics for the batch) rather than a standalone worker stage. Satisfies the "reactive on records-ingested + throttled metrics" intent with the smallest worker change. Alert-target rules are *defined-but-not-yet-evaluated* in v1 (documented non-goal; the shipped Medicare example pack uses entity + metric targets only).
- **D-DISPOSITION-JSONB:** the item disposition persists as a single nullable `jsonb` column (mirroring the `cases.timeline`/`alert_ids` jsonb style) rather than separate columns. Same "no separate table" intent.

---

## File Structure

**Create (backend):**
- `backend/policy/__init__.py` — package marker.
- `backend/policy/models.py` — `PolicyItem`, `PolicyDisposition`, `PolicyCitation`, Literal aliases.
- `backend/policy/exceptions.py` — `PolicyError`, `PolicyPersistenceError`, `PolicyItemNotFoundError`, `PolicyItemAlreadyTriagedError`.
- `backend/policy/adapters/__init__.py`, `backend/policy/adapters/protocols.py` — `PolicyItemRepository` protocol.
- `backend/policy/adapters/in_memory.py` — `InMemoryPolicyItemRepository`.
- `backend/policy/adapters/postgres.py` — `PostgresPolicyItemRepository`.
- `backend/policy/service.py` — `PolicyService`, `create_policy_service`.
- `backend/policy/evaluation.py` — `PolicyEvalState`, `PolicyMatch`, `evaluate`.
- `backend/policy/README.md` — module doc.
- `backend/database/migrations/versions/0003_policy.py` — `policy_items` table.
- `backend/tests/policy/{__init__.py,conftest.py,test_in_memory_store.py,test_postgres_store.py,test_service.py,test_evaluation.py}`.

**Modify (backend):**
- `backend/config/schema.py` — add `PolicyPredicateValue`, `PolicyPredicate`, `PolicyCitationRef`, `PolicyRule`, `PolicyRulePack`; add `DomainConfig.policy_rules`; extend `__all__`.
- `backend/config/defaults/medicare_fraud.yaml` (+ `medicare_fraud_dev.yaml`) — add a `policy_rules:` block.
- `backend/cases/service.py` — add additive `timeline` param to `CaseService.create`.
- `backend/agent/coordinator.py` — `WorkerDependencies` + `build_worker_dependencies` + `build_policy_item_repository`/`build_policy_service`; extend `handle_records_ingested`; dispatch wiring.
- `backend/api/contracts.py` — add `PolicyItem*` DTOs + `PolicyTriageRequest`; **remove** `PolicyGap*`/`PolicyBrief*`.
- `backend/api/routers/policy.py` — replace gap routes with item + triage routes.
- `backend/api/dependencies.py` — add `get_policy_repository`/`get_policy_service` + item payload/triage providers; **remove** the four `get_policy_gap_*`/`get_policy_brief_payload` providers.
- `backend/api/state.py` — **remove** `PolicyGapRecord` + `_seed_policy_gaps` + the four policy-gap methods + helpers + the `self._policy_gaps` assignment.
- `backend/api/routers/admin.py` (dev-seed) — seed one open `PolicyItem`; add `policy_item_id` to the seed response.
- `backend/tests/config/test_loader.py` — assert both defaults load with/without `policy_rules`.

**Modify (frontend):**
- `chili_app/src/api/policy.ts` — rewrite for the items contract (KB-scoped).
- `chili_app/src/api/contracts.ts` — swap `PolicyGap*` aliases for `PolicyItem*`.
- `chili_app/src/pages/PolicyIntelligencePage.tsx` — rebuild as the item queue + triage.
- `chili_app/src/pages/__tests__/PolicyIntelligencePage.test.tsx`, `chili_app/src/api/__tests__/policy.test.ts` — rewrite.
- `chili_app/e2e/helpers/seeded.ts` — add `policy_item_id`.
- `chili_app/e2e/policy-triage.spec.ts` — new e2e.

---

# Phase 1 — Policy module foundation (in-memory, fully unit-tested)

### Task 1: Domain models + exceptions

**Files:**
- Create: `backend/policy/__init__.py` (empty), `backend/policy/models.py`, `backend/policy/exceptions.py`
- Test: `backend/tests/policy/__init__.py` (empty), `backend/tests/policy/test_service.py` (model smoke here; service tests appended in Task 4)

- [ ] **Step 1: Write the failing test** — create `backend/tests/policy/__init__.py` (empty) and `backend/tests/policy/test_service.py`:

```python
from __future__ import annotations

from policy.models import PolicyDisposition, PolicyItem


def test_policy_item_defaults_to_open_with_timestamps() -> None:
    item = PolicyItem(
        id="item-1",
        knowledge_base_id="kb-1",
        rule_id="rule-1",
        rule_pack_id="pack-1",
        target_kind="entity",
        target_ref="claim-9",
        title="Claim claim-9 exceeds billing threshold",
        severity="high",
        matched_fields={"billed_amount": 1200.0},
        citations=[],
    )
    assert item.status == "open"
    assert item.disposition is None
    assert item.created_at == item.updated_at


def test_policy_disposition_carries_case_link() -> None:
    disp = PolicyDisposition(
        action="escalate",
        actor="analyst@example.com",
        note=None,
        decided_at=PolicyItem.model_fields["created_at"].default_factory(),  # type: ignore[misc]
        case_id="case-77",
    )
    assert disp.case_id == "case-77"
    assert disp.action == "escalate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_service.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy'`.

- [ ] **Step 3: Write `backend/policy/models.py`**

```python
"""Internal domain models for policy intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.utils import utc_now

PolicyItemStatus = Literal["open", "accepted", "rejected", "deferred", "escalated"]
PolicySeverity = Literal["medium", "high", "critical"]
PolicyTargetKind = Literal["entity", "alert", "metric"]
TriageAction = Literal["accept", "reject", "defer", "escalate"]

# Maps a triage action verb to its resulting item status.
ACTION_TO_STATUS: dict[TriageAction, PolicyItemStatus] = {
    "accept": "accepted",
    "reject": "rejected",
    "defer": "deferred",
    "escalate": "escalated",
}

MatchedValue = str | float | int | bool


class PolicyCitation(BaseModel):
    """A policy/document reference attached to a matched item."""

    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None


class PolicyDisposition(BaseModel):
    """The recorded triage decision for an item."""

    action: TriageAction
    actor: str
    note: str | None = None
    decided_at: datetime
    case_id: str | None = None


class PolicyItem(BaseModel):
    """A durable, KB-scoped policy review item generated by a configured rule."""

    id: str
    knowledge_base_id: str
    rule_id: str
    rule_pack_id: str
    target_kind: PolicyTargetKind
    target_ref: str
    title: str
    severity: PolicySeverity
    matched_fields: dict[str, MatchedValue] = Field(
        default_factory=lambda: cast(dict[str, MatchedValue], {})
    )
    citations: list[PolicyCitation] = Field(
        default_factory=lambda: cast(list[PolicyCitation], [])
    )
    status: PolicyItemStatus = "open"
    disposition: PolicyDisposition | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "ACTION_TO_STATUS",
    "MatchedValue",
    "PolicyCitation",
    "PolicyDisposition",
    "PolicyItem",
    "PolicyItemStatus",
    "PolicySeverity",
    "PolicyTargetKind",
    "TriageAction",
]
```

- [ ] **Step 4: Write `backend/policy/exceptions.py`**

```python
"""Exception hierarchy for the policy module."""

from __future__ import annotations


class PolicyError(Exception):
    """Base exception for policy intelligence failures."""


class PolicyPersistenceError(PolicyError):
    """Raised when a policy item cannot be persisted or read back."""


class PolicyItemNotFoundError(PolicyError):
    """Raised when a policy item is not found within a knowledge base scope."""

    def __init__(self, knowledge_base_id: str, item_id: str) -> None:
        super().__init__(
            f"Policy item '{item_id}' not found in knowledge base '{knowledge_base_id}'."
        )
        self.knowledge_base_id = knowledge_base_id
        self.item_id = item_id


class PolicyItemAlreadyTriagedError(PolicyError):
    """Raised when triaging an item that already carries a disposition."""

    def __init__(self, knowledge_base_id: str, item_id: str) -> None:
        super().__init__(
            f"Policy item '{item_id}' in knowledge base '{knowledge_base_id}' "
            "has already been triaged."
        )
        self.knowledge_base_id = knowledge_base_id
        self.item_id = item_id


__all__ = [
    "PolicyError",
    "PolicyItemAlreadyTriagedError",
    "PolicyItemNotFoundError",
    "PolicyPersistenceError",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_service.py`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/policy/__init__.py backend/policy/models.py backend/policy/exceptions.py backend/tests/policy/__init__.py backend/tests/policy/test_service.py
git commit -m "feat(policy): domain models + exception hierarchy (BL-011)"
```

---

### Task 2: Repository protocol

**Files:**
- Create: `backend/policy/adapters/__init__.py` (empty), `backend/policy/adapters/protocols.py`

- [ ] **Step 1: Write the protocol** (no separate test — exercised via the adapter contract test in Task 3). Create `backend/policy/adapters/__init__.py` empty, then `backend/policy/adapters/protocols.py`:

```python
"""Adapter-level protocol for policy item persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from policy.models import PolicyItem


@runtime_checkable
class PolicyItemRepository(Protocol):
    """Persist and query policy items, scoped by knowledge base.

    Identity is the natural key ``(knowledge_base_id, rule_id, target_ref)``.
    """

    def upsert(self, item: PolicyItem) -> PolicyItem:
        """Insert a new ``open`` item, refresh an existing ``open`` item in place,
        or leave an already-disposed item untouched. Return the stored item."""
        ...

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        """Return one item by its id within a KB scope, or ``None`` if absent."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        """Return a page of items (newest first) plus the total match count."""
        ...

    def update(self, item: PolicyItem) -> PolicyItem:
        """Replace an existing item (matched by natural key); raise
        ``PolicyItemNotFoundError`` if absent. Used to record triage."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all items for a knowledge base; return the count removed."""
        ...


__all__ = ["PolicyItemRepository"]
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && .venv/bin/python -c "from policy.adapters.protocols import PolicyItemRepository; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/policy/adapters/__init__.py backend/policy/adapters/protocols.py
git commit -m "feat(policy): PolicyItemRepository protocol (BL-011)"
```

---

### Task 3: In-memory repository

**Files:**
- Create: `backend/policy/adapters/in_memory.py`
- Test: `backend/tests/policy/test_in_memory_store.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from datetime import timedelta

from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.exceptions import PolicyItemNotFoundError
from policy.models import PolicyDisposition, PolicyItem
from shared.utils import utc_now

import pytest


def _item(*, item_id: str, rule_id: str = "rule-1", target_ref: str = "claim-1",
          kb: str = "kb-1", status: str = "open") -> PolicyItem:
    now = utc_now()
    return PolicyItem(
        id=item_id, knowledge_base_id=kb, rule_id=rule_id, rule_pack_id="pack-1",
        target_kind="entity", target_ref=target_ref, title="t", severity="high",
        matched_fields={"billed_amount": 1000.0}, citations=[], status=status,  # type: ignore[arg-type]
        created_at=now, updated_at=now,
    )


def test_upsert_inserts_then_refreshes_open_item_in_place() -> None:
    repo = InMemoryPolicyItemRepository()
    first = repo.upsert(_item(item_id="a"))
    # Same natural key, new id/value — should refresh in place, keep the first id.
    refreshed = repo.upsert(
        _item(item_id="b").model_copy(update={"matched_fields": {"billed_amount": 2000.0}})
    )
    assert refreshed.id == "a"
    assert refreshed.matched_fields == {"billed_amount": 2000.0}
    items, total = repo.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1


def test_upsert_does_not_reopen_a_disposed_item() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a"))
    stored = repo.get(knowledge_base_id="kb-1", item_id="a")
    assert stored is not None
    repo.update(stored.model_copy(update={
        "status": "accepted",
        "disposition": PolicyDisposition(action="accept", actor="x", decided_at=utc_now()),
    }))
    # A later matching evaluation must NOT reopen it.
    result = repo.upsert(_item(item_id="c"))
    assert result.status == "accepted"


def test_list_filters_by_status_and_sorts_newest_first() -> None:
    repo = InMemoryPolicyItemRepository()
    older = _item(item_id="a", target_ref="claim-1")
    newer = _item(item_id="b", target_ref="claim-2").model_copy(
        update={"updated_at": older.updated_at + timedelta(minutes=5)}
    )
    repo.upsert(older)
    repo.upsert(newer)
    open_items, total = repo.list(knowledge_base_id="kb-1", limit=10, offset=0, status="open")
    assert total == 2
    assert [i.id for i in open_items] == ["b", "a"]
    none_accepted, total2 = repo.list(knowledge_base_id="kb-1", limit=10, offset=0, status="accepted")
    assert (none_accepted, total2) == ([], 0)


def test_update_missing_raises() -> None:
    repo = InMemoryPolicyItemRepository()
    with pytest.raises(PolicyItemNotFoundError):
        repo.update(_item(item_id="ghost"))


def test_delete_by_kb_removes_only_that_kb() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", kb="kb-1"))
    repo.upsert(_item(item_id="b", kb="kb-2", rule_id="r2"))
    removed = repo.delete_by_kb("kb-1")
    assert removed == 1
    assert repo.list(knowledge_base_id="kb-1", limit=10, offset=0)[1] == 0
    assert repo.list(knowledge_base_id="kb-2", limit=10, offset=0)[1] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_in_memory_store.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy.adapters.in_memory'`.

- [ ] **Step 3: Write `backend/policy/adapters/in_memory.py`**

```python
"""In-memory policy item repository for tests and local development."""

from __future__ import annotations

from policy.exceptions import PolicyItemNotFoundError
from policy.models import PolicyItem

__all__ = ["InMemoryPolicyItemRepository"]

# Natural identity: (knowledge_base_id, rule_id, target_ref).
_Key = tuple[str, str, str]


def _key(item: PolicyItem) -> _Key:
    return (item.knowledge_base_id, item.rule_id, item.target_ref)


class InMemoryPolicyItemRepository:
    """A dict-backed ``PolicyItemRepository`` keyed by the natural identity."""

    def __init__(self) -> None:
        self._items: dict[_Key, PolicyItem] = {}

    def upsert(self, item: PolicyItem) -> PolicyItem:
        key = _key(item)
        existing = self._items.get(key)
        if existing is None:
            self._items[key] = item
            return item
        if existing.status != "open":
            # Disposed items are never reopened by re-evaluation.
            return existing
        refreshed = existing.model_copy(
            update={
                "title": item.title,
                "severity": item.severity,
                "matched_fields": item.matched_fields,
                "citations": item.citations,
                "updated_at": item.updated_at,
            }
        )
        self._items[key] = refreshed
        return refreshed

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        for item in self._items.values():
            if item.knowledge_base_id == knowledge_base_id and item.id == item_id:
                return item
        return None

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        matches = [
            item
            for item in self._items.values()
            if item.knowledge_base_id == knowledge_base_id
            and (status is None or item.status == status)
        ]
        matches.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def update(self, item: PolicyItem) -> PolicyItem:
        key = _key(item)
        if key not in self._items:
            raise PolicyItemNotFoundError(item.knowledge_base_id, item.id)
        self._items[key] = item
        return item

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._items if key[0] == knowledge_base_id]
        for key in keys:
            del self._items[key]
        return len(keys)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_in_memory_store.py`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/policy/adapters/in_memory.py backend/tests/policy/test_in_memory_store.py
git commit -m "feat(policy): in-memory repository with upsert/no-reopen semantics (BL-011)"
```

---

### Task 4: PolicyService (upsert + triage lifecycle)

**Files:**
- Create: `backend/policy/service.py`
- Test: `backend/tests/policy/test_service.py` (append to the file from Task 1)

- [ ] **Step 1: Append the failing tests** to `backend/tests/policy/test_service.py`:

```python
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.exceptions import PolicyItemAlreadyTriagedError, PolicyItemNotFoundError
from policy.service import create_policy_service

import pytest


def _service() -> tuple[object, InMemoryPolicyItemRepository]:
    repo = InMemoryPolicyItemRepository()
    return create_policy_service(repo), repo


def test_record_match_creates_open_item() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1",
        title="Claim claim-1 over threshold", severity="high",
        matched_fields={"billed_amount": 1500.0}, citations=[],
    )
    assert item.status == "open"
    assert item.id  # generated


def test_triage_records_disposition_and_status() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    triaged = service.triage(
        knowledge_base_id="kb-1", item_id=item.id, action="accept", actor="ana", note="ok",
    )
    assert triaged.status == "accepted"
    assert triaged.disposition is not None
    assert triaged.disposition.actor == "ana"


def test_triage_escalate_stores_case_id() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    triaged = service.triage(
        knowledge_base_id="kb-1", item_id=item.id, action="escalate",
        actor="ana", case_id="case-9",
    )
    assert triaged.status == "escalated"
    assert triaged.disposition is not None and triaged.disposition.case_id == "case-9"


def test_triage_missing_item_raises_not_found() -> None:
    service, _ = _service()
    with pytest.raises(PolicyItemNotFoundError):
        service.triage(knowledge_base_id="kb-1", item_id="nope", action="accept", actor="ana")


def test_triage_already_disposed_raises_conflict() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    service.triage(knowledge_base_id="kb-1", item_id=item.id, action="accept", actor="ana")
    with pytest.raises(PolicyItemAlreadyTriagedError):
        service.triage(knowledge_base_id="kb-1", item_id=item.id, action="reject", actor="ana")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_service.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy.service'`.

- [ ] **Step 3: Write `backend/policy/service.py`**

```python
"""Policy intelligence orchestration over a durable repository."""

from __future__ import annotations

from policy.adapters.protocols import PolicyItemRepository
from policy.exceptions import PolicyItemAlreadyTriagedError, PolicyItemNotFoundError
from policy.models import (
    ACTION_TO_STATUS,
    MatchedValue,
    PolicyCitation,
    PolicyDisposition,
    PolicyItem,
    PolicySeverity,
    PolicyTargetKind,
    TriageAction,
)
from shared.utils import generate_id, utc_now

__all__ = ["PolicyService", "create_policy_service"]


class PolicyService:
    """Upsert rule-generated items and record analyst triage (KB-scoped)."""

    def __init__(self, repository: PolicyItemRepository) -> None:
        self._repository = repository

    def record_match(
        self,
        *,
        knowledge_base_id: str,
        rule_id: str,
        rule_pack_id: str,
        target_kind: PolicyTargetKind,
        target_ref: str,
        title: str,
        severity: PolicySeverity,
        matched_fields: dict[str, MatchedValue],
        citations: list[PolicyCitation],
    ) -> PolicyItem:
        now = utc_now()
        item = PolicyItem(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            rule_id=rule_id,
            rule_pack_id=rule_pack_id,
            target_kind=target_kind,
            target_ref=target_ref,
            title=title,
            severity=severity,
            matched_fields=dict(matched_fields),
            citations=list(citations),
            status="open",
            created_at=now,
            updated_at=now,
        )
        return self._repository.upsert(item)

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        return self._repository.get(knowledge_base_id=knowledge_base_id, item_id=item_id)

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        return self._repository.list(
            knowledge_base_id=knowledge_base_id, limit=limit, offset=offset, status=status
        )

    def triage(
        self,
        *,
        knowledge_base_id: str,
        item_id: str,
        action: TriageAction,
        actor: str,
        note: str | None = None,
        case_id: str | None = None,
    ) -> PolicyItem:
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, item_id=item_id
        )
        if existing is None:
            raise PolicyItemNotFoundError(knowledge_base_id, item_id)
        if existing.status != "open":
            raise PolicyItemAlreadyTriagedError(knowledge_base_id, item_id)
        disposition = PolicyDisposition(
            action=action, actor=actor, note=note, decided_at=utc_now(), case_id=case_id
        )
        updated = existing.model_copy(
            update={
                "status": ACTION_TO_STATUS[action],
                "disposition": disposition,
                "updated_at": disposition.decided_at,
            }
        )
        return self._repository.update(updated)


def create_policy_service(repository: PolicyItemRepository) -> PolicyService:
    """Create the default policy service."""
    return PolicyService(repository)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_service.py`
Expected: PASS (7 passed — 2 model + 5 service).

- [ ] **Step 5: Typecheck + lint the new module**

Run: `cd backend && .venv/bin/pyright policy && .venv/bin/ruff check --no-cache policy tests/policy`
Expected: 0 errors, all checks pass. (Bare `pyright` is run at the end of the phase; `policy/` must be added to `tool.pyright.include` — see Task 5.)

- [ ] **Step 6: Commit**

```bash
git add backend/policy/service.py backend/tests/policy/test_service.py
git commit -m "feat(policy): PolicyService upsert + triage lifecycle (BL-011)"
```

---

### Task 5: Add `policy/` to the strict pyright scope

**Files:**
- Modify: `backend/pyproject.toml` (the `[tool.pyright].include` array)

- [ ] **Step 1: Read the current include list**

Run: `cd backend && .venv/bin/python -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['tool']['pyright']['include'])"`
Expected: a list of module/test paths (e.g. `["cases", "records", "tests/policy", ...]`).

- [ ] **Step 2: Add `"policy"` and `"tests/policy"`** to `[tool.pyright].include` in `backend/pyproject.toml` (alphabetical-ish, matching the existing style — insert `"policy"` near `"monitoring"`/`"rag"` and `"tests/policy"` near the other `tests/*` entries).

- [ ] **Step 3: Run the real gate**

Run: `cd backend && .venv/bin/pyright`
Expected: 0 errors, 0 warnings (the pre-existing `analytics/gnn`+`analytics/timeseries` untyped-third-party notes, if any, are unchanged — do not introduce new ones).

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(policy): add policy/ to strict pyright scope (BL-011)"
```

---

# Phase 2 — Config rule packs

### Task 6: Policy rule-pack config models + `DomainConfig.policy_rules`

**Files:**
- Modify: `backend/config/schema.py`
- Test: `backend/tests/config/test_policy_rules_schema.py` (new)

- [ ] **Step 1: Write the failing test** — create `backend/tests/config/test_policy_rules_schema.py`:

```python
from __future__ import annotations

import pytest

from config.schema import (
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)


def test_predicate_value_requires_exactly_one_source() -> None:
    with pytest.raises(ValueError):
        PolicyPredicateValue()  # neither literal nor config_ref
    with pytest.raises(ValueError):
        PolicyPredicateValue(literal=1, config_ref="x")  # both
    assert PolicyPredicateValue(literal=1200).literal == 1200
    assert PolicyPredicateValue(config_ref="amt_threshold").config_ref == "amt_threshold"


def test_rule_pack_round_trips() -> None:
    pack = PolicyRulePack(
        id="billing",
        name="Billing thresholds",
        thresholds={"amt_threshold": 1000.0},
        rules=[
            PolicyRule(
                id="over_billed",
                title_template="Claim {target_ref} exceeds the billing threshold",
                severity="high",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.billed_amount",
                    op="gt",
                    value=PolicyPredicateValue(config_ref="amt_threshold"),
                ),
            )
        ],
    )
    assert pack.rules[0].predicate.op == "gt"
    assert pack.thresholds["amt_threshold"] == 1000.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/config/test_policy_rules_schema.py`
Expected: FAIL — `ImportError: cannot import name 'PolicyPredicate' from 'config.schema'`.

- [ ] **Step 3: Add the models to `backend/config/schema.py`** — insert just above the `DomainConfig` class definition:

```python
class PolicyPredicateValue(BaseModel):
    """A predicate's right-hand value: exactly one of an inline literal or a
    ``config_ref`` resolving against the owning pack's ``thresholds`` map."""

    literal: str | float | int | bool | list[str] | None = None
    config_ref: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> PolicyPredicateValue:
        has_literal = self.literal is not None
        has_ref = self.config_ref is not None
        if has_literal == has_ref:
            raise ValueError(
                "PolicyPredicateValue requires exactly one of 'literal' or 'config_ref'."
            )
        return self


class PolicyPredicate(BaseModel):
    """A single bounded comparison evaluated against a target's field."""

    field: str  # "properties.<name>" | "risk_score" | "metric.<name>"
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"]
    value: PolicyPredicateValue


class PolicyCitationRef(BaseModel):
    """A policy/document reference surfaced on every item a rule generates."""

    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None


class PolicyRule(BaseModel):
    """A single rule: select targets, test one predicate, emit an item per hit."""

    id: str
    title_template: str
    severity: Literal["medium", "high", "critical"]
    target_kind: Literal["entity", "alert", "metric"]
    target_selector: dict[str, str] = Field(default_factory=lambda: cast(dict[str, str], {}))
    predicate: PolicyPredicate
    citations: list[PolicyCitationRef] = Field(
        default_factory=lambda: cast(list[PolicyCitationRef], [])
    )


class PolicyRulePack(BaseModel):
    """A named bundle of rules with shared, config-referenceable thresholds."""

    id: str
    name: str
    description: str | None = None
    thresholds: dict[str, str | float | int | bool] = Field(
        default_factory=lambda: cast(dict[str, str | float | int | bool], {})
    )
    rules: list[PolicyRule] = Field(default_factory=lambda: cast(list[PolicyRule], []))
```

Then add the field to `DomainConfig` (next to `records` / `analytics`):

```python
    policy_rules: list[PolicyRulePack] = Field(
        default_factory=lambda: cast(list[PolicyRulePack], [])
    )
```

Add `"PolicyCitationRef"`, `"PolicyPredicate"`, `"PolicyPredicateValue"`, `"PolicyRule"`, `"PolicyRulePack"` to the module `__all__`. (Confirm `model_validator`, `Literal`, and `cast` are already imported at the top of `schema.py` — they are used elsewhere in the file; add any that are missing.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/config/test_policy_rules_schema.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Typecheck + lint**

Run: `cd backend && .venv/bin/pyright config tests/config && .venv/bin/ruff check --no-cache config tests/config`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_policy_rules_schema.py
git commit -m "feat(config): policy_rules rule-pack schema on DomainConfig (BL-011)"
```

---

### Task 7: Ship example rule packs in the default configs + loader test

**Files:**
- Modify: `backend/config/defaults/medicare_fraud.yaml`, `backend/config/defaults/medicare_fraud_dev.yaml`
- Modify: `backend/tests/config/test_loader.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/config/test_loader.py`:

```python
def test_medicare_ships_policy_rules() -> None:
    cfg = load_config(MEDICARE_YAML)
    assert cfg.policy_rules, "medicare_fraud.yaml must ship at least one policy rule pack"
    rule = cfg.policy_rules[0].rules[0]
    assert rule.predicate.op in {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"}


def test_food_supply_loads_without_policy_rules() -> None:
    cfg = load_config(DEFAULTS_DIR / "food_supply_chain.yaml")
    assert cfg.policy_rules == []  # additive/optional — absent block defaults to []
```

(If `MEDICARE_YAML` / `DEFAULTS_DIR` are not already module-level constants in this test file, reuse the existing ones — they are referenced by `test_load_medicare_yaml` and `_all_default_yamls`.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/config/test_loader.py -k policy_rules`
Expected: FAIL — `test_medicare_ships_policy_rules` fails (`cfg.policy_rules` is empty).

- [ ] **Step 3: Add a `policy_rules:` block** to `backend/config/defaults/medicare_fraud.yaml` (top level, after the `records:` block):

```yaml
policy_rules:
  - id: billing_thresholds
    name: "Billing thresholds"
    description: "Flag claims whose billed amount exceeds the configured ceiling."
    thresholds:
      max_billed_amount: 5000
    rules:
      - id: claim_over_billed
        title_template: "Claim {target_ref} exceeds the billing threshold"
        severity: high
        target_kind: entity
        target_selector:
          entity_type: claim
        predicate:
          field: properties.amount
          op: gt
          value:
            config_ref: max_billed_amount
        citations:
          - citation_id: lcd-billing-001
            title: "LCD billing-amount guidance"
            source_ref: "policy://medicare/lcd/billing-001"
            excerpt: "Claims above the LCD ceiling require documented justification."
  - id: graph_scale
    name: "Graph growth watch"
    thresholds:
      max_entities: 100000
    rules:
      - id: kb_entity_volume
        title_template: "Knowledge base {target_ref} crossed the entity-volume watch line"
        severity: medium
        target_kind: metric
        target_selector:
          metric_name: entity_count
        predicate:
          field: metric.entity_count
          op: gt
          value:
            config_ref: max_entities
```

Apply the **same block** to `backend/config/defaults/medicare_fraud_dev.yaml` but set `thresholds.max_billed_amount: 100` (low, so the dev/e2e seed easily trips it). Leave `food_supply_chain.yaml` untouched (verifies the optional path).

> The `properties.amount` field matches the claim entity property mapped by the existing `claims_feed` (`amount: billed_amount`). Confirm against `records.feeds[].entities[].property_fields` in the same file; if the claim amount property is named differently there, use that exact name.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/config/test_loader.py`
Expected: PASS (all default-config tests green, including the parametrized `test_all_defaults_load_successfully`).

- [ ] **Step 5: Commit**

```bash
git add backend/config/defaults/medicare_fraud.yaml backend/config/defaults/medicare_fraud_dev.yaml backend/tests/config/test_loader.py
git commit -m "feat(config): ship example Medicare policy rule packs (BL-011)"
```

---

# Phase 3 — Rule evaluator (pure function)

### Task 8: `policy/evaluation.py`

**Files:**
- Create: `backend/policy/evaluation.py`
- Test: `backend/tests/policy/test_evaluation.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from config.schema import (
    PolicyCitationRef,
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)
from policy.evaluation import PolicyEvalState, evaluate
from shared.types import Entity


def _claim(entity_id: str, amount: float) -> Entity:
    return Entity(id=entity_id, type="claim", properties={"amount": amount})


def _pack() -> PolicyRulePack:
    return PolicyRulePack(
        id="billing",
        name="Billing thresholds",
        thresholds={"max_billed_amount": 1000.0},
        rules=[
            PolicyRule(
                id="claim_over_billed",
                title_template="Claim {target_ref} exceeds the billing threshold",
                severity="high",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.amount",
                    op="gt",
                    value=PolicyPredicateValue(config_ref="max_billed_amount"),
                ),
                citations=[
                    PolicyCitationRef(
                        citation_id="c1", title="LCD", source_ref="policy://x"
                    )
                ],
            )
        ],
    )


def test_entity_predicate_emits_one_match_per_hit() -> None:
    state = PolicyEvalState(
        entities=[_claim("claim-1", 1500.0), _claim("claim-2", 500.0)], alerts=[], metrics={}
    )
    matches = evaluate([_pack()], state)
    assert len(matches) == 1
    match = matches[0]
    assert match.target_ref == "claim-1"
    assert match.rule_id == "claim_over_billed"
    assert match.title == "Claim claim-1 exceeds the billing threshold"
    assert match.matched_fields == {"properties.amount": 1500.0}
    assert match.citations[0].citation_id == "c1"


def test_metric_predicate_matches_metric_value() -> None:
    pack = PolicyRulePack(
        id="scale", name="scale", thresholds={"max_entities": 100.0},
        rules=[
            PolicyRule(
                id="kb_volume", title_template="KB {target_ref} large", severity="medium",
                target_kind="metric", target_selector={"metric_name": "entity_count"},
                predicate=PolicyPredicate(
                    field="metric.entity_count", op="gt",
                    value=PolicyPredicateValue(config_ref="max_entities"),
                ),
            )
        ],
    )
    state = PolicyEvalState(entities=[], alerts=[], metrics={"entity_count": 250.0})
    matches = evaluate([pack], state)
    assert len(matches) == 1
    assert matches[0].target_ref == "entity_count"


def test_in_operator_with_literal_list() -> None:
    pack = PolicyRulePack(
        id="states", name="states", thresholds={},
        rules=[
            PolicyRule(
                id="watch_states", title_template="Claim {target_ref} in watch state",
                severity="medium", target_kind="entity", target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.state", op="in",
                    value=PolicyPredicateValue(literal=["FL", "TX"]),
                ),
            )
        ],
    )
    state = PolicyEvalState(
        entities=[
            Entity(id="claim-1", type="claim", properties={"state": "FL"}),
            Entity(id="claim-2", type="claim", properties={"state": "CA"}),
        ], alerts=[], metrics={},
    )
    matches = evaluate([pack], state)
    assert [m.target_ref for m in matches] == ["claim-1"]


def test_no_match_when_field_absent() -> None:
    pack = _pack()
    state = PolicyEvalState(
        entities=[Entity(id="claim-3", type="claim", properties={})], alerts=[], metrics={}
    )
    assert evaluate([pack], state) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_evaluation.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy.evaluation'`.

- [ ] **Step 3: Write `backend/policy/evaluation.py`**

```python
"""Pure evaluation of configured policy rule packs against KB state.

No I/O: ``evaluate(rule_packs, state) -> list[PolicyMatch]``. The worker calls
this with freshly-stored entities and (throttled) graph metrics; the result is
upserted as durable policy items.
"""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from pydantic import BaseModel, Field

from config.schema import (
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)
from policy.models import MatchedValue, PolicyCitation, PolicySeverity, PolicyTargetKind
from shared.types import Alert, Entity

__all__ = ["PolicyEvalState", "PolicyMatch", "evaluate"]


class PolicyEvalState(BaseModel):
    """The KB-scoped state a rule pack is evaluated against."""

    entities: list[Entity] = Field(default_factory=lambda: cast(list[Entity], []))
    alerts: list[Alert] = Field(default_factory=lambda: cast(list[Alert], []))
    metrics: dict[str, float] = Field(default_factory=lambda: cast(dict[str, float], {}))


class PolicyMatch(BaseModel):
    """A single rule hit, ready to be upserted as a ``PolicyItem``."""

    rule_id: str
    rule_pack_id: str
    target_kind: PolicyTargetKind
    target_ref: str
    title: str
    severity: PolicySeverity
    matched_fields: dict[str, MatchedValue]
    citations: list[PolicyCitation]


def evaluate(rule_packs: list[PolicyRulePack], state: PolicyEvalState) -> list[PolicyMatch]:
    matches: list[PolicyMatch] = []
    for pack in rule_packs:
        for rule in pack.rules:
            matches.extend(_evaluate_rule(pack, rule, state))
    return matches


def _evaluate_rule(
    pack: PolicyRulePack, rule: PolicyRule, state: PolicyEvalState
) -> list[PolicyMatch]:
    resolved = _resolve_value(pack, rule.predicate.value)
    out: list[PolicyMatch] = []
    for target_ref, field_value in _iter_targets(rule, state):
        if field_value is None:
            continue
        if _apply(rule.predicate.op, field_value, resolved):
            out.append(
                PolicyMatch(
                    rule_id=rule.id,
                    rule_pack_id=pack.id,
                    target_kind=rule.target_kind,
                    target_ref=target_ref,
                    title=_render_title(rule.title_template, target_ref),
                    severity=rule.severity,
                    matched_fields={rule.predicate.field: _as_matched(field_value)},
                    citations=[
                        PolicyCitation(
                            citation_id=c.citation_id,
                            title=c.title,
                            source_ref=c.source_ref,
                            excerpt=c.excerpt,
                        )
                        for c in rule.citations
                    ],
                )
            )
    return out


def _iter_targets(
    rule: PolicyRule, state: PolicyEvalState
) -> list[tuple[str, object | None]]:
    """Yield ``(target_ref, field_value)`` pairs for a rule's selected targets."""

    if rule.target_kind == "entity":
        wanted = rule.target_selector.get("entity_type")
        return [
            (entity.id, _entity_field(entity, rule.predicate.field))
            for entity in state.entities
            if wanted is None or entity.type == wanted
        ]
    if rule.target_kind == "metric":
        name = rule.target_selector.get("metric_name", "")
        if name not in state.metrics:
            return []
        return [(name, state.metrics[name])]
    # target_kind == "alert": defined but not evaluated in v1 (documented non-goal).
    return []


def _entity_field(entity: Entity, field: str) -> object | None:
    if field.startswith("properties."):
        return entity.properties.get(field.split(".", 1)[1])
    if field == "risk_score":
        return entity.properties.get("risk_score")
    return None


def _resolve_value(pack: PolicyRulePack, value: PolicyPredicateValue) -> object:
    if value.config_ref is not None:
        return pack.thresholds[value.config_ref]
    return value.literal


def _apply(op: str, left: object, right: object) -> bool:
    if op == "in":
        return left in _as_list(right)
    if op == "not_in":
        return left not in _as_list(right)
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    left_n, right_n = _as_float(left), _as_float(right)
    if left_n is None or right_n is None:
        return False
    if op == "gt":
        return left_n > right_n
    if op == "gte":
        return left_n >= right_n
    if op == "lt":
        return left_n < right_n
    if op == "lte":
        return left_n <= right_n
    return False


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_matched(value: object) -> MatchedValue:
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _render_title(template: str, target_ref: str) -> str:
    safe: defaultdict[str, str] = defaultdict(str)
    safe["target_ref"] = target_ref
    return template.format_map(safe)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/policy/test_evaluation.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Typecheck + lint**

Run: `cd backend && .venv/bin/pyright policy tests/policy && .venv/bin/ruff check --no-cache policy tests/policy`
Expected: 0 errors. (Confirm `Alert` and `Entity` field names used in tests match `shared/types.py`; adjust the test constructors if the real `Entity`/`Alert` signatures differ.)

- [ ] **Step 6: Commit**

```bash
git add backend/policy/evaluation.py backend/tests/policy/test_evaluation.py
git commit -m "feat(policy): pure rule evaluator over entity/metric state (BL-011)"
```

---

# Phase 4 — Persistence (migration + Postgres adapter)

### Task 9: Alembic migration `0003_policy`

**Files:**
- Create: `backend/database/migrations/versions/0003_policy.py`

- [ ] **Step 1: Write the migration** (no unit test — exercised by the integration test in Task 10):

```python
"""Policy items table for durable, KB-scoped policy intelligence (BL-011).

Backs ``policy.adapters.postgres.PostgresPolicyItemRepository``.

Revision ID: 0003_policy
Revises: 0002_cases
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_policy"
down_revision: str | None = "0002_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE policy_items (
            knowledge_base_id text        NOT NULL,
            rule_id           text        NOT NULL,
            target_ref        text        NOT NULL,
            item_id           text        NOT NULL,
            rule_pack_id      text        NOT NULL,
            target_kind       text        NOT NULL,
            title             text        NOT NULL,
            severity          text        NOT NULL,
            matched_fields    jsonb       NOT NULL DEFAULT '{}'::jsonb,
            citations         jsonb       NOT NULL DEFAULT '[]'::jsonb,
            status            text        NOT NULL,
            disposition       jsonb,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, rule_id, target_ref)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_policy_items_item_id "
        "ON policy_items (knowledge_base_id, item_id)"
    )
    op.execute(
        "CREATE INDEX ix_policy_items_status "
        "ON policy_items (knowledge_base_id, status, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_policy_items_status")
    op.execute("DROP INDEX IF EXISTS ux_policy_items_item_id")
    op.execute("DROP TABLE IF EXISTS policy_items")
```

- [ ] **Step 2: Verify the migration is the new head** (offline check — no DB needed)

Run: `cd backend && .venv/bin/alembic -c database/migrations/alembic.ini heads`
Expected: a single head `0003_policy` (no multiple-heads / branch error). If `alembic.ini` lives elsewhere, use the path referenced by `make dev`'s startup migration step (`df78dbb` wired auto-migrate on api startup — match that config path).

- [ ] **Step 3: Commit**

```bash
git add backend/database/migrations/versions/0003_policy.py
git commit -m "feat(database): 0003_policy migration for policy_items (BL-011)"
```

---

### Task 10: Postgres repository + shared adapter contract test

**Files:**
- Create: `backend/policy/adapters/postgres.py`
- Create: `backend/tests/policy/conftest.py`, `backend/tests/policy/test_postgres_store.py`

- [ ] **Step 1: Write the failing integration test** — `backend/tests/policy/test_postgres_store.py` (mirrors `tests/cases/test_postgres_store.py`; gated `@pytest.mark.integration`, runs against live TimescaleDB):

```python
from __future__ import annotations

import pytest

from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.models import PolicyDisposition, PolicyItem
from shared.utils import utc_now

pytestmark = pytest.mark.integration


def _item(item_id: str, *, target_ref: str = "claim-1", status: str = "open") -> PolicyItem:
    now = utc_now()
    return PolicyItem(
        id=item_id, knowledge_base_id="kb-pg", rule_id="rule-1", rule_pack_id="pack-1",
        target_kind="entity", target_ref=target_ref, title="t", severity="high",
        matched_fields={"properties.amount": 1500.0}, citations=[], status=status,  # type: ignore[arg-type]
        created_at=now, updated_at=now,
    )


def test_upsert_conflict_refreshes_open_but_not_disposed(policy_pg_repo: PostgresPolicyItemRepository) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a"))
    # Same natural key while open -> refresh, keep id "a".
    refreshed = repo.upsert(_item("b").model_copy(update={"matched_fields": {"properties.amount": 9.0}}))
    assert refreshed.id == "a"
    assert refreshed.matched_fields == {"properties.amount": 9.0}

    stored = repo.get(knowledge_base_id="kb-pg", item_id="a")
    assert stored is not None
    repo.update(stored.model_copy(update={
        "status": "accepted",
        "disposition": PolicyDisposition(action="accept", actor="x", decided_at=utc_now()),
    }))
    # Disposed -> upsert must not reopen.
    after = repo.upsert(_item("c"))
    assert after.status == "accepted"


def test_list_filter_and_delete(policy_pg_repo: PostgresPolicyItemRepository) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a", target_ref="claim-1"))
    repo.upsert(_item("b", target_ref="claim-2"))
    items, total = repo.list(knowledge_base_id="kb-pg", limit=10, offset=0, status="open")
    assert total == 2 and len(items) == 2
    assert repo.delete_by_kb("kb-pg") == 2
```

Add a `policy_pg_repo` fixture to `backend/tests/policy/conftest.py` that constructs a `PostgresPolicyItemRepository` from the test `ConnectionProvider` and truncates `policy_items` between tests — **copy the exact provider/cleanup fixture pattern from `backend/tests/cases/conftest.py`** (same DSN env var, same `TRUNCATE` teardown), changing the table name to `policy_items`.

- [ ] **Step 2: Run to verify it fails** (main session)

Run: `docker exec chiliai-api-1 sh -c "python -m pytest -q -m integration tests/policy/test_postgres_store.py"`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy.adapters.postgres'`.

- [ ] **Step 3: Write `backend/policy/adapters/postgres.py`** (mirrors `cases/adapters/postgres.py`: `ConnectionProvider`, `with self._provider.connection()`, `::jsonb` casts, `json.dumps`, row→model decode). Upsert is implemented as select-then-insert/update within one connection so the disposed-row guard and "keep original id/created_at on refresh" semantics exactly match the in-memory adapter:

```python
"""Postgres-backed policy item repository (BL-011)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from policy.exceptions import PolicyItemNotFoundError, PolicyPersistenceError
from policy.models import (
    MatchedValue,
    PolicyCitation,
    PolicyDisposition,
    PolicyItem,
    PolicyItemStatus,
    PolicySeverity,
    PolicyTargetKind,
)

__all__ = ["PostgresPolicyItemRepository"]

_COLUMNS = (
    "knowledge_base_id, rule_id, target_ref, item_id, rule_pack_id, target_kind, "
    "title, severity, matched_fields, citations, status, disposition, created_at, updated_at"
)

_SELECT_BY_KEY = f"""
    SELECT {_COLUMNS} FROM policy_items
    WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""

_SELECT_BY_ID = f"""
    SELECT {_COLUMNS} FROM policy_items
    WHERE knowledge_base_id = %s AND item_id = %s
"""

_INSERT = """
    INSERT INTO policy_items (
        knowledge_base_id, rule_id, target_ref, item_id, rule_pack_id, target_kind,
        title, severity, matched_fields, citations, status, disposition, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s)
"""

_UPDATE_REFRESH = """
    UPDATE policy_items
       SET title = %s, severity = %s, matched_fields = %s::jsonb,
           citations = %s::jsonb, updated_at = %s
     WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""

_UPDATE_FULL = """
    UPDATE policy_items
       SET title = %s, severity = %s, matched_fields = %s::jsonb, citations = %s::jsonb,
           status = %s, disposition = %s::jsonb, updated_at = %s
     WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""


class PostgresPolicyItemRepository:
    """A ``PolicyItemRepository`` backed by the ``policy_items`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert(self, item: PolicyItem) -> PolicyItem:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _SELECT_BY_KEY,
                    (item.knowledge_base_id, item.rule_id, item.target_ref),
                ).fetchone()
                if row is None:
                    conn.execute(_INSERT, _insert_params(item))
                    conn.commit()
                    return item
                existing = _row_to_item(row)
                if existing.status != "open":
                    return existing
                conn.execute(
                    _UPDATE_REFRESH,
                    (
                        item.title,
                        item.severity,
                        json.dumps(item.matched_fields, default=str),
                        _citations_json(item.citations),
                        item.updated_at,
                        item.knowledge_base_id,
                        item.rule_id,
                        item.target_ref,
                    ),
                )
                conn.commit()
                return existing.model_copy(
                    update={
                        "title": item.title,
                        "severity": item.severity,
                        "matched_fields": item.matched_fields,
                        "citations": item.citations,
                        "updated_at": item.updated_at,
                    }
                )
        except PolicyPersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to upsert policy item.") from exc

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_SELECT_BY_ID, (knowledge_base_id, item_id)).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to read policy item.") from exc
        return None if row is None else _row_to_item(row)

    def list(
        self, *, knowledge_base_id: str, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[PolicyItem], int]:
        where = "WHERE knowledge_base_id = %s"
        params: list[object] = [knowledge_base_id]
        if status is not None:
            where += " AND status = %s"
            params.append(status)
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM policy_items {where}", tuple(params)
                ).fetchone()
                total = int(total_row[0]) if total_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM policy_items {where} "
                    "ORDER BY updated_at DESC, item_id DESC LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to list policy items.") from exc
        return [_row_to_item(row) for row in rows], total

    def update(self, item: PolicyItem) -> PolicyItem:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _UPDATE_FULL,
                    (
                        item.title,
                        item.severity,
                        json.dumps(item.matched_fields, default=str),
                        _citations_json(item.citations),
                        item.status,
                        _disposition_json(item.disposition),
                        item.updated_at,
                        item.knowledge_base_id,
                        item.rule_id,
                        item.target_ref,
                    ),
                )
                if cursor.rowcount == 0:
                    raise PolicyItemNotFoundError(item.knowledge_base_id, item.id)
                conn.commit()
        except PolicyItemNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to update policy item.") from exc
        return item

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM policy_items WHERE knowledge_base_id = %s",
                    (knowledge_base_id,),
                )
                conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to delete policy items.") from exc


def _insert_params(item: PolicyItem) -> tuple[object, ...]:
    return (
        item.knowledge_base_id,
        item.rule_id,
        item.target_ref,
        item.id,
        item.rule_pack_id,
        item.target_kind,
        item.title,
        item.severity,
        json.dumps(item.matched_fields, default=str),
        _citations_json(item.citations),
        item.status,
        _disposition_json(item.disposition),
        item.created_at,
        item.updated_at,
    )


def _citations_json(citations: list[PolicyCitation]) -> str:
    return json.dumps([c.model_dump(mode="json") for c in citations])


def _disposition_json(disposition: PolicyDisposition | None) -> str | None:
    return None if disposition is None else json.dumps(disposition.model_dump(mode="json"))


def _row_to_item(row: Row) -> PolicyItem:
    return PolicyItem(
        knowledge_base_id=cast(str, row[0]),
        rule_id=cast(str, row[1]),
        target_ref=cast(str, row[2]),
        id=cast(str, row[3]),
        rule_pack_id=cast(str, row[4]),
        target_kind=cast(PolicyTargetKind, row[5]),
        title=cast(str, row[6]),
        severity=cast(PolicySeverity, row[7]),
        matched_fields=_decode_matched(row[8]),
        citations=_decode_citations(row[9]),
        status=cast(PolicyItemStatus, row[10]),
        disposition=_decode_disposition(row[11]),
        created_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
    )


def _as_obj(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _decode_matched(value: object) -> dict[str, MatchedValue]:
    return cast(dict[str, MatchedValue], _as_obj(value) or {})


def _decode_citations(value: object) -> list[PolicyCitation]:
    return [PolicyCitation.model_validate(c) for c in cast(list[object], _as_obj(value) or [])]


def _decode_disposition(value: object) -> PolicyDisposition | None:
    obj = _as_obj(value)
    return None if obj is None else PolicyDisposition.model_validate(obj)
```

- [ ] **Step 4: Run the integration test to verify it passes** (main session)

Run: `docker exec chiliai-api-1 sh -c "python -m pytest -q -m integration tests/policy/test_postgres_store.py"`
Expected: PASS (2 passed). (If the migration hasn't been applied in the container, restart it — `df78dbb` auto-runs alembic on api startup — or run the alembic upgrade step the startup uses.)

- [ ] **Step 5: Typecheck + lint**

Run: `cd backend && .venv/bin/pyright policy tests/policy && .venv/bin/ruff check --no-cache policy tests/policy`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/policy/adapters/postgres.py backend/tests/policy/conftest.py backend/tests/policy/test_postgres_store.py
git commit -m "feat(policy): Postgres repository + live-DB contract tests (BL-011)"
```

---

# Phase 5 — Worker evaluation

### Task 11: Additive `timeline` param on `CaseService.create` (enables escalate)

**Files:**
- Modify: `backend/cases/service.py`
- Test: `backend/tests/cases/test_service.py` (append)

- [ ] **Step 1: Append the failing test** to `backend/tests/cases/test_service.py`:

```python
def test_create_accepts_optional_timeline() -> None:
    from cases.adapters.in_memory import InMemoryCaseRepository
    from cases.models import CaseTimelineEvent
    from cases.service import create_case_service
    from shared.utils import utc_now

    service = create_case_service(InMemoryCaseRepository())
    event = CaseTimelineEvent(occurred_at=utc_now(), label="Policy escalation", detail="rule x")
    case = service.create(
        knowledge_base_id="kb-1", title="Policy escalation: t", priority="high",
        timeline=[event],
    )
    assert case.timeline == [event]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/cases/test_service.py -k optional_timeline`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'timeline'`.

- [ ] **Step 3: Add the param** to `CaseService.create` in `backend/cases/service.py` — add `timeline: list[CaseTimelineEvent] | None = None,` to the signature and `timeline=list(timeline or []),` to the `Case(...)` constructor. (`CaseTimelineEvent` is already imported in that file.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/cases/test_service.py`
Expected: PASS (all cases service tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/cases/service.py backend/tests/cases/test_service.py
git commit -m "feat(cases): additive timeline param on create (enables policy escalate, BL-011)"
```

---

### Task 12: Fold policy evaluation into the worker (`handle_records_ingested`)

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_policy_evaluation_stage.py` (new)

- [ ] **Step 1: Write the failing test** — `backend/tests/agent/test_policy_evaluation_stage.py`. It drives `handle_records_ingested` with a stub graph service that returns one over-threshold claim entity, a real `InMemoryPolicyItemRepository`+`PolicyService`, and asserts one open item is produced. Model it on the existing `tests/agent/test_records_ingested*` handler tests (reuse their stub builders for `records_config`, `raw_record_store`, `graph_service`, `observation_writer`). The new assertion:

```python
def test_records_ingested_generates_policy_items(/* reuse existing fixtures */) -> None:
    # ...arrange: feed config maps a 'claim' entity with property 'amount';
    # graph_service.upsert_records_graph returns [Entity(id="claim-1", type="claim",
    #   properties={"amount": 1500.0})]; policy_rules = a billing pack with
    #   threshold 1000 (see Task 8 test for the pack shape); policy_service wraps
    #   an InMemoryPolicyItemRepository.
    handle_records_ingested(
        event,
        records_config=records_config,
        raw_record_store=raw_record_store,
        graph_service=graph_service,
        observation_writer=observation_writer,
        policy_rules=[billing_pack],
        policy_service=policy_service,
    )
    items, total = policy_service.list(knowledge_base_id=event.knowledge_base_id, limit=10, offset=0)
    assert total == 1
    assert items[0].rule_id == "claim_over_billed"
    assert items[0].status == "open"


def test_policy_evaluation_is_skipped_when_unwired(/* fixtures */) -> None:
    # policy_service=None -> no crash, returns the record count as before.
    result = handle_records_ingested(event, records_config=records_config,
        raw_record_store=raw_record_store, graph_service=graph_service,
        observation_writer=observation_writer)
    assert result >= 0
```

> Read the existing `tests/agent/` records-ingested test to copy the exact stub constructors (the spec'd pseudo-comments above must become real fixtures before this compiles — no placeholder fixtures in the committed test).

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/agent/test_policy_evaluation_stage.py`
Expected: FAIL — `handle_records_ingested() got an unexpected keyword argument 'policy_service'`.

- [ ] **Step 3: Extend `handle_records_ingested`** in `backend/agent/coordinator.py`. Add two optional params and an evaluation step after `stored_entities` are upserted (uses the already-imported `graph_service.compute_metrics`; reuses `metrics_throttle` so metric predicates don't thrash):

```python
def handle_records_ingested(
    event: RecordsIngestedEvent,
    *,
    records_config: RecordsConfig,
    raw_record_store: RawRecordStore,
    graph_service: GraphService,
    observation_writer: ObservationWriter,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    policy_rules: list[PolicyRulePack] | None = None,      # NEW
    policy_service: PolicyService | None = None,           # NEW
    metrics_throttle: MetricsRecomputeThrottle | None = None,  # NEW (for metric predicates)
) -> int:
    # ... existing body through `stored_entities, _ = graph_service.upsert_records_graph(...)`
    # ... existing embeddings + observations blocks unchanged ...

    if policy_service is not None and policy_rules:
        _evaluate_policy_rules(
            event=event,
            policy_rules=policy_rules,
            policy_service=policy_service,
            entities=stored_entities,
            graph_service=graph_service,
            metrics_throttle=metrics_throttle,
        )
    return len(records)


def _evaluate_policy_rules(
    *,
    event: RecordsIngestedEvent,
    policy_rules: list[PolicyRulePack],
    policy_service: PolicyService,
    entities: list[Entity],
    graph_service: GraphService,
    metrics_throttle: MetricsRecomputeThrottle | None,
) -> None:
    """Flow P — evaluate configured rules over the freshly-stored entities and
    (throttled) graph metrics; upsert a durable item per match. Best-effort:
    a failure here is logged but never aborts records ingestion."""

    try:
        metrics: dict[str, float] = {}
        if metrics_throttle is None or metrics_throttle.should_recompute(
            event.knowledge_base_id, now=utc_now()
        ):
            graph_metrics = graph_service.compute_metrics(event.knowledge_base_id)
            metrics = {
                "entity_count": float(graph_metrics.entity_count),
                "relationship_count": float(graph_metrics.relationship_count),
                "avg_degree": graph_metrics.avg_degree,
            }
        matches = evaluate(
            policy_rules, PolicyEvalState(entities=entities, alerts=[], metrics=metrics)
        )
        for match in matches:
            policy_service.record_match(
                knowledge_base_id=event.knowledge_base_id,
                rule_id=match.rule_id,
                rule_pack_id=match.rule_pack_id,
                target_kind=match.target_kind,
                target_ref=match.target_ref,
                title=match.title,
                severity=match.severity,
                matched_fields=match.matched_fields,
                citations=match.citations,
            )
    except Exception as exc:  # noqa: BLE001 - policy eval must not block ingestion
        logger.warning(
            "Policy evaluation failed for kb=%s: %s", event.knowledge_base_id, exc
        )
```

Add imports near the other module imports in `coordinator.py`:

```python
from config.schema import PolicyRulePack
from policy.evaluation import PolicyEvalState, evaluate
from policy.service import PolicyService
from shared.types import Entity  # if not already imported
from shared.utils import utc_now  # if not already imported
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/agent/test_policy_evaluation_stage.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_policy_evaluation_stage.py
git commit -m "feat(agent): evaluate policy rules in the records-ingested stage (BL-011)"
```

---

### Task 13: Wire policy service into the worker composition root + dispatch

**Files:**
- Modify: `backend/agent/coordinator.py` (`WorkerDependencies`, `build_worker_dependencies`, `build_policy_item_repository`/`build_policy_service`, `drain_ingestion_events`/`_dispatch_event` call sites)
- Test: `backend/tests/agent/test_worker_dependencies.py` (append, or the existing build-deps test)

- [ ] **Step 1: Write the failing test** — append to the existing worker-deps test (find it: `grep -rl build_worker_dependencies backend/tests`). Assert the wired deps expose a `policy_service` and `policy_rules`:

```python
def test_build_worker_dependencies_wires_policy(monkeypatch) -> None:
    # reuse the existing monkeypatched config/env setup from this file
    deps = build_worker_dependencies()
    assert deps.policy_service is not None
    assert isinstance(deps.policy_rules, list)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/agent/test_worker_dependencies.py -k policy`
Expected: FAIL — `AttributeError: 'WorkerDependencies' object has no attribute 'policy_service'`.

- [ ] **Step 3: Wire it** in `backend/agent/coordinator.py`:

1. Add builder selectors next to `build_observation_writer`:

```python
def build_policy_item_repository(
    provider: ConnectionProvider | None,
) -> PolicyItemRepository:
    """Select a policy item repository: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryPolicyItemRepository()
    return PostgresPolicyItemRepository(provider)


def build_policy_service(provider: ConnectionProvider | None) -> PolicyService:
    return create_policy_service(build_policy_item_repository(provider))
```

2. Add `policy_service: PolicyService` and `policy_rules: list[PolicyRulePack]` to the `WorkerDependencies` dataclass.

3. In `build_worker_dependencies`, after `connection_provider = build_connection_provider(config)`:

```python
    policy_service = build_policy_service(connection_provider)
    policy_rules = list(config.policy_rules)
```

and add `policy_service=policy_service, policy_rules=policy_rules,` to the `return WorkerDependencies(...)`.

4. In the `run_worker` → `drain_ingestion_events(...)` call, pass `policy_service=deps.policy_service,` and `policy_rules=deps.policy_rules,`. Thread those two params through `drain_ingestion_events` → `_dispatch_event` → into the `handle_records_ingested(...)` call within the `RecordsIngestedEvent` branch (also pass `metrics_throttle=metrics_throttle` there, which is already available in the dispatch scope).

5. Add the imports:

```python
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.adapters.protocols import PolicyItemRepository
from policy.service import PolicyService, create_policy_service
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/agent/test_worker_dependencies.py -k policy`
Expected: PASS.

- [ ] **Step 5: Full backend gate for the phase**

Run: `cd backend && .venv/bin/pytest -q -m "not integration" && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full green; pyright 0 errors; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_worker_dependencies.py
git commit -m "feat(agent): wire PolicyService + policy_rules into the worker (BL-011)"
```

---

# Phase 6 — API surface (items + triage; remove gaps; de-seed)

### Task 14: Policy item DTOs (add) + remove gap/brief contracts

**Files:**
- Modify: `backend/api/contracts.py`
- Test: `backend/tests/api/test_policy_contracts.py` (new)

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_policy_contracts.py`:

```python
from __future__ import annotations

import pytest


def test_policy_item_dtos_exist() -> None:
    from api.contracts import (
        PolicyItemDetailResponse,
        PolicyItemListResponse,
        PolicyItemSummaryResponse,
        PolicyTriageRequest,
    )

    req = PolicyTriageRequest(action="accept", note="ok")
    assert req.action == "accept"
    assert PolicyItemListResponse(items=[]).items == []
    assert "status" in PolicyItemSummaryResponse.model_fields
    assert "disposition" in PolicyItemDetailResponse.model_fields


def test_legacy_policy_gap_contracts_are_removed() -> None:
    import api.contracts as contracts

    for removed in (
        "PolicyGapSummaryResponse", "PolicyGapListResponse", "PolicyGapDetailResponse",
        "PolicyGapCaseListResponse", "PolicyBriefCreateRequest",
    ):
        assert not hasattr(contracts, removed), f"{removed} should be removed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_contracts.py`
Expected: FAIL — `ImportError: cannot import name 'PolicyItemDetailResponse'`.

- [ ] **Step 3: Edit `backend/api/contracts.py`**:

Add the new DTOs (mirror the `Case*Response` field style):

```python
class PolicyCitationResponse(BaseModel):
    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None


class PolicyDispositionResponse(BaseModel):
    action: Literal["accept", "reject", "defer", "escalate"]
    actor: str
    note: str | None = None
    decided_at: datetime
    case_id: str | None = None


class PolicyItemSummaryResponse(BaseModel):
    id: str
    knowledge_base_id: str
    rule_id: str
    rule_pack_id: str
    target_kind: Literal["entity", "alert", "metric"]
    target_ref: str
    title: str
    severity: Literal["medium", "high", "critical"]
    status: Literal["open", "accepted", "rejected", "deferred", "escalated"]
    updated_at: datetime


class PolicyItemListResponse(BaseModel):
    items: list[PolicyItemSummaryResponse] = Field(
        default_factory=lambda: cast(list[PolicyItemSummaryResponse], [])
    )
    total: int = 0


class PolicyItemDetailResponse(BaseModel):
    item: PolicyItemSummaryResponse
    matched_fields: dict[str, str | float | int | bool] = Field(
        default_factory=lambda: cast(dict[str, str | float | int | bool], {})
    )
    citations: list[PolicyCitationResponse] = Field(
        default_factory=lambda: cast(list[PolicyCitationResponse], [])
    )
    disposition: PolicyDispositionResponse | None = None


class PolicyTriageRequest(BaseModel):
    action: Literal["accept", "reject", "defer", "escalate"]
    note: str | None = None
```

**Remove** the classes `PolicyGapSummaryResponse`, `PolicyGapListResponse`, `PolicyGapDetailResponse`, `PolicyGapCaseListResponse`, `PolicyBriefCreateRequest`, `PolicyBriefResponse`, and any `PolicyCitation`/`PolicyTrend` helper types used only by gaps. Delete their entries from `__all__` and add the new DTO names. (`Literal`, `datetime`, `cast`, `Field` are already imported in this file.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_contracts.py`
Expected: PASS (2 passed). Other API tests will now fail to import the removed names — those are fixed in Tasks 15–16 (router + dependencies + state). Do not run the full API suite until Task 16.

- [ ] **Step 5: Commit**

```bash
git add backend/api/contracts.py backend/tests/api/test_policy_contracts.py
git commit -m "feat(api): policy item DTOs; remove policy-gap/brief contracts (BL-011)"
```

---

### Task 15: Policy dependencies (service wiring + payloads + escalate orchestration); remove gap providers

**Files:**
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/api/test_policy_dependencies.py` (new)

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_policy_dependencies.py`. Build an in-memory `PolicyService` + `CaseService`, seed one open item, and assert the triage-escalate path creates a case and links it:

```python
from __future__ import annotations

import pytest

from api.contracts import PolicyTriageRequest
from api.dependencies import _apply_policy_triage  # tested through the public helper
from cases.adapters.in_memory import InMemoryCaseRepository
from cases.service import create_case_service
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.service import create_policy_service


def _wire():
    policy = create_policy_service(InMemoryPolicyItemRepository())
    cases = create_case_service(InMemoryCaseRepository())
    item = policy.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1", target_kind="entity",
        target_ref="claim-1", title="Claim claim-1 over threshold", severity="high",
        matched_fields={"properties.amount": 1500.0}, citations=[],
    )
    return policy, cases, item


def test_escalate_creates_and_links_case() -> None:
    policy, cases, item = _wire()
    detail = _apply_policy_triage(
        policy_service=policy, case_service=cases, knowledge_base_id="kb-1",
        item_id=item.id, payload=PolicyTriageRequest(action="escalate", note="urgent"),
        actor="ana@example.com",
    )
    assert detail.item.status == "escalated"
    assert detail.disposition is not None and detail.disposition.case_id is not None
    listed, total = cases.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1
    assert listed[0].timeline  # carries the policy-origin event


def test_accept_does_not_create_a_case() -> None:
    policy, cases, item = _wire()
    detail = _apply_policy_triage(
        policy_service=policy, case_service=cases, knowledge_base_id="kb-1",
        item_id=item.id, payload=PolicyTriageRequest(action="accept"), actor="ana",
    )
    assert detail.item.status == "accepted"
    assert cases.list(knowledge_base_id="kb-1", limit=10, offset=0)[1] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_dependencies.py`
Expected: FAIL — `ImportError: cannot import name '_apply_policy_triage'`.

- [ ] **Step 3: Edit `backend/api/dependencies.py`**:

Add the repository/service providers (mirror `get_case_repository`/`get_case_service`):

```python
def get_policy_repository(request: Request) -> PolicyItemRepository:
    repository = getattr(request.app.state, "policy_repository", None)
    if isinstance(repository, PolicyItemRepository):
        return repository
    provider = get_connection_provider()
    repository = (
        InMemoryPolicyItemRepository() if provider is None
        else PostgresPolicyItemRepository(provider)
    )
    request.app.state.policy_repository = repository
    return repository


def get_policy_service(
    repository: PolicyItemRepository = Depends(get_policy_repository),
) -> PolicyService:
    return create_policy_service(repository)
```

Add the mapping helpers and the triage orchestration (the escalate path uses `CaseService.create` with a policy-origin timeline event — D-ESCALATE-IMPL):

```python
def _policy_item_to_summary(item: PolicyItem) -> PolicyItemSummaryResponse:
    return PolicyItemSummaryResponse(
        id=item.id, knowledge_base_id=item.knowledge_base_id, rule_id=item.rule_id,
        rule_pack_id=item.rule_pack_id, target_kind=item.target_kind,
        target_ref=item.target_ref, title=item.title, severity=item.severity,
        status=item.status, updated_at=item.updated_at,
    )


def _policy_item_to_detail(item: PolicyItem) -> PolicyItemDetailResponse:
    disposition = (
        None if item.disposition is None
        else PolicyDispositionResponse(**item.disposition.model_dump())
    )
    return PolicyItemDetailResponse(
        item=_policy_item_to_summary(item),
        matched_fields=dict(item.matched_fields),
        citations=[PolicyCitationResponse(**c.model_dump()) for c in item.citations],
        disposition=disposition,
    )


_POLICY_SEVERITY_TO_PRIORITY: dict[str, CasePriority] = {
    "medium": "medium", "high": "high", "critical": "critical",
}


def _apply_policy_triage(
    *,
    policy_service: PolicyService,
    case_service: CaseService,
    knowledge_base_id: str,
    item_id: str,
    payload: PolicyTriageRequest,
    actor: str,
) -> PolicyItemDetailResponse:
    existing = policy_service.get(knowledge_base_id=knowledge_base_id, item_id=item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy item not found.")
    case_id: str | None = None
    if payload.action == "escalate":
        case = case_service.create(
            knowledge_base_id=knowledge_base_id,
            title=f"Policy escalation: {existing.title}",
            priority=_POLICY_SEVERITY_TO_PRIORITY.get(existing.severity, "medium"),
            timeline=[
                CaseTimelineEvent(
                    occurred_at=utc_now(),
                    label=f"Escalated from policy rule {existing.rule_id}",
                    detail=f"target={existing.target_ref}; matched={existing.matched_fields}",
                )
            ],
        )
        case_id = case.id
    try:
        updated = policy_service.triage(
            knowledge_base_id=knowledge_base_id, item_id=item_id,
            action=payload.action, actor=actor, note=payload.note, case_id=case_id,
        )
    except PolicyItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyItemAlreadyTriagedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _policy_item_to_detail(updated)
```

Add the FastAPI payload providers used by the router:

```python
def get_policy_item_list_payload(
    knowledge_base_id: str = Query(...),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyItemListResponse:
    items, total = service.list(
        knowledge_base_id=knowledge_base_id, limit=limit, offset=offset, status=status
    )
    return PolicyItemListResponse(
        items=[_policy_item_to_summary(i) for i in items], total=total
    )


def get_policy_item_detail_payload(
    item_id: str = Path(...),
    knowledge_base_id: str = Query(...),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyItemDetailResponse:
    item = service.get(knowledge_base_id=knowledge_base_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Policy item not found.")
    return _policy_item_to_detail(item)


def get_policy_triage_payload(
    payload: PolicyTriageRequest,
    item_id: str = Path(...),
    knowledge_base_id: str = Query(...),
    policy_service: PolicyService = Depends(get_policy_service),
    case_service: CaseService = Depends(get_case_service),
    principal: Principal = Depends(get_current_principal),
) -> PolicyItemDetailResponse:
    return _apply_policy_triage(
        policy_service=policy_service, case_service=case_service,
        knowledge_base_id=knowledge_base_id, item_id=item_id, payload=payload,
        actor=principal.subject,
    )
```

**Remove** `get_policy_gap_list_payload`, `get_policy_gap_detail_payload`, `get_policy_gap_cases_payload`, `get_policy_brief_payload`.

Add the imports (`PolicyItem`, the new contracts, `PolicyItemRepository`, the adapters, `PolicyService`/`create_policy_service`, `PolicyItemNotFoundError`/`PolicyItemAlreadyTriagedError`, `CaseTimelineEvent`, `utc_now`, `Query`/`Path`/`HTTPException` if not already imported). Confirm the `get_current_principal`/`Principal.subject` names against the existing auth dependency (used by the cases feedback provider for the actor) — reuse that exact dependency.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_dependencies.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/api/dependencies.py backend/tests/api/test_policy_dependencies.py
git commit -m "feat(api): policy service wiring + triage/escalate orchestration; drop gap providers (BL-011)"
```

---

### Task 16: Policy router (items + triage) + ApiState de-seed

**Files:**
- Modify: `backend/api/routers/policy.py`, `backend/api/state.py`
- Test: `backend/tests/api/test_policy_router.py` (new), plus the de-seed regression assertion

- [ ] **Step 1: Write the failing test** — `backend/tests/api/test_policy_router.py` (uses the existing FastAPI `TestClient` app fixture — find the pattern in `tests/api/test_cases_router.py` and reuse its `client`/auth fixtures). It seeds one item directly via the app's policy repository, then exercises the routes:

```python
def test_list_and_get_and_triage_items(client, seed_policy_item) -> None:
    kb = "kb-1"
    item_id = seed_policy_item(kb=kb)  # fixture upserts one open item via app.state.policy_repository

    listed = client.get(f"/policy/items?knowledge_base_id={kb}")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = client.get(f"/policy/items/{item_id}?knowledge_base_id={kb}")
    assert detail.status_code == 200
    assert detail.json()["item"]["status"] == "open"

    triaged = client.post(
        f"/policy/items/{item_id}/triage?knowledge_base_id={kb}",
        json={"action": "defer", "note": "later"},
    )
    assert triaged.status_code == 200
    assert triaged.json()["item"]["status"] == "deferred"

    # second triage on a disposed item -> 409
    again = client.post(
        f"/policy/items/{item_id}/triage?knowledge_base_id={kb}",
        json={"action": "accept"},
    )
    assert again.status_code == 409


def test_legacy_gap_routes_are_gone(client) -> None:
    assert client.get("/policy/gaps").status_code == 404


def test_no_seed_methods_outside_tests() -> None:
    # de-seed regression: ApiState must not expose policy-gap seeding anymore.
    import api.state as state_mod
    assert not hasattr(state_mod, "PolicyGapRecord")
    assert not hasattr(state_mod.ApiState, "_seed_policy_gaps")
    assert not hasattr(state_mod.ApiState, "list_policy_gaps")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_router.py`
Expected: FAIL — legacy gap routes still resolve / `_seed_policy_gaps` still present.

- [ ] **Step 3: Replace `backend/api/routers/policy.py`**:

```python
"""Policy intelligence router: rule-generated items + analyst triage (BL-011)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import PolicyItemDetailResponse, PolicyItemListResponse
from api.dependencies import (
    get_policy_item_detail_payload,
    get_policy_item_list_payload,
    get_policy_triage_payload,
)
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get(
    "/items",
    response_model=PolicyItemListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_policy_items(
    payload: PolicyItemListResponse = Depends(get_policy_item_list_payload),
) -> PolicyItemListResponse:
    """List KB-scoped policy items, optionally filtered by status."""
    return payload


@router.get(
    "/items/{item_id}",
    response_model=PolicyItemDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_policy_item(
    payload: PolicyItemDetailResponse = Depends(get_policy_item_detail_payload),
) -> PolicyItemDetailResponse:
    """Return one policy item detail payload."""
    return payload


@router.post(
    "/items/{item_id}/triage",
    response_model=PolicyItemDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def triage_policy_item(
    payload: PolicyItemDetailResponse = Depends(get_policy_triage_payload),
) -> PolicyItemDetailResponse:
    """Triage a policy item (accept/reject/defer/escalate)."""
    return payload
```

- [ ] **Step 4: De-seed `backend/api/state.py`** — remove: the `PolicyGapRecord` dataclass; `_seed_policy_gaps`; `list_policy_gaps`; `get_policy_gap_detail`; `list_policy_gap_cases`; `create_policy_brief`; the `_to_policy_gap_summary` and `_sorted_policy_gaps` helpers; and the `self._policy_gaps = self._seed_policy_gaps()` assignment in `__init__`. Remove now-unused imports (e.g. the `PolicyGap*`/`PolicyBrief*` contract imports). Leave the cases/alert/conversation seeds alone — those belong to BL-012.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/api/test_policy_router.py`
Expected: PASS (3 passed). (Add the `seed_policy_item` fixture to `tests/api/conftest.py` or the test file: upsert one `PolicyItem` via `client.app.state.policy_repository` — set the repo first if absent, mirroring how cases tests seed durable rows.)

- [ ] **Step 6: Full backend gate**

Run: `cd backend && .venv/bin/pytest -q -m "not integration" && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full green; pyright 0; ruff clean. **Fix any failures surfaced by the de-seed** (e.g. a supervisor view or test referencing `list_policy_gaps`) — do not leave a red test (turn-gate rule).

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/policy.py backend/api/state.py backend/tests/api/test_policy_router.py backend/tests/api/conftest.py
git commit -m "feat(api): /policy/items + triage routes; remove seeded policy gaps (BL-011)"
```

---

# Phase 7 — Frontend (contract regen + page rebuild)

### Task 17: Regenerate contracts + rewrite the policy API client

**Files:**
- Modify: `chili_app/src/api/contracts.ts`, `chili_app/src/api/policy.ts`
- Test: `chili_app/src/api/__tests__/policy.test.ts`
- Generated (do not hand-edit): `chili_app/src/lib/api/schema.ts`, `chili_app/openapi.json`

- [ ] **Step 1: Regenerate the OpenAPI contracts** (main session — backend must import cleanly first):

Run (repo root): `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`
Then: `cd chili_app && npm run codegen:api`
Expected: `src/lib/api/schema.ts` now contains `PolicyItemSummaryResponse`, `PolicyItemDetailResponse`, `PolicyItemListResponse`, `PolicyTriageRequest`, and no longer contains `PolicyGap*`.

- [ ] **Step 2: Write the failing client test** — replace `chili_app/src/api/__tests__/policy.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'

import * as client from '../client'
import { getPolicyItems, getPolicyItem, triagePolicyItem } from '../policy'

describe('policy api client', () => {
  it('threads knowledge_base_id and status into requests', async () => {
    const apiFetch = vi.spyOn(client, 'apiFetch').mockResolvedValue({ items: [], total: 0 })
    await getPolicyItems('kb-1', 'open')
    expect(apiFetch).toHaveBeenCalledWith('/policy/items?knowledge_base_id=kb-1&status=open')

    apiFetch.mockResolvedValue({ item: {}, matched_fields: {}, citations: [] })
    await getPolicyItem('kb-1', 'item-9')
    expect(apiFetch).toHaveBeenCalledWith('/policy/items/item-9?knowledge_base_id=kb-1')
  })

  it('posts triage actions', async () => {
    const apiPost = vi.spyOn(client, 'apiPost').mockResolvedValue({ item: {}, matched_fields: {}, citations: [] })
    await triagePolicyItem('kb-1', 'item-9', { action: 'escalate', note: 'urgent' })
    expect(apiPost).toHaveBeenCalledWith(
      '/policy/items/item-9/triage?knowledge_base_id=kb-1',
      { action: 'escalate', note: 'urgent' },
    )
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd chili_app && npx vitest run src/api/__tests__/policy.test.ts`
Expected: FAIL — `getPolicyItems` is not exported.

- [ ] **Step 4: Swap the contract aliases** in `chili_app/src/api/contracts.ts` — remove the `PolicyGap*`/`PolicyBrief*` exports and add (mirror the `Case*` alias style):

```typescript
export type PolicyItemStatus = Schemas['PolicyItemSummaryResponse']['status']
export type PolicySeverity = Schemas['PolicyItemSummaryResponse']['severity']
export type PolicyItemSummaryResponse = Schemas['PolicyItemSummaryResponse']
export type PolicyItemListResponse = RequireFields<Schemas['PolicyItemListResponse'], 'items'>
export type PolicyItemDetailResponse = RequireFields<
  Schemas['PolicyItemDetailResponse'],
  'matched_fields' | 'citations'
>
export type PolicyTriageRequest = Schemas['PolicyTriageRequest']
```

- [ ] **Step 5: Rewrite `chili_app/src/api/policy.ts`** (mirror `api/cases.ts` — `kbQuery` helper, KB-scoped query keys, `useQuery`/`useMutation`, invalidation):

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  PolicyItemDetailResponse,
  PolicyItemListResponse,
  PolicyTriageRequest,
} from './contracts'

const kbQuery = (kb: string, extra?: Record<string, string>) => {
  const params = new URLSearchParams({ knowledge_base_id: kb, ...(extra ?? {}) })
  return params.toString()
}

export const policyItemsQueryKey = (kb: string | null, status?: string) =>
  ['policy', 'items', kb, status ?? 'all'] as const
export const policyItemQueryKey = (kb: string | null, itemId: string | null) =>
  ['policy', 'items', kb, itemId] as const

export function getPolicyItems(kb: string, status?: string): Promise<PolicyItemListResponse> {
  const query = status ? kbQuery(kb, { status }) : kbQuery(kb)
  return apiFetch<PolicyItemListResponse>(`/policy/items?${query}`)
}

export function getPolicyItem(kb: string, itemId: string): Promise<PolicyItemDetailResponse> {
  return apiFetch<PolicyItemDetailResponse>(`/policy/items/${itemId}?${kbQuery(kb)}`)
}

export function triagePolicyItem(
  kb: string, itemId: string, payload: PolicyTriageRequest,
): Promise<PolicyItemDetailResponse> {
  return apiPost<PolicyItemDetailResponse, PolicyTriageRequest>(
    `/policy/items/${itemId}/triage?${kbQuery(kb)}`, payload,
  )
}

export function usePolicyItems(kb: string | null, status?: string) {
  return useQuery({
    queryKey: policyItemsQueryKey(kb, status),
    queryFn: () => getPolicyItems(kb ?? '', status),
    enabled: Boolean(kb),
  })
}

export function usePolicyItem(kb: string | null, itemId: string | null) {
  return useQuery({
    queryKey: policyItemQueryKey(kb, itemId),
    queryFn: () => getPolicyItem(kb ?? '', itemId ?? ''),
    enabled: Boolean(kb) && Boolean(itemId),
  })
}

export function useTriagePolicyItem(kb: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { itemId: string; payload: PolicyTriageRequest }) =>
      triagePolicyItem(kb ?? '', vars.itemId, vars.payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['policy', 'items', kb] })
    },
  })
}
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd chili_app && npx vitest run src/api/__tests__/policy.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts chili_app/src/api/policy.ts chili_app/src/api/__tests__/policy.test.ts
git commit -m "feat(fe): regenerate contracts + KB-scoped policy items client (BL-011)"
```

---

### Task 18: Rebuild `PolicyIntelligencePage` as the item queue + triage

**Files:**
- Modify: `chili_app/src/pages/PolicyIntelligencePage.tsx`
- Test: `chili_app/src/pages/__tests__/PolicyIntelligencePage.test.tsx`

- [ ] **Step 1: Rewrite the page test** — `chili_app/src/pages/__tests__/PolicyIntelligencePage.test.tsx` (mirror `CaseManagementPage.test.tsx`: hoisted mocks for `usePolicyItems`/`usePolicyItem`/`useTriagePolicyItem` + `useKnowledgeBases`, render inside `MemoryRouter initialEntries={['/policy?kb=kb-1']}`):

```typescript
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { PolicyIntelligencePage } from '../PolicyIntelligencePage'

const mocks = vi.hoisted(() => ({
  triage: vi.fn(),
  usePolicyItems: vi.fn(),
  usePolicyItem: vi.fn(),
  useKnowledgeBases: vi.fn(),
}))

vi.mock('../../api/knowledgebases', () => ({ useKnowledgeBases: mocks.useKnowledgeBases }))
vi.mock('../../api/policy', () => ({
  usePolicyItems: mocks.usePolicyItems,
  usePolicyItem: mocks.usePolicyItem,
  useTriagePolicyItem: () => ({ mutate: mocks.triage, isPending: false }),
}))

function setup() {
  mocks.useKnowledgeBases.mockReturnValue({ data: { items: [{ id: 'kb-1', name: 'KB 1' }] } })
  mocks.usePolicyItems.mockReturnValue({
    isLoading: false, isError: false,
    data: { items: [{ id: 'item-1', title: 'Claim claim-1 over threshold', severity: 'high', status: 'open', updated_at: '2026-06-04T00:00:00Z' }], total: 1 },
  })
  mocks.usePolicyItem.mockReturnValue({
    isLoading: false, isError: false,
    data: { item: { id: 'item-1', title: 'Claim claim-1 over threshold', severity: 'high', status: 'open', updated_at: '2026-06-04T00:00:00Z' }, matched_fields: { 'properties.amount': 1500 }, citations: [] },
  })
}

describe('PolicyIntelligencePage', () => {
  it('lists items and triages the selected item', () => {
    setup()
    render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)
    expect(screen.getByText('Policy Intelligence')).toBeInTheDocument()
    expect(screen.getAllByText('Claim claim-1 over threshold').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
    expect(mocks.triage).toHaveBeenCalledWith(
      { itemId: 'item-1', payload: { action: 'accept' } }, expect.anything(),
    )
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd chili_app && npx vitest run src/pages/__tests__/PolicyIntelligencePage.test.tsx`
Expected: FAIL — the page still renders the gaps surface / `useTriagePolicyItem` not used.

- [ ] **Step 3: Rewrite `chili_app/src/pages/PolicyIntelligencePage.tsx`** — KB from `useSearchParams()` (`?kb=`) falling back to the first KB (the `CaseManagementPage` pattern); a status filter; the item list (severity/status chips) → detail (matched_fields + citations + disposition) → a triage action bar with four buttons calling `triageMutation.mutate({ itemId, payload: { action } }, { onSuccess/onError: showToast })`; reuse `Card`/`Chip`/`SectionHeader`/`EmptyState`/`LoadingState`/`ErrorState` and `showToast` from `../components/common/toastStore`. Buttons must have accessible names `Accept`/`Reject`/`Defer`/`Escalate`. (Drop the `TrendBars`/brief-builder UI — the brief is descoped per R-01; if reinstated later it returns as its own task.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd chili_app && npx vitest run src/pages/__tests__/PolicyIntelligencePage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Lint + build + full unit run**

Run: `cd chili_app && npm run lint && npm run build && npx vitest run`
Expected: ESLint clean; `tsc -b` + vite build succeed; all vitest green. Fix any breakage from the removed `PolicyGap*` types (e.g. other files importing them).

- [ ] **Step 6: Commit**

```bash
git add chili_app/src/pages/PolicyIntelligencePage.tsx chili_app/src/pages/__tests__/PolicyIntelligencePage.test.tsx
git commit -m "feat(fe): rebuild Policy Intelligence as item queue + triage (BL-011)"
```

---

# Phase 8 — Dev-seed + Playwright e2e (full stack)

### Task 19: Seed one policy item in the dev-seed endpoint

**Files:**
- Modify: `backend/api/routers/admin.py` (the dev-seed endpoint), and the seed-response model
- Modify: `chili_app/e2e/helpers/seeded.ts`
- Test: extend the existing dev-seed backend test (find it: `grep -rl dev-seed backend/tests`)

- [ ] **Step 1: Write the failing test** — extend the dev-seed test to assert the response includes a `policy_item_id` and that the item is retrievable:

```python
def test_dev_seed_creates_a_policy_item(client) -> None:
    res = client.post("/admin/dev-seed")
    assert res.status_code == 200
    body = res.json()
    assert body["policy_item_id"]
    kb = body["knowledge_base_id"]
    got = client.get(f"/policy/items/{body['policy_item_id']}?knowledge_base_id={kb}")
    assert got.status_code == 200
    assert got.json()["item"]["status"] == "open"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest -q <dev-seed test path> -k policy_item`
Expected: FAIL — `KeyError: 'policy_item_id'`.

- [ ] **Step 3: Extend the dev-seed endpoint** in `backend/api/routers/admin.py` — after seeding the KB/alert/case, upsert one open `PolicyItem` via the app's policy service (deterministic; bypasses the worker so the e2e is stable, matching the dev-seed rationale from `2ba8730`):

```python
    policy_service = create_policy_service(get_policy_repository(request))
    policy_item = policy_service.record_match(
        knowledge_base_id=knowledge_base_id,
        rule_id="claim_over_billed",
        rule_pack_id="billing_thresholds",
        target_kind="entity",
        target_ref=entity_id,
        title=f"Claim {entity_id} exceeds the billing threshold",
        severity="high",
        matched_fields={"properties.amount": 1500.0},
        citations=[],
    )
    # ...add policy_item_id=policy_item.id to the seed response model + return value.
```

Add `policy_item_id: str` to the dev-seed response Pydantic model.

- [ ] **Step 4: Add `policy_item_id` to `chili_app/e2e/helpers/seeded.ts`** `SeededIds` type.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest -q <dev-seed test path>`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/admin.py chili_app/e2e/helpers/seeded.ts backend/tests/<dev-seed test>
git commit -m "feat(e2e): seed a deterministic open policy item via dev-seed (BL-011)"
```

---

### Task 20: Playwright e2e — triage + escalate against the full stack

**Files:**
- Create: `chili_app/e2e/policy-triage.spec.ts`

- [ ] **Step 1: Write the spec** (mirror `case-promote.spec.ts` — uses `seeded()`):

```typescript
/**
 * Policy triage + escalate (full stack, BL-011). The dev-seed scenario creates
 * one open policy item; this spec triages it via the real /policy/items/{id}/triage
 * endpoint and asserts the status flips. Escalate additionally creates a case.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Policy triage', () => {
  test('escalating the seeded policy item creates a case via the real API', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/policy?kb=${kb}`)

    await expect(page.getByText('Policy Intelligence')).toBeVisible()
    const escalate = page.getByRole('button', { name: 'Escalate' }).first()
    await expect(escalate).toBeVisible()
    await escalate.click()

    // The detail panel reflects the escalated status from the real backend.
    await expect(page.getByText('escalated')).toBeVisible()

    // The escalation created a case, visible KB-scoped on the Cases page.
    await page.goto(`/cases?kb=${kb}`)
    await expect(page.getByText(/Policy escalation:/)).toBeVisible()
  })
})
```

- [ ] **Step 2: Run the full e2e suite** (main session — brings up the full stack)

Run: `make test-e2e`
Expected: all specs pass, including `policy-triage.spec.ts`. If the policy item isn't visible, confirm the dev-seed change is in the running image (the stack rebuilds in `make test-e2e`) and that `medicare_fraud_dev.yaml` ships the rule pack.

- [ ] **Step 3: a11y check** — confirm no axe regressions on `/policy` (reuse the existing axe helper if the suite has one; otherwise spot-check via the chrome-devtools a11y skill against `http://localhost:5173/policy?kb=<kb>` in the main session).

- [ ] **Step 4: Commit**

```bash
git add chili_app/e2e/policy-triage.spec.ts
git commit -m "test(e2e): policy triage + escalate-to-case on the full stack (BL-011)"
```

---

# Phase 9 — Docs + final verification

### Task 21: Module + project docs

**Files:**
- Create: `backend/policy/README.md`
- Modify: `docs/architecture.md` (add `policy/` to the module map + the policy-item flow), `backend/README.md` (module list + § Current State), `docs/backlog/README.md` status note, `docs/project/planning/backlog.md` (BL-011 → done; D-15 → RESOLVED), `docs/project/planning/sprints/2026-24.md` (flip BL-011 status), the ledger files touched (`docs/ledger/http-routes.md` for the route change, `docs/ledger/config-schema.md` for `policy_rules`, `docs/ledger/event-catalog.md` if applicable, `docs/ledger/module-map.md`).

- [ ] **Step 1: Write `backend/policy/README.md`** — purpose, the `(kb, rule_id, target_ref)` identity + no-reopen lifecycle, the `evaluate` contract, the worker fold-in (D-EVAL-IMPL), the escalate path (D-ESCALATE-IMPL), and the v1 non-goals (single predicate per rule, alert-target deferred, no auto-resolution). Mirror `backend/cases/README.md` structure.

- [ ] **Step 2: Update the cross-cutting docs** — in `docs/architecture.md` add `policy/` beside `cases/` and describe the rule-pack → worker → item → triage → escalate flow; in `backend/README.md` add `policy/` to the module map and a § Current State line; flip `docs/project/planning/backlog.md` BL-011 to `done (Sprint 2026-24)` and D-15 to RESOLVED; update `docs/ledger/http-routes.md` (remove `/policy/gaps*`, add `/policy/items*`) and `docs/ledger/config-schema.md` (`policy_rules`).

- [ ] **Step 3: Commit**

```bash
git add backend/policy/README.md docs/architecture.md backend/README.md docs/backlog/README.md docs/project/planning/backlog.md docs/project/planning/sprints/2026-24.md docs/ledger/
git commit -m "docs(policy): module README + architecture/backlog/ledger updates (BL-011)"
```

---

### Task 22: Final full verification (the turn-gate)

**Files:** none (verification only).

- [ ] **Step 1: Backend — unit suite + coverage + types + lint**

Run: `cd backend && .venv/bin/pytest -q -m "not integration" --cov=policy --cov=config --cov=api --cov=agent --cov-report=term-missing && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full green; coverage ≥ 85% for `policy/` and touched packages; pyright 0 errors; ruff clean.

- [ ] **Step 2: Backend — integration suite** (main session)

Run: `docker exec chiliai-api-1 sh -c "python -m pytest -q -m integration tests/policy"`
Expected: live-DB policy tests pass.

- [ ] **Step 3: Frontend — lint + build + unit**

Run: `cd chili_app && npm run lint && npm run build && npx vitest run`
Expected: ESLint clean; build succeeds; vitest green.

- [ ] **Step 4: Contract drift check** (main session)

Run: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json && cd chili_app && npm run codegen:api && git diff --exit-code src/lib/api/schema.ts openapi.json`
Expected: no diff (contracts already regenerated in Task 17 — CI fails on drift).

- [ ] **Step 5: E2E — full stack** (main session)

Run: `make test-e2e`
Expected: all specs green, including `policy-triage.spec.ts`.

- [ ] **Step 6: Confirm the BL-011 acceptance checklist** in the spec (§12) is fully satisfied; tick the boxes. If any item is unmet, return to the owning task — do not end on a red gate.

---

## Self-Review (writing-plans checklist — completed)

**1. Spec coverage:** §3 module → Tasks 1–5,10; §4 model → Task 1; §5 config → Tasks 6–7; §6 API (items+triage, remove gaps) → Tasks 14–16; §7 worker (reactive+throttled) → Tasks 12–13; §8 escalate → Tasks 11,15; §9 frontend → Tasks 17–18; §10 persistence → Tasks 9–10; §11 testing → every task + Task 22; §12 acceptance → Task 22 step 6; the D-RECONCILE removal → Tasks 14,16,17; the policy-gaps de-seed (BL-011-owned) → Task 16. No spec section is unmapped.

**2. Placeholder scan:** the only deliberately-deferred-to-the-engineer details are the two reuse-existing-fixtures notes (Task 12's worker stubs, Task 16's `client` fixture) — each names the exact existing test to copy from and forbids committing pseudo-fixtures. No `TBD`/`handle edge cases`/un-shown code remains.

**3. Type consistency:** `PolicyItem`/`PolicyDisposition`/`PolicyCitation`, the Literal aliases, `record_match`/`triage`/`upsert`/`update`/`list`/`get`, `PolicyEvalState`/`PolicyMatch`/`evaluate`, the `PolicyItem*Response`/`PolicyTriageRequest` DTOs, and the natural key `(knowledge_base_id, rule_id, target_ref)` are used identically across model, adapters, service, evaluator, worker, API, and frontend tasks.

---

## Execution Handoff

Choose how to execute (offered after the plan is reviewed):
1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks. NB: per the dev-environment notes, keep Docker/`make`/codegen steps (Tasks 9 step-4, 10, 17 step-1, 19, 20, 22 steps 2/4/5) in the **main session** — subagents stall on Docker prompts.
2. **Inline Execution** — batch with checkpoints via executing-plans.
