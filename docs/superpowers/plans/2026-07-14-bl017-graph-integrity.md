# BL-017 Graph Integrity + Version/Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relationship upserts reject dangling endpoints (no phantom Neo4j nodes), bulk entity/relationship upserts merge properties instead of blindly overwriting, and `version` becomes an adapter-owned counter with optimistic-conflict detection — per `docs/superpowers/specs/2026-07-14-bl017-graph-integrity-design.md`.

**Architecture:** New typed exceptions (`GraphIntegrityError`, `GraphVersionConflictError`) and a `GraphUpsertOptions` transport model carry three knobs (`merge_mode`, `expected_version`, `integrity_mode`) through the `GraphRepository` protocol into both adapters. The in-memory adapter does the merge/version logic inline; the Neo4j adapter does an atomic read-modify-write inside the caller's transaction (its `_run_read`/`_run_write` reuse the active transaction) with one batched existence query per relationship batch. The coordinator classifies `GraphIntegrityError` as permanent and converts it to a per-document `DocumentsFailedEvent` (BL-041 machinery).

**Tech Stack:** Python 3.12, Pydantic v2, Neo4j driver (fake-driver unit tests + `-m integration` live tests), pytest, pyright --strict.

## Global Constraints

- Product-owner rulings (spec §"Product-owner rulings"): doc-path integrity failure **fails the document**; records flow **strict from day one**; version conflicts **pipeline-internal** (no API/contract/frontend changes, no OpenAPI regen).
- `merge_properties` is a **shallow top-level-key merge** (the `update_entity_properties` pattern): payload keys overwrite (including explicit `None`), absent keys are preserved, nested dicts replace wholesale.
- `version` is platform-owned: adapters ignore incoming `version` on upsert; stored version increments by 1 **only on effective change** — post-merge `properties` or `type` differ (for relationships: `properties`, `type`, or `weight`). Metadata-only changes write but do not bump `version`. A true no-op leaves the stored row untouched.
- `expected_version` conflict checks are a **pre-pass over the whole batch** before any write (so a conflict writes nothing), raising `GraphVersionConflictError`.
- Run gates from `backend/`: `.venv/bin/pytest tests/graph tests/agent -q`, `.venv/bin/pyright` (bare — include-scoped tests must be strict-clean), `.venv/bin/ruff check --no-cache .`. Coverage ≥ 85% on `graph/`.
- Never import private `_helpers` into test modules (pyright `reportPrivateUsage`).
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Live verification happens **in-sprint** (sprint 2026-27 R-5) — Task 7 includes it; do not defer.

---

### Task 1: Typed exceptions + GraphUpsertOptions

**Files:**
- Modify: `backend/graph/exceptions.py`
- Modify: `backend/graph/models.py`
- Test: `backend/tests/graph/test_models.py`

**Interfaces:**
- Produces: `GraphIntegrityError(GraphPersistenceError)` with `.knowledge_base_id: str`, `.missing_entity_ids: list[str]`, `.relationship_ids: list[str]`; `GraphVersionConflictError(GraphPersistenceError)` with `.entity_id: str`, `.expected_version: int`, `.actual_version: int`; `GraphUpsertOptions(BaseModel)` with `merge_mode: Literal["merge_properties","replace_properties"] = "merge_properties"`, `expected_version: int | None = None`, `integrity_mode: Literal["strict","create_placeholders"] = "strict"`. All later tasks consume exactly these names.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/graph/test_models.py`:

```python
from graph.exceptions import GraphIntegrityError, GraphVersionConflictError
from graph.models import GraphUpsertOptions


def test_graph_integrity_error_carries_missing_endpoints() -> None:
    error = GraphIntegrityError(
        knowledge_base_id="kb-1",
        missing_entity_ids=["e-2", "e-3"],
        relationship_ids=["r-1"],
    )
    assert error.knowledge_base_id == "kb-1"
    assert error.missing_entity_ids == ["e-2", "e-3"]
    assert error.relationship_ids == ["r-1"]
    assert "e-2" in str(error)


def test_graph_version_conflict_error_carries_versions() -> None:
    error = GraphVersionConflictError(
        entity_id="e-1", expected_version=3, actual_version=5
    )
    assert error.entity_id == "e-1"
    assert error.expected_version == 3
    assert error.actual_version == 5
    assert "e-1" in str(error)


def test_graph_upsert_options_defaults() -> None:
    options = GraphUpsertOptions()
    assert options.merge_mode == "merge_properties"
    assert options.expected_version is None
    assert options.integrity_mode == "strict"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/graph/test_models.py -q`
Expected: FAIL with `ImportError` (names not defined).

- [ ] **Step 3: Implement.** In `backend/graph/exceptions.py`, insert after `GraphPersistenceError` and add both classes to `__all__` (keep it case-sensitively sorted):

```python
class GraphIntegrityError(GraphPersistenceError):
    """Raised when a relationship references entity endpoints that do not exist."""

    def __init__(
        self,
        knowledge_base_id: str,
        missing_entity_ids: list[str],
        relationship_ids: list[str],
    ) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.missing_entity_ids = missing_entity_ids
        self.relationship_ids = relationship_ids
        super().__init__(
            f"Relationship upsert references missing entities {missing_entity_ids} "
            f"in knowledge base '{knowledge_base_id}' "
            f"(relationships: {relationship_ids})."
        )


class GraphVersionConflictError(GraphPersistenceError):
    """Raised when an upsert's expected_version does not match the stored version."""

    def __init__(
        self, entity_id: str, expected_version: int, actual_version: int
    ) -> None:
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict on entity '{entity_id}': expected "
            f"{expected_version}, stored {actual_version}."
        )
