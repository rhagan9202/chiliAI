# Theme 1 — Fix Cross-Module Imports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the two cross-module import violations of CLAUDE.md Hard Rule 1 by relocating `KnowledgeBaseRepository` (+ implementations) out of `api/` into a new `backend/knowledgebases/` module, and relocating `MonitoringObservation` from `monitoring/models.py` into `shared/types.py`.

**Architecture:** The current code has two cross-feature imports that the gateway-only/coordinator-only/`shared/`-only rule forbids: `agent/coordinator.py:116` imports `KnowledgeBaseRepository` from `api/_kb_store`, and `records/mappers/feed_mapper.py:14` imports `MonitoringObservation` from `monitoring/models`. The fix is structural: KB metadata persistence becomes its own `backend/knowledgebases/` module (with the standard protocols/models/adapters layout that other modules already follow), and the platform-generic `MonitoringObservation` Pydantic model moves into `shared/types.py` since it's a scored-observation envelope with no business logic. After this theme, the only cross-module surfaces remaining are `shared/`, the FastAPI gateway, and the Redis Streams event bus — matching the documented architecture.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pyright `--strict`, pytest

**Dependencies on other themes:** None. Theme 1 is independent and unblocks Theme 2 (`shared/` will have one additional type, but Theme 2 doesn't need it).

---

## File Structure

**Create:**
- `backend/knowledgebases/__init__.py` — re-exports the public surface
- `backend/knowledgebases/models.py` — `DocumentRecord`
- `backend/knowledgebases/protocols.py` — `KnowledgeBaseRepository`
- `backend/knowledgebases/snapshots.py` — `_KnowledgeBaseStoreSnapshot` (internal)
- `backend/knowledgebases/adapters/__init__.py` — empty
- `backend/knowledgebases/adapters/in_memory.py` — `InMemoryKnowledgeBaseRepository`
- `backend/knowledgebases/adapters/object_store.py` — `ObjectStoreKnowledgeBaseRepository`

**Modify (import updates only):**
- `backend/api/dependencies.py:653` — switch `from api._kb_store import ...` to `from knowledgebases import ...`
- `backend/api/routers/knowledgebases.py:18` — same switch
- `backend/api/routers/records.py:9` — same switch
- `backend/api/routers/rag.py:19` — same switch
- `backend/api/routers/events.py:14` — same switch
- `backend/api/_kb_projection.py:12` — same switch
- `backend/agent/coordinator.py:116` — same switch (this is the architectural-rule violation)
- `backend/monitoring/models.py` — re-export `MonitoringObservation` from `shared.types` (or remove if all consumers updated)
- `backend/monitoring/service.py` — switch import to `shared.types`
- `backend/monitoring/adapters/protocols.py` — same
- `backend/monitoring/adapters/postgres.py` — same
- `backend/monitoring/__init__.py` — re-export `MonitoringObservation` from `shared.types`
- `backend/records/mappers/feed_mapper.py:14` — switch to `shared.types` (this is the architectural-rule violation)
- `backend/api/state.py` — switch to `shared.types`
- `backend/shared/types.py` — add `MonitoringObservation` model
- All test files referencing the old paths (see Task 8)

**Delete:**
- `backend/api/_kb_store.py` — its content is now distributed across the new `knowledgebases/` module

---

## Pre-Flight Sanity Check (do this once before Task 1)

- [ ] **Confirm the violations exist**

```bash
cd backend && grep -rn "from api\." agent/ records/ ingestion/ monitoring/ rag/ graph/ llm/ embeddings/ vectorstore/ analytics/ 2>/dev/null | grep -v test
```

Expected: exactly one line — `agent/coordinator.py:116:from api._kb_store import KnowledgeBaseRepository`. If there are more, expand Task 5 to update them.

```bash
cd backend && grep -rn "from monitoring" records/ ingestion/ rag/ graph/ 2>/dev/null | grep -v test
```

Expected: exactly one line — `records/mappers/feed_mapper.py:14:from monitoring.models import MonitoringObservation`. If there are more, expand Task 7 to update them.

- [ ] **Confirm baseline test pass**

```bash
cd backend && pytest --no-cov -q 2>&1 | tail -5
```

Expected: all tests pass. If any tests fail BEFORE you make changes, fix them or note the pre-existing failures so you can distinguish your-changes failures later.

---

## Task 1: Create `backend/knowledgebases/` skeleton with shared definitions

**Files:**
- Create: `backend/knowledgebases/__init__.py`
- Create: `backend/knowledgebases/protocols.py`
- Create: `backend/knowledgebases/models.py`
- Create: `backend/knowledgebases/snapshots.py`
- Create: `backend/knowledgebases/adapters/__init__.py`

- [ ] **Step 1: Create `backend/knowledgebases/models.py`**

Copy the `DocumentRecord` class out of `backend/api/_kb_store.py` (lines 28-39) into a new file at `backend/knowledgebases/models.py`:

```python
"""Models for the knowledgebases module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

__all__ = ["DocumentRecord"]


class DocumentRecord(BaseModel):
    """Metadata recorded for a registered document inside a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 2: Create `backend/knowledgebases/snapshots.py`**

Copy the internal `_KnowledgeBaseStoreSnapshot` class out of `_kb_store.py` (lines 42-48):

```python
"""Internal serialization snapshot for object-store-backed persistence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase

__all__ = ["KnowledgeBaseStoreSnapshot"]


class KnowledgeBaseStoreSnapshot(BaseModel):
    """Serialized repository state for durable object-store persistence."""

    knowledge_bases: dict[str, KnowledgeBase] = Field(default_factory=dict)
    knowledge_base_order: list[str] = Field(default_factory=list)
    documents: dict[str, dict[str, DocumentRecord]] = Field(default_factory=dict)
    document_order: dict[str, list[str]] = Field(default_factory=dict)
```

Note: the leading underscore on the old class name (`_KnowledgeBaseStoreSnapshot`) was a marker for "private to `api/_kb_store.py`." In the new module it's still internal — kept out of `__init__.py` re-exports — but the underscore is dropped so the file's public surface is consistent.

- [ ] **Step 3: Create `backend/knowledgebases/protocols.py`**

Copy the `KnowledgeBaseRepository` Protocol out of `_kb_store.py` (lines 51-107):

```python
"""Persistence protocol for knowledge base and document metadata."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase

__all__ = ["KnowledgeBaseRepository"]


@runtime_checkable
class KnowledgeBaseRepository(Protocol):
    """Persistence boundary for knowledge base and document metadata."""

    def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None: ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KnowledgeBase], int]: ...

    def update_summary(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        entity_count: int | None = None,
        relationship_count: int | None = None,
    ) -> KnowledgeBase | None: ...

    def delete(self, knowledge_base_id: str) -> bool: ...

    def mark_pending_cleanup(self, knowledge_base_id: str) -> None: ...

    def add_document(self, document: DocumentRecord) -> DocumentRecord: ...

    def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> DocumentRecord | None: ...

    def list_documents(
        self,
        knowledge_base_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentRecord], int]: ...

    def update_document_status(
        self,
        knowledge_base_id: str,
        document_id: str,
        status: str,
    ) -> DocumentRecord | None: ...

    def delete_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool: ...

    def get_document_by_content_hash(
        self,
        knowledge_base_id: str,
        content_hash: str,
    ) -> DocumentRecord | None: ...
```

- [ ] **Step 4: Create `backend/knowledgebases/adapters/__init__.py`**

Empty file with just `"""Adapters for the knowledgebases module."""` as a docstring.

- [ ] **Step 5: Create `backend/knowledgebases/__init__.py`**

```python
"""Knowledge base and document metadata persistence.

Used by `api/` (gateway routers) and `agent/` (worker coordinator). Lives
outside both so neither feature module needs to import from the other.
"""

from __future__ import annotations

from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from knowledgebases.protocols import KnowledgeBaseRepository

__all__ = [
    "DocumentRecord",
    "InMemoryKnowledgeBaseRepository",
    "KnowledgeBaseRepository",
    "ObjectStoreKnowledgeBaseRepository",
]
```

This will fail until Tasks 2 and 3 are done. That's expected — the `__init__.py` reflects the final shape.

- [ ] **Step 6: Do not run tests yet — the adapter files don't exist. Move to Task 2.**

---

## Task 2: Move `InMemoryKnowledgeBaseRepository` to `knowledgebases/adapters/in_memory.py`

**Files:**
- Create: `backend/knowledgebases/adapters/in_memory.py`

- [ ] **Step 1: Copy the in-memory adapter**

Read the full `InMemoryKnowledgeBaseRepository` class from `backend/api/_kb_store.py` (it starts at line 110 — read through to wherever the class ends; expect it to run ~150 lines and include private helpers).

Create `backend/knowledgebases/adapters/in_memory.py` with that class, updating imports at the top:

```python
"""In-memory knowledge base + document metadata repository."""