```

In `backend/graph/models.py`, add `Literal` to the imports (`from typing import Literal`) and insert before `GraphUpsertResult`; add `"GraphUpsertOptions"` to `__all__` (sorted):

```python
class GraphUpsertOptions(BaseModel):
    """Caller-selectable semantics for bulk graph upserts (BL-017)."""

    merge_mode: Literal["merge_properties", "replace_properties"] = "merge_properties"
    expected_version: int | None = None
    integrity_mode: Literal["strict", "create_placeholders"] = "strict"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/graph/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/graph/exceptions.py backend/graph/models.py backend/tests/graph/test_models.py
git commit -m "feat(graph): GraphIntegrityError, GraphVersionConflictError, GraphUpsertOptions (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: In-memory entity upsert — merge, adapter-owned version, conflict pre-pass

**Files:**
- Modify: `backend/graph/adapters/protocols.py` (both upsert signatures)
- Modify: `backend/graph/adapters/in_memory.py`
- Test: `backend/tests/graph/test_in_memory_adapter.py`

**Interfaces:**
- Consumes: Task 1's `GraphUpsertOptions`, `GraphVersionConflictError`.
- Produces: `GraphRepository.upsert_entities(knowledge_base_id: str, entities: list[Entity], options: GraphUpsertOptions | None = None) -> list[Entity]` and the same trailing `options` parameter on `upsert_relationships` (implemented for relationships in Task 3). Insert semantics: new entities always store `version=1` regardless of payload. Tasks 4–6 rely on these exact signatures.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/graph/test_in_memory_adapter.py` (module already imports `Entity`; add `GraphUpsertOptions` / `GraphVersionConflictError` imports at the top):

```python
from graph.exceptions import GraphVersionConflictError
from graph.models import GraphUpsertOptions


def _entity(entity_id: str, *, properties: dict[str, object] | None = None, version: int = 1) -> Entity:
    return Entity(id=entity_id, type="provider", properties=properties or {}, version=version)


def test_upsert_entities_merges_properties_by_default() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"name": "Ann", "city": "Reno"})])
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"city": "Boise", "npi": "123"})])
    stored = repo.get_entities("kb-1")[0]
    assert stored.properties == {"name": "Ann", "city": "Boise", "npi": "123"}


def test_upsert_entities_replace_mode_preserves_legacy_overwrite() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"name": "Ann", "city": "Reno"})])
    repo.upsert_entities(
        "kb-1",
        [_entity("e-1", properties={"city": "Boise"})],
        GraphUpsertOptions(merge_mode="replace_properties"),
    )
    assert repo.get_entities("kb-1")[0].properties == {"city": "Boise"}


def test_upsert_entities_explicit_none_overwrites_in_merge_mode() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"city": "Reno"})])
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"city": None})])
    assert repo.get_entities("kb-1")[0].properties == {"city": None}


def test_upsert_entities_version_is_adapter_owned() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"a": 1}, version=99)])
    assert repo.get_entities("kb-1")[0].version == 1  # incoming version ignored
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"a": 2}, version=99)])
    assert repo.get_entities("kb-1")[0].version == 2  # effective change bumps


def test_upsert_entities_noop_replay_does_not_bump_version() -> None:
    repo = InMemoryGraphRepository()
    payload = _entity("e-1", properties={"a": 1})
    repo.upsert_entities("kb-1", [payload])
    repo.upsert_entities("kb-1", [payload.model_copy(deep=True)])
    assert repo.get_entities("kb-1")[0].version == 1


def test_upsert_entities_version_conflict_writes_nothing() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1", properties={"a": 1})])
    with pytest.raises(GraphVersionConflictError) as excinfo:
        repo.upsert_entities(
            "kb-1",
            [_entity("e-1", properties={"a": 2})],
            GraphUpsertOptions(expected_version=7),
        )
    assert excinfo.value.entity_id == "e-1"
    assert excinfo.value.expected_version == 7
    assert excinfo.value.actual_version == 1
    assert repo.get_entities("kb-1")[0].properties == {"a": 1}  # nothing written
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/graph/test_in_memory_adapter.py -q`
Expected: FAIL (merge/version behavior not implemented; `options` parameter missing).

- [ ] **Step 3: Update the protocol.** In `backend/graph/adapters/protocols.py`, import the options model (`from graph.models import GraphDeleteByProvenance, GraphUpsertOptions, SubgraphResult`) and change both upsert signatures:

```python
    def upsert_entities(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        options: GraphUpsertOptions | None = None,
    ) -> list[Entity]: ...

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
        options: GraphUpsertOptions | None = None,
    ) -> list[Relationship]: ...