from __future__ import annotations

from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now

__all__ = ["InMemoryKnowledgeBaseRepository"]


# <Paste the full InMemoryKnowledgeBaseRepository class body here verbatim from
# api/_kb_store.py, plus the helper function `_build_knowledge_base_summary_updates`
# referenced on line 150. Read the source to find the helper's definition and
# include it before the class (private with leading underscore preserved).>
```

**Critical:** the class on line 110 of `_kb_store.py` references `_build_knowledge_base_summary_updates` on line 150 and `_sync_document_count` (a method on the class itself). The free function `_build_knowledge_base_summary_updates` must move with the in-memory adapter (it's an implementation detail). The `_sync_document_count` is a method and stays on the class. If `_build_knowledge_base_summary_updates` is also called by the object-store adapter, share it via a private helper in `knowledgebases/_helpers.py` instead of duplicating; check before deciding by greping inside `_kb_store.py` for both uses of the helper.

- [ ] **Step 2: Verify pyright passes on the new file**

```bash
cd backend && pyright knowledgebases/adapters/in_memory.py
```

Expected: 0 errors. Common failure modes: missing `from __future__ import annotations`, forgotten helper function, stale `shared.utils` import.

- [ ] **Step 3: Do not commit yet — the package isn't importable until Task 3.**

---

## Task 3: Move `ObjectStoreKnowledgeBaseRepository` to `knowledgebases/adapters/object_store.py`

**Files:**
- Create: `backend/knowledgebases/adapters/object_store.py`

- [ ] **Step 1: Copy the object-store adapter**

In `backend/api/_kb_store.py`, find the `ObjectStoreKnowledgeBaseRepository` class (it follows the in-memory class; use `grep -n "class ObjectStore" backend/api/_kb_store.py` to find the exact line). Copy its full body into `backend/knowledgebases/adapters/object_store.py`:

```python
"""Object-store-backed knowledge base + document metadata repository."""

from __future__ import annotations

import json
import logging

from knowledgebases.models import DocumentRecord
from knowledgebases.snapshots import KnowledgeBaseStoreSnapshot
from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.protocols import ObjectStore

__all__ = ["ObjectStoreKnowledgeBaseRepository"]


# <Paste the full ObjectStoreKnowledgeBaseRepository class body here verbatim
# from api/_kb_store.py. Update any internal references to `_KnowledgeBaseStoreSnapshot`
# to use `KnowledgeBaseStoreSnapshot` (drop the leading underscore). If the class
# uses `_build_knowledge_base_summary_updates`, import it from in_memory.py or
# move it to a shared `_helpers.py` (see Task 2's note).>
```

- [ ] **Step 2: Verify pyright on the new adapter**

```bash
cd backend && pyright knowledgebases/adapters/object_store.py
```

Expected: 0 errors.

- [ ] **Step 3: Verify the full new module imports cleanly**

```bash
cd backend && python -c "from knowledgebases import DocumentRecord, KnowledgeBaseRepository, InMemoryKnowledgeBaseRepository, ObjectStoreKnowledgeBaseRepository; print('ok')"
```

Expected: prints `ok`. If the import fails, the error message will indicate which file is broken; fix it and retry.

- [ ] **Step 4: Commit the new module (before any consumer updates)**

```bash
cd backend && git add knowledgebases/
git commit -m "$(cat <<'EOF'
feat(knowledgebases): introduce module for KB and document metadata persistence

New module owns the KnowledgeBaseRepository Protocol + in-memory and
object-store adapters that previously lived in api/_kb_store.py. Both
api/ (gateway routers) and agent/ (worker coordinator) will depend on
this module so neither feature module imports from the other.

No consumer updates yet; api/_kb_store.py remains in place and the old
import sites still work. Subsequent commits migrate consumers and then
delete the old file.
EOF
)"
```

This intentionally leaves the old file in place so the codebase is in a valid intermediate state.

---

## Task 4: Update `api/` consumers to import from `knowledgebases`

**Files:**
- Modify: `backend/api/dependencies.py:653`
- Modify: `backend/api/routers/knowledgebases.py:18`
- Modify: `backend/api/routers/records.py:9`
- Modify: `backend/api/routers/rag.py:19`
- Modify: `backend/api/routers/events.py:14`
- Modify: `backend/api/_kb_projection.py:12`
- Modify: `backend/api/state.py` (only if it imports from `_kb_store`; confirm via grep below)

- [ ] **Step 1: Inventory `api/` consumers**

```bash
cd backend && grep -rn "from api\._kb_store" api/ 2>/dev/null
```

Expected: 6 files (listed above). If grep returns a 7th file (e.g. `api/state.py`), include it in Step 2.

- [ ] **Step 2: Update each import**

For every file listed in Step 1, change:

```python
from api._kb_store import ...
```

to:

```python
from knowledgebases import ...
```

The imported symbols (`DocumentRecord`, `KnowledgeBaseRepository`, `InMemoryKnowledgeBaseRepository`, `ObjectStoreKnowledgeBaseRepository`) are all re-exported by `knowledgebases/__init__.py`, so the import contents don't change — only the module path.

Concrete example: in `backend/api/routers/knowledgebases.py`, line 18 currently reads:

```python
from api._kb_store import DocumentRecord, KnowledgeBaseRepository
```

Change to:

```python
from knowledgebases import DocumentRecord, KnowledgeBaseRepository
```

Apply the same shape to each of the 6 (or 7) files.

- [ ] **Step 3: Run the API test suite**

```bash
cd backend && pytest tests/api/ -q --no-cov 2>&1 | tail -10
```

Expected: all tests pass. The test files still import from `api._kb_store` — that's fine for now, because the old file is still in place and re-exports the same names. Test imports are updated in Task 8.

- [ ] **Step 4: Commit**

```bash
cd backend && git add api/
git commit -m "$(cat <<'EOF'
refactor(api): import KnowledgeBaseRepository from knowledgebases module

api/ routers, dependencies, and projection now import the KB metadata
types from the new knowledgebases/ module. api/_kb_store.py still
re-exports them so test files and agent/coordinator.py still work; those
move in the next commits.
EOF
)"
```

---

## Task 5: Update `agent/coordinator.py` to import from `knowledgebases` (the architectural-rule fix)

**Files:**
- Modify: `backend/agent/coordinator.py:116`

- [ ] **Step 1: Update the import**

In `backend/agent/coordinator.py`, line 116 currently reads:

```python
from api._kb_store import KnowledgeBaseRepository
```

Change to:

```python
from knowledgebases import KnowledgeBaseRepository
```

- [ ] **Step 2: Confirm the violation is resolved**

```bash
cd backend && grep -rn "from api\." agent/ records/ ingestion/ monitoring/ rag/ graph/ llm/ embeddings/ vectorstore/ analytics/ 2>/dev/null | grep -v test
```

Expected: no output (empty result).

- [ ] **Step 3: Run the agent + e2e test suites**

```bash
cd backend && pytest tests/agent/ tests/e2e/ -q --no-cov 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 4: Commit (this is the architectural-rule fix for half of Theme 1)**

```bash
cd backend && git add agent/coordinator.py
git commit -m "$(cat <<'EOF'
fix(arch): agent/coordinator imports KnowledgeBaseRepository from knowledgebases

Removes the last cross-feature import from agent/ into api/, closing
half of the CLAUDE.md Hard Rule 1 gap.
EOF
)"
```

---

## Task 6: Delete `api/_kb_store.py` and update test consumers

**Files:**
- Delete: `backend/api/_kb_store.py`
- Modify: `backend/tests/api/test_kb_store.py:14`
- Modify: `backend/tests/api/test_knowledgebases_router.py:11`
- Modify: `backend/tests/api/test_kb_projection.py:11`
- Modify: `backend/tests/api/test_events_router.py:18`
- Modify: `backend/tests/api/test_workflow_busy_guard.py:14`
- Modify: `backend/tests/api/test_kb_delete_cascade.py:18`
- Modify: `backend/tests/api/test_dependencies.py:907,923`

- [ ] **Step 1: Inventory test consumers**

```bash
cd backend && grep -rn "from api\._kb_store" tests/ 2>/dev/null
```

Expected: 7 files (listed above). If the count differs, include all of them in Step 2.

- [ ] **Step 2: Update each test import**

For every test file from Step 1, change `from api._kb_store import ...` to `from knowledgebases import ...`. Same as Task 4 — the symbol names don't change.

For `tests/api/test_kb_store.py` specifically: the file's name still refers to "kb_store" but it tests the `KnowledgeBaseRepository` Protocol implementations. Consider renaming it to `tests/api/test_knowledgebases_repository.py` for clarity — but only if no other file references its current name (CI may have a path-specific assertion). Run `grep -rn "test_kb_store" backend/ docs/` to check; if no references, rename via `git mv`.