```

- [ ] **Step 4: Implement in-memory entity semantics.** In `backend/graph/adapters/in_memory.py`, add imports (`from graph.exceptions import GraphVersionConflictError`, `from graph.models import GraphDeleteByProvenance, GraphUpsertOptions, SubgraphResult`, `from shared.utils import utc_now`), delete the class-level `TODO(production)` comment block (this story retires it), and replace `upsert_entities`:

```python
    def upsert_entities(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        options: GraphUpsertOptions | None = None,
    ) -> list[Entity]:
        opts = options or GraphUpsertOptions()
        entity_bucket = self._entities.setdefault(knowledge_base_id, {})
        if opts.expected_version is not None:
            # Conflict pre-pass over the whole batch: a conflict writes nothing.
            for entity in entities:
                existing = entity_bucket.get(entity.id)
                if existing is not None and existing.version != opts.expected_version:
                    raise GraphVersionConflictError(
                        entity.id, opts.expected_version, existing.version
                    )
        stored: list[Entity] = []
        for entity in entities:
            existing = entity_bucket.get(entity.id)
            if existing is None:
                # version is platform-owned: inserts always start at 1.
                record = entity.model_copy(update={"version": 1})
                entity_bucket[entity.id] = record
                stored.append(record)
                continue
            if opts.merge_mode == "merge_properties":
                properties = {**existing.properties, **entity.properties}
                metadata = {**existing.metadata, **entity.metadata}
            else:
                properties = dict(entity.properties)
                metadata = dict(entity.metadata)
            effective_change = (
                properties != existing.properties or entity.type != existing.type
            )
            if not effective_change and metadata == existing.metadata:
                stored.append(existing)  # true no-op: row untouched
                continue
            record = existing.model_copy(
                update={
                    "type": entity.type,
                    "properties": properties,
                    "metadata": metadata,
                    "updated_at": entity.updated_at or utc_now(),
                    "version": existing.version + 1 if effective_change else existing.version,
                }
            )
            entity_bucket[entity.id] = record
            stored.append(record)
        return stored
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/graph/test_in_memory_adapter.py tests/graph/test_service.py -q`
Expected: PASS (existing service tests must stay green — the `options` parameter defaults keep call sites compatible; note `upsert_entities` now returns stored records, e.g. `version=1` even when the payload claimed 99).

- [ ] **Step 6: Commit**

```bash
git add backend/graph/adapters/protocols.py backend/graph/adapters/in_memory.py backend/tests/graph/test_in_memory_adapter.py
git commit -m "feat(graph): in-memory entity merge semantics + adapter-owned version + conflict pre-pass (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: In-memory relationship upsert — strict integrity + merge/version

**Files:**
- Modify: `backend/graph/adapters/in_memory.py`
- Test: `backend/tests/graph/test_in_memory_adapter.py`

**Interfaces:**
- Consumes: Task 1's `GraphIntegrityError`, Task 2's `options` signature.
- Produces: strict-mode `upsert_relationships` raising `GraphIntegrityError` listing **every** missing endpoint ID and every referencing relationship ID; `create_placeholders` preserves legacy write-through (endpoints stay absent from the entity bucket in-memory — this adapter never fabricated placeholder entities; the mode simply skips the check).

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/graph/test_in_memory_adapter.py` (add `GraphIntegrityError` to the exceptions import; module already imports `Relationship`):

```python
def _relationship(rel_id: str, source: str, target: str, *, weight: float | None = None) -> Relationship:
    return Relationship(
        id=rel_id, type="billed", source_id=source, target_id=target, weight=weight
    )


def test_upsert_relationships_strict_rejects_missing_endpoints() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1")])
    with pytest.raises(GraphIntegrityError) as excinfo:
        repo.upsert_relationships(
            "kb-1",
            [_relationship("r-1", "e-1", "e-missing"), _relationship("r-2", "e-ghost", "e-1")],
        )
    assert sorted(excinfo.value.missing_entity_ids) == ["e-ghost", "e-missing"]
    assert sorted(excinfo.value.relationship_ids) == ["r-1", "r-2"]
    assert repo.get_relationships("kb-1") == []  # nothing written


def test_upsert_relationships_create_placeholders_preserves_legacy() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_relationships(
        "kb-1",
        [_relationship("r-1", "e-1", "e-2")],
        GraphUpsertOptions(integrity_mode="create_placeholders"),
    )
    assert len(repo.get_relationships("kb-1")) == 1


def test_upsert_relationships_merge_and_version() -> None:
    repo = InMemoryGraphRepository()
    repo.upsert_entities("kb-1", [_entity("e-1"), _entity("e-2")])
    first = _relationship("r-1", "e-1", "e-2")
    first.properties = {"amount": 10}
    repo.upsert_relationships("kb-1", [first])
    second = _relationship("r-1", "e-1", "e-2", weight=0.5)
    second.properties = {"code": "A1"}
    repo.upsert_relationships("kb-1", [second])
    stored = repo.get_relationships("kb-1")[0]
    assert stored.properties == {"amount": 10, "code": "A1"}
    assert stored.weight == 0.5
    assert stored.version == 2
    repo.upsert_relationships("kb-1", [second.model_copy(deep=True)])
    assert repo.get_relationships("kb-1")[0].version == 2  # no-op replay
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/graph/test_in_memory_adapter.py -q`
Expected: FAIL (no integrity check, no merge/version on relationships).

- [ ] **Step 3: Implement.** Replace `upsert_relationships` in `backend/graph/adapters/in_memory.py`:

```python
    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
        options: GraphUpsertOptions | None = None,
    ) -> list[Relationship]:
        opts = options or GraphUpsertOptions()
        entity_bucket = self._entities.get(knowledge_base_id, {})
        if opts.integrity_mode == "strict":
            missing_ids: set[str] = set()
            offending: list[str] = []
            for relationship in relationships:
                dangling = [
                    endpoint
                    for endpoint in (relationship.source_id, relationship.target_id)
                    if endpoint not in entity_bucket
                ]
                if dangling:
                    missing_ids.update(dangling)
                    offending.append(relationship.id)
            if missing_ids:
                raise GraphIntegrityError(
                    knowledge_base_id=knowledge_base_id,
                    missing_entity_ids=sorted(missing_ids),
                    relationship_ids=offending,
                )
        relationship_bucket = self._relationships.setdefault(knowledge_base_id, {})
        if opts.expected_version is not None:
            for relationship in relationships:
                existing = relationship_bucket.get(relationship.id)
                if existing is not None and existing.version != opts.expected_version:
                    raise GraphVersionConflictError(
                        relationship.id, opts.expected_version, existing.version
                    )
        stored: list[Relationship] = []
        for relationship in relationships:
            existing = relationship_bucket.get(relationship.id)
            if existing is None:
                record = relationship.model_copy(update={"version": 1})
                relationship_bucket[relationship.id] = record
                stored.append(record)
                continue
            if opts.merge_mode == "merge_properties":
                properties = {**existing.properties, **relationship.properties}
                metadata = {**existing.metadata, **relationship.metadata}
            else:
                properties = dict(relationship.properties)
                metadata = dict(relationship.metadata)
            effective_change = (
                properties != existing.properties
                or relationship.type != existing.type
                or relationship.weight != existing.weight
            )
            if not effective_change and metadata == existing.metadata:
                stored.append(existing)
                continue
            record = existing.model_copy(
                update={
                    "type": relationship.type,
                    "properties": properties,
                    "metadata": metadata,
                    "weight": relationship.weight,
                    "updated_at": relationship.updated_at or utc_now(),
                    "version": existing.version + 1 if effective_change else existing.version,
                }
            )
            relationship_bucket[relationship.id] = record
            stored.append(record)
        self._adjacency_is_stale.add(knowledge_base_id)
        return stored
```

- [ ] **Step 4: Run the graph suite**

Run: `cd backend && .venv/bin/pytest tests/graph -q`
Expected: PASS. If existing tests upserted relationships without entities, update those tests to create their endpoint entities first (or pass `integrity_mode="create_placeholders"` where the test's subject is unrelated to integrity) — do not weaken the new default.

- [ ] **Step 5: Commit**

```bash
git add backend/graph/adapters/in_memory.py backend/tests/graph/test_in_memory_adapter.py
git commit -m "feat(graph): strict referential integrity + relationship merge/version in-memory (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Neo4j entity upsert — atomic read-modify-write

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py`
- Test: `backend/tests/graph/test_neo4j_adapter.py`

**Interfaces:**
- Consumes: Tasks 1–2 (`GraphUpsertOptions`, `GraphVersionConflictError`, protocol signature).
- Produces: `Neo4jGraphRepository.upsert_entities(kb, entities, options=None)` doing (1) one `UNWIND $ids … MATCH` read of existing rows, (2) merge/version computation in Python (JSON compare is exact because `_dump_json_property` uses `sort_keys=True`), (3) one `UNWIND $rows … MERGE` write with fully precomputed values. Both statements run through `_run_read`/`_run_write`, which reuse the caller's active transaction — the service's `with repository.transaction(kb):` makes the pair atomic.

- [ ] **Step 1: Write the failing test** (fake-driver style used throughout `test_neo4j_adapter.py` — the fake returns queued results per statement; queue the read result then the write result):

```python
def test_upsert_entities_merges_and_bumps_version(repository_factory: Callable[[], Neo4jGraphRepository]) -> None:
    repository = repository_factory()
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    # Read pass returns the existing row; write pass echoes the merged entity.
    driver.results = [
        [
            {
                "entity_id": "e-1",
                "type": "provider",
                "properties_json": '{"city": "Reno", "name": "Ann"}',
                "metadata_json": "{}",
                "version": 1,
            }
        ],
        [_entity_record("e-1", properties_json='{"city": "Boise", "name": "Ann"}', version=2)],
    ]
    stored = repository.upsert_entities(
        "kb-1", [Entity(id="e-1", type="provider", properties={"city": "Boise"})]
    )
    read_query, read_params, _ = driver.queries[-2]
    write_query, write_params, _ = driver.queries[-1]
    assert "MATCH" in read_query and read_params["ids"] == ["e-1"]
    rows = cast(list[dict[str, object]], write_params["rows"])
    assert rows[0]["properties_json"] == '{"city": "Boise", "name": "Ann"}'
    assert rows[0]["version"] == 2
    assert stored[0].version == 2


def test_upsert_entities_version_conflict_raises_before_write(repository_factory: Callable[[], Neo4jGraphRepository]) -> None:
    repository = repository_factory()
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [
        [
            {
                "entity_id": "e-1",
                "type": "provider",
                "properties_json": "{}",
                "metadata_json": "{}",
                "version": 4,
            }
        ]
    ]
    with pytest.raises(GraphVersionConflictError):
        repository.upsert_entities(
            "kb-1",
            [Entity(id="e-1", type="provider")],
            GraphUpsertOptions(expected_version=2),
        )
    assert all(mode == "read" for _, _, mode in driver.queries[-1:])  # no write issued
```

Reuse the module's existing fixtures/helpers; if `repository_factory` or `_entity_record` don't exist under those names, adapt to the module's actual factory/record helpers (read the file first) — but keep the assertions identical.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/graph/test_neo4j_adapter.py -q -k "merge or conflict"`
Expected: FAIL.

- [ ] **Step 3: Implement.** In `backend/graph/adapters/neo4j_adapter.py`, add imports (`from graph.exceptions import GraphIntegrityError, GraphPersistenceError, GraphVersionConflictError`, `from graph.models import GraphUpsertOptions` — extend the existing import lines) and replace `upsert_entities`:

```python
    def upsert_entities(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        options: GraphUpsertOptions | None = None,
    ) -> list[Entity]:
        opts = options or GraphUpsertOptions()
        existing_rows = self._read_existing_entities(
            knowledge_base_id, [entity.id for entity in entities]
        )
        payload: list[dict[str, object]] = []
        for entity in entities:
            existing = existing_rows.get(entity.id)
            if existing is None:
                payload.append(self._entity_row(entity, version=1))
                continue
            if (
                opts.expected_version is not None
                and existing["version"] != opts.expected_version
            ):
                raise GraphVersionConflictError(
                    entity.id, opts.expected_version, cast(int, existing["version"])
                )
            new_properties_json = _dump_json_property(entity.properties)
            new_metadata_json = _dump_json_property(entity.metadata)
            if opts.merge_mode == "merge_properties":
                merged_properties = {
                    **json.loads(cast(str, existing["properties_json"])),
                    **entity.properties,
                }
                merged_metadata = {
                    **json.loads(cast(str, existing["metadata_json"])),
                    **entity.metadata,
                }
                new_properties_json = _dump_json_property(merged_properties)
                new_metadata_json = _dump_json_property(merged_metadata)
            effective_change = (
                new_properties_json != existing["properties_json"]
                or entity.type != existing["type"]
            )
            version = cast(int, existing["version"]) + (1 if effective_change else 0)
            row = self._entity_row(entity, version=version)
            row["properties_json"] = new_properties_json
            row["metadata_json"] = new_metadata_json
            payload.append(row)
        query = f"""
        UNWIND $rows AS row
        MERGE (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.entity_id}})
        ON CREATE SET entity.created_at = row.created_at
        SET entity.type = row.type,
            entity.properties_json = row.properties_json,
            entity.metadata_json = row.metadata_json,
            entity.updated_at = row.updated_at,
            entity.version = row.version
        RETURN entity
        """
        try:
            records = self._run_write(
                query, knowledge_base_id=knowledge_base_id, rows=payload
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j entities.") from exc
        return [self._record_to_entity(record, "entity") for record in records]

    def _read_existing_entities(
        self, knowledge_base_id: str, entity_ids: list[str]
    ) -> dict[str, dict[str, object]]:
        query = f"""
        UNWIND $ids AS id
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: id}})
        RETURN entity.entity_id AS entity_id, entity.type AS type,
               entity.properties_json AS properties_json,
               entity.metadata_json AS metadata_json, entity.version AS version
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=entity_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to read existing Neo4j entities.") from exc
        return {
            cast(str, record["entity_id"]): {
                "type": record["type"],
                "properties_json": record["properties_json"],
                "metadata_json": record["metadata_json"],
                "version": record["version"],
            }
            for record in records
        }

    def _entity_row(self, entity: Entity, *, version: int) -> dict[str, object]:
        return {
            "entity_id": entity.id,
            "type": entity.type,
            "properties_json": _dump_json_property(entity.properties),
            "metadata_json": _dump_json_property(entity.metadata),
            "created_at": entity.created_at.isoformat(),
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
            "version": version,
        }
```

(The old inline `payload = [...]` list comprehension is replaced by `_entity_row`. `json` and `cast` are already imported in this module — verify; add if not.)

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/graph/test_neo4j_adapter.py -q`
Expected: PASS (fix any pre-existing fake-driver tests that queued only one result for `upsert_entities` — they now need a read result queued before the write result).

- [ ] **Step 5: Commit**

```bash
git add backend/graph/adapters/neo4j_adapter.py backend/tests/graph/test_neo4j_adapter.py
git commit -m "feat(graph): Neo4j entity merge/version via atomic read-modify-write (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Neo4j relationship upsert — batched existence check + strict MATCH write

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py`
- Test: `backend/tests/graph/test_neo4j_adapter.py` (fake-driver + live `-m integration` tests)

**Interfaces:**
- Consumes: Tasks 1, 4.
- Produces: strict mode issues (1) one endpoint-existence read (`UNWIND $ids … MATCH` over distinct endpoint IDs), raising `GraphIntegrityError` with every missing ID before any write; (2) one existing-relationships read for merge/version; (3) one write whose endpoint clauses are `MATCH` (never `MERGE`) so phantom nodes are impossible. `create_placeholders` keeps the legacy `MERGE`-endpoints query verbatim (with version/merge still applied).

- [ ] **Step 1: Write the failing fake-driver tests**:

```python
def test_upsert_relationships_strict_raises_on_missing_endpoint(repository_factory: Callable[[], Neo4jGraphRepository]) -> None:
    repository = repository_factory()
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [[{"entity_id": "e-1"}]]  # existence read finds only e-1
    with pytest.raises(GraphIntegrityError) as excinfo:
        repository.upsert_relationships(
            "kb-1",
            [Relationship(id="r-1", type="billed", source_id="e-1", target_id="e-missing")],
        )
    assert excinfo.value.missing_entity_ids == ["e-missing"]
    assert excinfo.value.relationship_ids == ["r-1"]
    assert len(driver.queries) == 1  # only the existence read ran