- [ ] **Step 3: Delete `backend/api/_kb_store.py`**

```bash
cd backend && git rm api/_kb_store.py
```

- [ ] **Step 4: Confirm no stale references**

```bash
cd backend && grep -rn "api\._kb_store\|api/_kb_store" . 2>/dev/null | grep -v __pycache__
```

Expected: no output. If any matches remain (e.g., in docs/, README.md, or comments), update them.

- [ ] **Step 5: Run the full test suite + pyright**

```bash
cd backend && pyright . 2>&1 | tail -5
cd backend && pytest -q --no-cov 2>&1 | tail -10
```

Expected: pyright reports 0 errors, all tests pass.

- [ ] **Step 6: Commit**

```bash
cd backend && git add -A
git commit -m "$(cat <<'EOF'
refactor: delete api/_kb_store.py; tests import from knowledgebases

Completes the relocation of KB metadata persistence out of api/. No
production code now references api/_kb_store.
EOF
)"
```

---

## Task 7: Move `MonitoringObservation` to `shared/types.py`

**Files:**
- Modify: `backend/shared/types.py` — add `MonitoringObservation`
- Modify: `backend/monitoring/models.py` — re-export and stop defining
- Modify: `backend/records/mappers/feed_mapper.py:14` — switch to `shared.types`
- Modify: `backend/monitoring/service.py` — switch to `shared.types`
- Modify: `backend/monitoring/adapters/protocols.py` — same
- Modify: `backend/monitoring/adapters/postgres.py` — same
- Modify: `backend/monitoring/__init__.py` — re-export from `shared.types`
- Modify: `backend/api/state.py` — switch to `shared.types`

- [ ] **Step 1: Add `MonitoringObservation` to `backend/shared/types.py`**

Append to `backend/shared/types.py` (at the end of the file, before the `__all__` list if one exists; if it does, add `"MonitoringObservation"` to it):

```python
class MonitoringObservation(BaseModel):
    """A scored observation produced by upstream monitoring inputs.

    Lives in shared/ because both monitoring/ (consumer) and records/
    (producer) need it, and the model has no business logic — just a
    scored-observation envelope.
    """

    entity_id: str
    entity_type: str
    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=utc_now)
    rationale: str
    evidence_pack_id: str | None = None
```

Verify `BaseModel`, `Field`, `datetime`, and `utc_now` are already imported at the top of `shared/types.py` (they should be — `shared/types.py` already imports `BaseModel, Field` and `utc_now` per its existing types).

- [ ] **Step 2: Update `backend/monitoring/models.py`**

Replace the local `MonitoringObservation` class definition (lines 12-21) with a re-export. The new top of the file:

```python
"""Internal transport and workflow models for active monitoring."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from shared.types import MonitoringObservation
from shared.utils import utc_now
```

Delete the original `class MonitoringObservation(BaseModel): ...` block (lines 12-21). Keep `MonitoringBatch`, `AlertCandidate`, `SuppressionRule`, `AlertGroup`, `AlertHistoryRecord` and the `model_validator` import as-is. Update `__all__` at the bottom to still include `"MonitoringObservation"` — the symbol is re-exported even though it's defined elsewhere.

- [ ] **Step 3: Update `backend/records/mappers/feed_mapper.py:14` — the architectural-rule fix**

Replace:

```python
from monitoring.models import MonitoringObservation
```

with:

```python
from shared.types import MonitoringObservation
```

- [ ] **Step 4: Update other monitoring-internal consumers**

In each of the following files, replace `from monitoring.models import MonitoringObservation` (or `from .models import MonitoringObservation`) with `from shared.types import MonitoringObservation`:

- `backend/monitoring/service.py`
- `backend/monitoring/adapters/protocols.py`
- `backend/monitoring/adapters/postgres.py`
- `backend/api/state.py`

For `backend/monitoring/__init__.py`, change any `from .models import MonitoringObservation` to `from shared.types import MonitoringObservation`. The re-export in `monitoring/__init__.py` is kept so existing external callers using `from monitoring import MonitoringObservation` continue to work for now.

- [ ] **Step 5: Confirm no monitoring import remains in non-monitoring code**

```bash
cd backend && grep -rn "from monitoring" records/ ingestion/ rag/ graph/ llm/ embeddings/ vectorstore/ analytics/ 2>/dev/null | grep -v test
```

Expected: no output. The `records/` violation is resolved by Step 3.

- [ ] **Step 6: Run tests**

```bash
cd backend && pytest tests/monitoring/ tests/records/ tests/agent/ -q --no-cov 2>&1 | tail -10
```

Expected: all tests pass. The Pydantic model is structurally identical (same fields, same validators) so no behavioral change.

- [ ] **Step 7: Commit**

```bash
cd backend && git add shared/types.py monitoring/ records/mappers/feed_mapper.py api/state.py
git commit -m "$(cat <<'EOF'
fix(arch): move MonitoringObservation to shared/types.py

records/mappers/feed_mapper.py no longer imports from monitoring/,
closing the second half of the CLAUDE.md Hard Rule 1 gap.
monitoring/models.py re-exports MonitoringObservation from shared/types
so existing internal consumers and external callers via
monitoring/__init__.py continue to work.
EOF
)"
```

---

## Task 8: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full architectural-rule grep**

```bash
cd backend && grep -rn "from api\." agent/ records/ ingestion/ monitoring/ rag/ graph/ llm/ embeddings/ vectorstore/ analytics/ 2>/dev/null | grep -v test
```

Expected: empty.

```bash
cd backend && grep -rn "from monitoring" records/ ingestion/ rag/ graph/ llm/ embeddings/ vectorstore/ analytics/ 2>/dev/null | grep -v test
```

Expected: empty.

- [ ] **Step 2: pyright strict on the entire backend**

```bash
cd backend && pyright . 2>&1 | tail -5
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 3: Full test suite with coverage**

```bash
cd backend && pytest --cov 2>&1 | tail -20
```

Expected: all tests pass, total coverage ≥ 85%.

- [ ] **Step 4: ruff clean on all touched files**

```bash
cd backend && ruff check knowledgebases/ monitoring/ records/mappers/feed_mapper.py api/ shared/types.py
```

Expected: no findings.

- [ ] **Step 5: Update `docs/architecture.md`**

Add `knowledgebases/` to the backend module map (under § "Backend Module Map (Target)"). Add `MonitoringObservation` to the list of types in `shared/types.py` referenced in the architecture doc. Read `docs/architecture.md` for the exact wording style and add accordingly.

- [ ] **Step 6: Commit the docs update**

```bash
git add docs/architecture.md
git commit -m "docs: document knowledgebases/ module + MonitoringObservation in shared/"
```

---

## Acceptance Criteria — Sign-off Checklist

- [ ] `backend/knowledgebases/` module exists with the standard layout (`__init__.py`, `protocols.py`, `models.py`, `snapshots.py`, `adapters/in_memory.py`, `adapters/object_store.py`).
- [ ] `backend/api/_kb_store.py` is deleted.
- [ ] `grep -rn "from api\." backend/agent/ backend/records/ backend/ingestion/ backend/monitoring/ backend/rag/ backend/graph/ backend/llm/ backend/embeddings/ backend/vectorstore/ backend/analytics/` (excluding tests) returns no matches.
- [ ] `grep -rn "from monitoring" backend/records/ backend/ingestion/ backend/rag/ backend/graph/` (excluding tests) returns no matches.
- [ ] `MonitoringObservation` is defined in `backend/shared/types.py` and re-exported from `backend/monitoring/models.py` and `backend/monitoring/__init__.py`.
- [ ] `pyright` clean, `ruff check` clean, `pytest --cov` shows ≥ 85% coverage on all packages.
- [ ] `docs/architecture.md` lists `backend/knowledgebases/` in the module map.

## Scope Discipline

- **Do NOT** refactor the `KnowledgeBaseRepository` Protocol signature itself. Move-only; behavior unchanged.
- **Do NOT** rename `DocumentRecord`, `InMemoryKnowledgeBaseRepository`, or `ObjectStoreKnowledgeBaseRepository`. Same names in the new location.
- **Do NOT** introduce a new "knowledgebases-service" layer or any new abstraction. The Protocol + two adapters is the entire module.
- **Do NOT** attempt to drop the re-export shim in `monitoring/models.py` and `monitoring/__init__.py` in this theme. That's a separate cleanup once external consumers (if any exist outside the backend codebase) have migrated.
- **Do NOT** address the broader "monitoring should consume observations via the event bus instead of via Pydantic import" architectural question. The cross-module-import rule is satisfied by moving the type into `shared/`; redesigning the contract is a separate effort.