def test_upsert_relationships_strict_write_uses_match_endpoints(repository_factory: Callable[[], Neo4jGraphRepository]) -> None:
    repository = repository_factory()
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [
        [{"entity_id": "e-1"}, {"entity_id": "e-2"}],  # existence read
        [],                                            # existing-relationships read
        [_relationship_record("r-1", "e-1", "e-2", version=1)],  # write
    ]
    repository.upsert_relationships(
        "kb-1", [Relationship(id="r-1", type="billed", source_id="e-1", target_id="e-2")]
    )
    write_query = driver.queries[-1][0]
    assert "MATCH (source" in write_query and "MATCH (target" in write_query
    assert "MERGE (source:" not in write_query and "MERGE (target:" not in write_query
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/graph/test_neo4j_adapter.py -q -k relationship`
Expected: FAIL.

- [ ] **Step 3: Implement.** Replace `upsert_relationships` in `backend/graph/adapters/neo4j_adapter.py`:

```python
    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
        options: GraphUpsertOptions | None = None,
    ) -> list[Relationship]:
        opts = options or GraphUpsertOptions()
        if opts.integrity_mode == "strict":
            endpoint_ids = sorted(
                {r.source_id for r in relationships} | {r.target_id for r in relationships}
            )
            found = self._read_existing_entity_ids(knowledge_base_id, endpoint_ids)
            missing = [eid for eid in endpoint_ids if eid not in found]
            if missing:
                offending = [
                    r.id
                    for r in relationships
                    if r.source_id in set(missing) or r.target_id in set(missing)
                ]
                raise GraphIntegrityError(
                    knowledge_base_id=knowledge_base_id,
                    missing_entity_ids=missing,
                    relationship_ids=offending,
                )
        existing_rows = self._read_existing_relationships(
            knowledge_base_id, [r.id for r in relationships]
        )
        payload: list[dict[str, object]] = []
        for relationship in relationships:
            existing = existing_rows.get(relationship.id)
            if existing is None:
                payload.append(self._relationship_row(relationship, version=1))
                continue
            if (
                opts.expected_version is not None
                and existing["version"] != opts.expected_version
            ):
                raise GraphVersionConflictError(
                    relationship.id,
                    opts.expected_version,
                    cast(int, existing["version"]),
                )
            new_properties_json = _dump_json_property(relationship.properties)
            if opts.merge_mode == "merge_properties":
                new_properties_json = _dump_json_property(
                    {
                        **json.loads(cast(str, existing["properties_json"])),
                        **relationship.properties,
                    }
                )
            effective_change = (
                new_properties_json != existing["properties_json"]
                or relationship.type != existing["type"]
                or relationship.weight != existing["weight"]
            )
            version = cast(int, existing["version"]) + (1 if effective_change else 0)
            row = self._relationship_row(relationship, version=version)
            row["properties_json"] = new_properties_json
            payload.append(row)
        endpoint_clause = (
            f"MATCH (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.source_id}})\n"
            f"        MATCH (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.target_id}})"
            if opts.integrity_mode == "strict"
            else f"MERGE (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.source_id}})\n"
            f"        MERGE (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.target_id}})"
        )
        query = f"""
        UNWIND $rows AS row
        {endpoint_clause}
        MERGE (source)-[relationship:{_RELATIONSHIP_LABEL} {{
            knowledge_base_id: $knowledge_base_id,
            relationship_id: row.relationship_id
        }}]->(target)
        ON CREATE SET relationship.created_at = row.created_at
        SET relationship.type = row.type,
            relationship.properties_json = row.properties_json,
            relationship.updated_at = row.updated_at,
            relationship.version = row.version,
            relationship.weight = row.weight
        RETURN relationship, source.entity_id AS source_id, target.entity_id AS target_id
        """
        try:
            records = self._run_write(
                query, knowledge_base_id=knowledge_base_id, rows=payload
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j relationships.") from exc
        return [self._record_to_relationship(record) for record in records]

    def _read_existing_entity_ids(
        self, knowledge_base_id: str, entity_ids: list[str]
    ) -> set[str]:
        query = f"""
        UNWIND $ids AS id
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: id}})
        RETURN entity.entity_id AS entity_id
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=entity_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to verify Neo4j entity endpoints.") from exc
        return {cast(str, record["entity_id"]) for record in records}

    def _read_existing_relationships(
        self, knowledge_base_id: str, relationship_ids: list[str]
    ) -> dict[str, dict[str, object]]:
        query = f"""
        UNWIND $ids AS id
        MATCH ()-[relationship:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id, relationship_id: id}}]->()
        RETURN relationship.relationship_id AS relationship_id,
               relationship.type AS type,
               relationship.properties_json AS properties_json,
               relationship.version AS version, relationship.weight AS weight
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=relationship_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError(
                "Failed to read existing Neo4j relationships."
            ) from exc
        return {
            cast(str, record["relationship_id"]): {
                "type": record["type"],
                "properties_json": record["properties_json"],
                "version": record["version"],
                "weight": record["weight"],
            }
            for record in records
        }

    def _relationship_row(
        self, relationship: Relationship, *, version: int
    ) -> dict[str, object]:
        return {
            "relationship_id": relationship.id,
            "type": relationship.type,
            "source_id": relationship.source_id,
            "target_id": relationship.target_id,
            "properties_json": _dump_json_property(relationship.properties),
            "created_at": relationship.created_at.isoformat(),
            "updated_at": relationship.updated_at.isoformat()
            if relationship.updated_at
            else None,
            "version": version,
            "weight": relationship.weight,
        }
```

- [ ] **Step 4: Add the live integration test** (spec §7 — proves no phantom node), following the module's existing `@pytest.mark.integration` live-Neo4j fixture pattern:

```python
@pytest.mark.integration
def test_strict_upsert_creates_no_phantom_node(live_repository: Neo4jGraphRepository) -> None:
    kb = f"kb-integrity-{uuid4()}"
    live_repository.upsert_entities(kb, [Entity(id="e-1", type="provider")])
    with pytest.raises(GraphIntegrityError):
        live_repository.upsert_relationships(
            kb,
            [Relationship(id="r-1", type="billed", source_id="e-1", target_id="e-phantom")],
        )
    assert live_repository.get_entity([kb], "e-phantom") is None
    assert live_repository.get_relationships(kb) == []
    live_repository.delete_knowledge_base(kb)
```

(Adapt the fixture name to the module's live fixture; skip-unless-integration is handled by the marker.)

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/pytest tests/graph -q` then, with the dev stack's Neo4j up, `.venv/bin/pytest tests/graph/test_neo4j_adapter.py -m integration -q`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/graph/adapters/neo4j_adapter.py backend/tests/graph/test_neo4j_adapter.py
git commit -m "feat(graph): Neo4j strict endpoint integrity + relationship merge/version (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Service + GraphBuildTask plumbing

**Files:**
- Modify: `backend/graph/service_models.py` (GraphBuildTask)
- Modify: `backend/graph/service.py` (`_upsert_entities`, `_upsert_relationships`, `upsert_records_graph`)
- Test: `backend/tests/graph/test_service.py`, `backend/tests/graph/test_records_graph.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `GraphBuildTask.upsert_options: GraphUpsertOptions | None = None`; `GraphService.upsert_task` passes `task.upsert_options or GraphUpsertOptions()` to both repository calls; `upsert_records_graph(knowledge_base_id, entities, relationships, options: GraphUpsertOptions | None = None)` does the same. `BatchUpsertError.__cause__` carries the underlying `GraphIntegrityError` / `GraphVersionConflictError` (already true via `raise … from exc` — pinned by test). Task 7 relies on `exc.__cause__` introspection.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/graph/test_service.py`:

```python
def test_upsert_task_chains_integrity_error() -> None:
    repository = InMemoryGraphRepository()
    service = build_service(repository)  # use the module's existing service factory helper
    task = build_task(  # use the module's existing task helper
        entities=[Entity(id="e-1", type="provider")],
        relationships=[
            Relationship(id="r-1", type="billed", source_id="e-1", target_id="e-missing")
        ],
    )
    with pytest.raises(BatchUpsertError) as excinfo:
        service.upsert_task(task)
    assert isinstance(excinfo.value.__cause__, GraphIntegrityError)
    assert excinfo.value.__cause__.missing_entity_ids == ["e-missing"]


def test_upsert_task_honors_create_placeholders_option() -> None:
    repository = InMemoryGraphRepository()
    service = build_service(repository)
    task = build_task(
        entities=[],
        relationships=[
            Relationship(id="r-1", type="billed", source_id="e-a", target_id="e-b")
        ],
        upsert_options=GraphUpsertOptions(integrity_mode="create_placeholders"),
    )
    receipt = service.upsert_task(task)
    assert receipt.upserted_relationship_count == 1
```

(`build_service` / `build_task` stand for whatever construction helpers `test_service.py` already uses — read the module and reuse its existing fixtures; the helper must now accept an optional `upsert_options` passthrough.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/graph/test_service.py -q -k "chains or placeholders"`
Expected: FAIL (`GraphBuildTask` has no `upsert_options`).

- [ ] **Step 3: Implement.** In `backend/graph/service_models.py`, import `GraphUpsertOptions` from `graph.models` and add to `GraphBuildTask` after `relationships`:

```python
    upsert_options: GraphUpsertOptions | None = None
```

In `backend/graph/service.py`, import `GraphUpsertOptions` and thread options through — in `_upsert_entities` and `_upsert_relationships` replace the repository calls:

```python
        options = task.upsert_options or GraphUpsertOptions()
        # ...inside the loop:
                    stored_entities.extend(
                        self._repository.upsert_entities(
                            task.knowledge_base_id,
                            entity_batch,
                            options,
                        )
                    )
```

(and identically `self._repository.upsert_relationships(task.knowledge_base_id, relationship_batch, options)`). In `upsert_records_graph`, add the parameter and pass it through both calls:

```python
    def upsert_records_graph(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        relationships: list[Relationship],
        options: GraphUpsertOptions | None = None,
    ) -> tuple[list[Entity], list[Relationship]]:
        resolved_options = options or GraphUpsertOptions()
```

passing `resolved_options` as the third argument to both `upsert_entities` and `upsert_relationships` calls.

- [ ] **Step 4: Run the full graph + records suites**

Run: `cd backend && .venv/bin/pytest tests/graph tests/records -q`
Expected: PASS. `test_records_graph.py` exercises `upsert_records_graph` — records flow is now strict by default (ruling 2); fix any test data that relied on dangling endpoints by adding the endpoint entities (they were exercising the phantom-node bug).

- [ ] **Step 5: Commit**

```bash
git add backend/graph/service_models.py backend/graph/service.py backend/tests/graph/
git commit -m "feat(graph): plumb GraphUpsertOptions through GraphBuildTask and records upserts (BL-017)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Coordinator per-document isolation + docs + live verification

**Files:**
- Modify: `backend/agent/coordinator.py` (`handle_entities_validated`, ~line 1687)
- Modify: `backend/graph/service.py:29` (retire the idempotency `TODO(production)` comment — delivered by change detection)
- Modify: `backend/graph/README.md`, `backend/agent/README.md`, `docs/backlog/graph.md` (story statuses), `docs/project/planning/backlog.md`, `docs/project/planning/sprints/2026-27.md`
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `BatchUpsertError.__cause__` introspection (Task 6), `GraphIntegrityError` (Task 1), BL-041's `DocumentFailureReference`/`DocumentsFailedEvent`, BL-043's `ingestion_documents_failed_total` + `log_stage` (both in `shared/metrics.py`, already imported by `coordinator.py`).
- Produces: a `GraphIntegrityError`-caused upsert failure fails only that document; other exceptions still propagate to retry/DLQ.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/agent/test_coordinator.py`, mirroring the module's existing `handle_documents_parsed` isolation tests (reuse its event/fixture helpers):

```python
def test_handle_entities_validated_isolates_integrity_failure() -> None:
    # Arrange: two documents; doc-bad's validation report contains a
    # relationship whose endpoint entity is absent from the graph.
    # (Build both ValidationReports, store them via InMemoryObjectStore,
    # and construct the EntitiesValidatedEvent exactly like the module's
    # existing handle_entities_validated tests do.)
    event_bus = InMemoryEventBus()
    processed = handle_entities_validated(
        event,
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
    )
    assert processed == 1  # the good document still processed
    failed_events = [
        e for e in event_bus.published_events if isinstance(e, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert "missing" in failed_events[0].documents[0].error_message.lower()
    graph_events = [
        e for e in event_bus.published_events if isinstance(e, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1  # only the good document advanced
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/agent/test_coordinator.py -q -k entities_validated`
Expected: FAIL — `handle_entities_validated` has no `event_bus` parameter and no isolation.

- [ ] **Step 3: Implement.** Rewrite `handle_entities_validated` in `backend/agent/coordinator.py` (adding the `event_bus` keyword and updating `_dispatch_event`'s call site to pass it — same wiring style as `handle_documents_parsed`):

```python
def handle_entities_validated(
    event: EntitiesValidatedEvent,
    *,
    graph_service: GraphService,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Upsert validated runtime objects into the graph and publish graph updates.

    Per-document isolation (BL-017): a ``GraphIntegrityError`` chained inside
    ``BatchUpsertError`` is a permanent failure — the document's relationships
    reference endpoints that do not exist in the graph — so it fails only that
    document via ``DocumentsFailedEvent``. Any other upsert failure (e.g. a
    transient Neo4j error) propagates to the retry/DLQ wrapper.
    """
    processed = 0
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        if document.validation_storage_key is None:
            raise ValueError("EntitiesValidatedEvent requires validation_storage_key for graph updates.")
        stored = object_store.get_bytes(document.validation_storage_key)
        validation_report = ValidationReport.model_validate_json(stored.content)
        try:
            graph_service.upsert_task(
                GraphBuildTask(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    parsed_document_id=document.parsed_document_id,
                    extraction_result_id=document.extraction_result_id,
                    validation_report_id=document.validation_report_id,
                    validation_storage_key=document.validation_storage_key,
                    correlation_id=event.correlation_id,
                    entities=validation_report.valid_entities,
                    relationships=validation_report.valid_relationships,
                )
            )
        except BatchUpsertError as exc:
            cause = exc.__cause__
            if not isinstance(cause, GraphIntegrityError):
                raise
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        "Graph integrity violation: relationships reference "
                        f"missing entities {cause.missing_entity_ids} "
                        f"(relationships: {cause.relationship_ids})."
                    ),
                    storage_key=document.storage_key,
                )
            )
            ingestion_documents_failed_total.labels(
                stage="graph", error_class="GraphIntegrityError"
            ).inc()
            log_stage(
                stage="graph",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
        log_stage(
            stage="graph",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="success",
        )
        processed += 1
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
            )
        )
    return processed
```

Add the imports this needs at the top of the module if not present (`from graph.exceptions import BatchUpsertError, GraphIntegrityError` — extend the existing `graph` import block). Update the `_dispatch_event` branch for `entities.validated` to pass `event_bus=event_bus`. Note `document.storage_key` — confirm `EntitiesValidatedEvent`'s reference model carries `storage_key`; if it does not, pass `storage_key=None` (the field is optional on `DocumentFailureReference`).

- [ ] **Step 4: Run the suites and static gates**

Run: `cd backend && .venv/bin/pytest tests/agent tests/graph -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: all green, pyright 0 errors.

- [ ] **Step 5: Full test run with coverage**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q`
Expected: full pass, `graph` package ≥ 85% (whole-suite aggregate ≥ 85%). (The `chili_test` DATABASE_URL guard keeps the dev-stack `chili` database from being wiped — CLAUDE.md tooling gotcha.)

- [ ] **Step 6: Live full-stack verification (in-sprint, sprint R-5 — do not defer)**

With `make dev` up (worker recreated so it loads the new code):
1. Re-ingest the same document twice into one KB → second run: document ready, stored entity `version` unchanged (inspect via the graph API or `docker compose -f docker-compose.dev.yaml exec neo4j cypher-shell`).
2. Craft a validation report defect (or use a records push whose relationship references a nonexistent entity) → document shows `FAILED` with the integrity reason in `GET /knowledgebases/{kb_id}/documents`; sibling documents in the same batch unaffected; `ingestion_documents_failed_total{stage="graph",error_class="GraphIntegrityError"}` visible on `:8001/metrics`.
3. Confirm no phantom node: the missing endpoint ID does not exist as an entity afterward.

- [ ] **Step 7: Update docs + backlog.** Retire `graph/service.py:29`'s TODO comment. Update `backend/graph/README.md` (integrity modes, merge/version semantics, options plumbing) and `backend/agent/README.md` (graph-stage isolation). Flip `docs/backlog/graph.md` graph.01 + graph.02 → `done` with Done lines (`2026-07-XX · BL-017 (Sprint 2026-27) · <branch>`) and all AC boxes checked — note the two deliberate deviations in each story body: `integrity_mode` travels inside `GraphUpsertOptions` rather than as a separate service kwarg, and `merge_properties` is shallow (the spec resolves the story's "deep-merge" wording). Update `docs/project/planning/backlog.md` BL-017 → done and the sprint file's progress section. Run `backend/.venv/bin/python scripts/backlog_consistency.py --check` — must exit 0.

- [ ] **Step 8: Commit**

```bash
git add backend/agent/coordinator.py backend/graph/service.py backend/tests/agent/test_coordinator.py backend/graph/README.md backend/agent/README.md docs/
git commit -m "feat(agent): per-document isolation for graph integrity failures; BL-017 docs closeout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (already applied)

- Spec coverage: §1→Tasks 3/5, §2→Task 7, §3→Tasks 2/3/4/5, §4→Tasks 2/3/4/5, §5→Task 6, §6 housekeeping→prereq cleanup already landed with the spec commit (`b5b820e`); story-status flips→Task 7, §7 testing→each task + Task 7 steps 5–6.
- Type consistency: `GraphUpsertOptions` fields and both exception signatures are identical across Tasks 1–7; repository upsert signatures introduced in Task 2 are consumed verbatim in Tasks 4–6.
- Fake-driver test helpers (`repository_factory`, `_entity_record`, `_relationship_record`, `live_repository`, `build_service`, `build_task`) are placeholders for the modules' *existing* helpers — implementers must read the test module first and reuse its actual fixture names; assertions are normative, helper names are not.
