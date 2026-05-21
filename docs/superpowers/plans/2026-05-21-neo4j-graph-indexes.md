# Neo4j Graph Adapter Indexes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four idempotent schema statements (one composite uniqueness constraint, three composite/single indexes) to the Neo4j graph adapter so KB-scoped reads and writes stop scanning the full `:Entity` label.

**Architecture:** A new private `_ensure_schema()` method on `Neo4jGraphRepository` issues four `CREATE ... IF NOT EXISTS` statements once at adapter `__init__`. Each statement runs in its own try/except so a DDL-permission failure on one statement logs a warning and continues rather than aborting startup. The existing fake-driver test infrastructure gains tolerance for queries that don't pre-load a result (the schema statements don't need to consume rows), which keeps every existing test working unchanged.

**Tech Stack:** Python 3.12, Neo4j 5 (Python driver), pytest, pyright strict, ruff.

**Spec:** `docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md`

---

## Conventions Used Throughout

- All paths are relative to repo root unless prefixed with `/`.
- Backend commands run from `backend/` with the host venv activated: `source /home/rdhagan92/chiliAI/backend/.venv/bin/activate` followed by the command. (Per `memory/dev_environment.md`: tests, pyright, and ruff run directly on the host venv without Docker.)
- `tsc -b --noEmit` and `npm run lint` do not apply — this is a pure-backend change.
- TDD discipline: write the failing test, run it to confirm it fails, implement the minimum to make it pass, commit.

---

## Task 1: Make the fake-driver test helper tolerant of empty result queues

**Why this is first:** The schema statements issued from `__init__` don't need to consume any rows, but the existing `_FakeTransaction.run` helper does `self._driver.results.pop(0)`, which raises `IndexError` when `results` is empty. The moment we add `_ensure_schema` to `__init__`, every existing test that constructs `Neo4jGraphRepository` would break with an `IndexError` because none of them pre-load results for the four schema statements. Making the fake tolerant unblocks all subsequent work and is a no-op for tests that DO pre-load results (they still pop in order).

**Files:**
- Modify: `backend/tests/graph/test_neo4j_adapter.py` (the `_FakeTransaction.run` method around lines 97-98)

- [ ] **Step 1: Update `_FakeTransaction.run` to return `[]` when no result is pre-loaded**

Locate the existing helper class (around lines 93-98):

```python
class _FakeTransaction:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    def run(self, query: str, **parameters: object) -> list[FakeRecord]:
        return self._driver.results.pop(0)
```

Replace the `run` method body:

```python
    def run(self, query: str, **parameters: object) -> list[FakeRecord]:
        if not self._driver.results:
            return []
        return self._driver.results.pop(0)
```

The rest of the class is unchanged. This applies symmetrically to `_FakeManagedTransaction` because it inherits `run` from `_FakeTransaction`.

- [ ] **Step 2: Run the full Neo4j adapter test file to confirm no regressions**

Run:

```bash
cd /home/rdhagan92/chiliAI && source backend/.venv/bin/activate && cd backend && pytest tests/graph/test_neo4j_adapter.py -v
```

Expected: all existing tests still pass (the change is purely permissive — tests that pre-load results still pop them in order; tests that don't pre-load receive `[]` instead of raising).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/graph/test_neo4j_adapter.py
git commit -m "test(graph): make fake Neo4j transaction tolerant of empty result queues"
```

---

## Task 2: Write the failing test for schema-statement issuance and implement `_ensure_schema`

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py` (add module logger, add `_ensure_schema`, call from `__init__`)
- Modify: `backend/tests/graph/test_neo4j_adapter.py` (add test asserting the four statements are issued)

- [ ] **Step 1: Write the failing test**

Append this new test to the end of `backend/tests/graph/test_neo4j_adapter.py` (i.e. at module level, after the last existing test):

```python
def test_neo4j_repository_ensures_schema_statements_on_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )

    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None

    schema_queries = [entry[0] for entry in driver.queries]
    schema_text = "\n".join(schema_queries)

    assert "CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS" in schema_text
    assert "FOR (e:Entity)" in schema_text
    assert "REQUIRE (e.knowledge_base_id, e.entity_id) IS UNIQUE" in schema_text

    assert "CREATE INDEX entity_kb_id IF NOT EXISTS" in schema_text
    assert "ON (e.knowledge_base_id)" in schema_text

    assert "CREATE INDEX rel_kb_id_relationship_id IF NOT EXISTS" in schema_text
    assert "FOR ()-[r:RELATES]-()" in schema_text
    assert "ON (r.knowledge_base_id, r.relationship_id)" in schema_text

    assert "CREATE INDEX rel_kb_id IF NOT EXISTS" in schema_text
    assert "ON (r.knowledge_base_id)" in schema_text
```

- [ ] **Step 2: Run the failing test to confirm it fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py::test_neo4j_repository_ensures_schema_statements_on_init -v
```

Expected: FAIL — no `CREATE` statements appear in `driver.queries` because `_ensure_schema` does not exist yet.

- [ ] **Step 3: Add the module logger to the adapter**

Open `backend/graph/adapters/neo4j_adapter.py`. The current imports (lines 1-17) don't include `logging`. Add `import logging` to the standard-library import group near the top, then add a module-level logger definition immediately after the `__all__` line (which is currently around line 98). Insert:

```python
import logging
```

into the import block (after the other `from`/`import` statements, alphabetically — between `import json` (line 5) and `from collections.abc import Callable, Generator, Iterable, Sequence` (line 6) is fine; keep the import group together).

Then add the logger declaration immediately after `__all__ = ["Neo4jGraphRepository"]` (currently line 98):

```python
logger = logging.getLogger(__name__)
```

So the resulting block reads:

```python
__all__ = ["Neo4jGraphRepository"]

logger = logging.getLogger(__name__)

_MAX_NEIGHBOR_DEPTH = 5
_ENTITY_LABEL = "Entity"
_RELATIONSHIP_LABEL = "RELATES"
```

- [ ] **Step 4: Add the `_ensure_schema` method**

In the same file, add a new private method `_ensure_schema` to the `Neo4jGraphRepository` class. Place it immediately after the `close` method (currently around line 131-132). The class structure should now read:

```python
    def close(self) -> None:
        self._driver.close()

    def _ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS "
            "FOR (e:Entity) "
            "REQUIRE (e.knowledge_base_id, e.entity_id) IS UNIQUE",
            "CREATE INDEX entity_kb_id IF NOT EXISTS "
            "FOR (e:Entity) "
            "ON (e.knowledge_base_id)",
            "CREATE INDEX rel_kb_id_relationship_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id, r.relationship_id)",
            "CREATE INDEX rel_kb_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id)",
        ]
        for stmt in statements:
            with self._session() as session:
                session.execute_write(self._run_query, stmt)

    def transaction(self, knowledge_base_id: str) -> AbstractContextManager[None]:
        return self._transaction_scope()
```

Note: this version has no try/except yet — it's the minimum to make the issuance test pass. Failure tolerance comes in Task 3.

- [ ] **Step 5: Call `_ensure_schema` from `__init__`**

Locate the end of the existing `__init__` body (currently around lines 122-129):

```python
        self._database = database
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=auth,
            max_connection_pool_size=config.pool_size,
        )
        self._active_transaction: Neo4jTransactionProtocol | None = None
        self._active_session: Neo4jSessionProtocol | None = None
```

Append a call to `_ensure_schema` at the end of `__init__` (after the last assignment):

```python
        self._database = database
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=auth,
            max_connection_pool_size=config.pool_size,
        )
        self._active_transaction: Neo4jTransactionProtocol | None = None
        self._active_session: Neo4jSessionProtocol | None = None
        self._ensure_schema()
```

- [ ] **Step 6: Run the schema test to verify it passes**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py::test_neo4j_repository_ensures_schema_statements_on_init -v
```

Expected: PASS.

- [ ] **Step 7: Run the full Neo4j adapter test file to confirm no regressions**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py -v
```

Expected: all tests pass (the existing tests that pre-load `results` for their own queries are not affected by the four no-result schema queries that now also run at `__init__` — those just produce `[]` from the tolerant fake transaction).

- [ ] **Step 8: Commit**

```bash
git add backend/graph/adapters/neo4j_adapter.py backend/tests/graph/test_neo4j_adapter.py
git commit -m "feat(graph): ensure Neo4j schema indexes and constraints on adapter init"
```

---

## Task 3: Tolerate schema-statement failures with a logged warning

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py` (wrap `_ensure_schema`'s per-statement execution in try/except)
- Modify: `backend/tests/graph/test_neo4j_adapter.py` (add failure-tolerance test)

- [ ] **Step 1: Write the failing test**

Append this new test at module level in `backend/tests/graph/test_neo4j_adapter.py`, after the previous schema-issuance test:

```python
def test_neo4j_repository_tolerates_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If a single CREATE statement fails, init logs a warning and continues."""

    class _FlakySession(_FakeSession):
        def __init__(self, driver: _FakeDriver) -> None:
            super().__init__(driver)
            self._call_count = 0

        def execute_write(
            self,
            callback: Callable[..., list[FakeRecord]],
            query: str,
            **parameters: object,
        ) -> list[FakeRecord]:
            self._call_count += 1
            self._driver.queries.append((query, parameters, "write"))
            if self._call_count == 1:
                raise neo4j_adapter.Neo4jError("simulated DDL permission denied")
            return callback(_FakeTransaction(self._driver), query, **parameters)

    class _FlakyDriver(_FakeDriver):
        def session(self, **kwargs: object) -> _FlakySession:
            self.session_kwargs.append(kwargs)
            return _FlakySession(self)

    class _FlakyDatabase:
        driver_instance: _FlakyDriver | None = None

        @classmethod
        def driver(
            cls,
            uri: str,
            *,
            auth: tuple[str, str] | None,
            max_connection_pool_size: int,
        ) -> _FlakyDriver:
            cls.driver_instance = _FlakyDriver()
            return cls.driver_instance

    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FlakyDatabase)

    with caplog.at_level("WARNING", logger="graph.adapters.neo4j_adapter"):
        Neo4jGraphRepository(
            GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
            auth=("neo4j", "password"),
        )

    driver = _FlakyDatabase.driver_instance
    assert driver is not None
    # All four schema statements were still attempted even though the first one failed.
    assert len(driver.queries) == 4
    # The failure was logged at WARNING.
    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING"
    ]
    assert any("Failed to ensure Neo4j schema" in msg for msg in warning_messages)
    assert any("simulated DDL permission denied" in msg for msg in warning_messages)
```

- [ ] **Step 2: Run the failing test to confirm it fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py::test_neo4j_repository_tolerates_schema_failure -v
```

Expected: FAIL — `__init__` raises the simulated `Neo4jError` because `_ensure_schema` has no try/except yet.

- [ ] **Step 3: Add per-statement try/except + warning log in `_ensure_schema`**

In `backend/graph/adapters/neo4j_adapter.py`, replace the body of `_ensure_schema` (added in Task 2) with the failure-tolerant version:

```python
    def _ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS "
            "FOR (e:Entity) "
            "REQUIRE (e.knowledge_base_id, e.entity_id) IS UNIQUE",
            "CREATE INDEX entity_kb_id IF NOT EXISTS "
            "FOR (e:Entity) "
            "ON (e.knowledge_base_id)",
            "CREATE INDEX rel_kb_id_relationship_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id, r.relationship_id)",
            "CREATE INDEX rel_kb_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id)",
        ]
        for stmt in statements:
            try:
                with self._session() as session:
                    session.execute_write(self._run_query, stmt)
            except Neo4jError as exc:
                logger.warning("Failed to ensure Neo4j schema: %s — %s", stmt, exc)
```

Only the inner `for` loop body is changed — the statement list is identical. Each statement now runs in its own `try`/`except Neo4jError`; a failure logs at WARNING and the loop continues with the next statement.

- [ ] **Step 4: Run the failure-tolerance test to verify it passes**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py::test_neo4j_repository_tolerates_schema_failure -v
```

Expected: PASS.

- [ ] **Step 5: Re-run the full file to confirm no regressions**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/graph/adapters/neo4j_adapter.py backend/tests/graph/test_neo4j_adapter.py
git commit -m "feat(graph): tolerate Neo4j schema-statement failures with logged warning"
```

---

## Task 4: Add an idempotency test

**Files:**
- Modify: `backend/tests/graph/test_neo4j_adapter.py` (add idempotency test)

This task adds the third spec-required test. No new implementation code is needed — the implementation supports re-construction because each `CREATE ... IF NOT EXISTS` is idempotent at the Cypher level. The test verifies our code does not gate the call.

- [ ] **Step 1: Add the idempotency test**

Append at module level in `backend/tests/graph/test_neo4j_adapter.py`, after the failure-tolerance test:

```python
def test_neo4j_repository_schema_ensure_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructing the repository twice issues the schema statements both times."""
    _FakeGraphDatabase.captured = []
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)

    Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    first_driver = _FakeGraphDatabase.driver_instance
    assert first_driver is not None
    first_query_count = len(first_driver.queries)

    Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    second_driver = _FakeGraphDatabase.driver_instance
    assert second_driver is not None

    # Each construction creates a new fake driver, so the second driver's query
    # log captures its own four schema statements (independent of the first).
    assert len(first_driver.queries) == first_query_count  # first driver unchanged
    assert len(second_driver.queries) >= 4
    second_schema_text = "\n".join(entry[0] for entry in second_driver.queries)
    assert "CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS" in second_schema_text
```

- [ ] **Step 2: Run the idempotency test**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/test_neo4j_adapter.py::test_neo4j_repository_schema_ensure_is_idempotent -v
```

Expected: PASS (no new implementation is required; this verifies the existing code allows repeated construction).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/graph/test_neo4j_adapter.py
git commit -m "test(graph): cover Neo4j schema-ensure idempotency across reconstructions"
```

---

## Task 5: Document the schema invariants in the graph README

**Files:**
- Modify: `backend/graph/README.md`

- [ ] **Step 1: Read the current README**

Run:

```bash
cd /home/rdhagan92/chiliAI && cat backend/graph/README.md | head -60
```

Inspect the section structure so the new section slots in coherently (typically after an "Adapters" or "Neo4j" section).

- [ ] **Step 2: Add the schema-invariants section**

Append the following section to `backend/graph/README.md` — choose the closest existing heading level (probably `##` to sit alongside other top-level subsections). If the README is short or has no subsections, append at the end:

```markdown
## Neo4j Schema Invariants

The `Neo4jGraphRepository` adapter issues four idempotent schema statements at construction time via `_ensure_schema()`. These power KB-scoped lookups and the path-traversal filter in `get_neighbors`:

- `CREATE CONSTRAINT entity_kb_id_unique` — composite uniqueness on `(:Entity {knowledge_base_id, entity_id})`. Enforces the invariant the rest of the code assumes and provides the composite index used by every entity `MERGE` and lookup.
- `CREATE INDEX entity_kb_id` — single-column index on `(:Entity {knowledge_base_id})` for full-KB scans (`get_entities`, `get_relationships`).
- `CREATE INDEX rel_kb_id_relationship_id` — composite index on `()-[r:RELATES]-()` over `(r.knowledge_base_id, r.relationship_id)`. Powers relationship `MERGE` and lookup. A relationship key constraint would be cleaner but is Neo4j 5.7+ only; this codebase pins the major version only.
- `CREATE INDEX rel_kb_id` — single-column index on `()-[r:RELATES]-()` over `(r.knowledge_base_id)`. Powers the per-hop `kb_id` filter in the variable-length neighborhood traversal.

Each statement uses `IF NOT EXISTS` so re-construction (multiple worker processes, repeated boots) is a no-op. Statement-level failures (e.g. insufficient DDL permission) log a `WARNING` and continue — the queries still work without indexes, just slowly.

To verify the schema is in place against a running Neo4j: `CALL db.indexes()` and `CALL db.constraints()` from cypher-shell.
```

- [ ] **Step 3: Commit**

```bash
git add backend/graph/README.md
git commit -m "docs(graph): document Neo4j schema invariants enforced at adapter init"
```

---

## Task 6: Full verification pass

Run the full quality gate before declaring done.

- [ ] **Step 1: Pyright strict**

Run:

```bash
cd /home/rdhagan92/chiliAI && source backend/.venv/bin/activate && cd backend && pyright
```

Expected: no errors. `pyright` is scoped via `tool.pyright.include` in `pyproject.toml` — `graph/` is already in the include list since it's covered by existing tests.

- [ ] **Step 2: Ruff lint**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && ruff check .
```

Expected: no errors.

- [ ] **Step 3: Full pytest with coverage**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest --cov
```

Expected: all tests pass, coverage ≥ 85% for `backend/graph/` (the package gate). The three new tests sit in the existing `tests/graph/test_neo4j_adapter.py` file so they're picked up automatically.

- [ ] **Step 4: Manual verification against the running Neo4j (optional but recommended)**

The dev stack should already be running. If not: `cd /home/rdhagan92/chiliAI && make dev`.

Once up, exec into the API container and confirm the indexes exist by issuing the verification queries from the README:

```bash
docker compose -f docker-compose.dev.yaml exec neo4j cypher-shell -u neo4j -p chiliai 'SHOW INDEXES;'
docker compose -f docker-compose.dev.yaml exec neo4j cypher-shell -u neo4j -p chiliai 'SHOW CONSTRAINTS;'
```

Expected: the four expected schema objects (`entity_kb_id_unique`, `entity_kb_id`, `rel_kb_id_relationship_id`, `rel_kb_id`) appear in the listings. (The exact `cypher-shell` password depends on `.env` — adjust if needed.)

If this is a fresh dev environment that started before the change, restart the API to trigger `_ensure_schema` again:

```bash
docker compose -f docker-compose.dev.yaml restart chili-api
```

- [ ] **Step 5: No commit needed if Steps 1-4 all pass**

If anything fails, report it precisely — do not silently fix.

---

## Out of Scope (Tracked, Not Implemented)

- Cross-KB query signatures (changing `get_entity(kb_id, ...)` to `get_entity(kb_ids, ...)`) — dual-graph work.
- Domain-config-level auto-attach of a reference KB — dual-graph work.
- A KB metadata table linking transactional KBs to reference KBs — dual-graph work.
- Indexes on cross-KB join keys such as `npi` for providers — domain-shape-specific, lands with reference-data feed definitions.
- Migrating to relationship key constraints when Neo4j 5.7+ is explicitly pinned — minor follow-up if/when the compose pin tightens.

## Success Criteria (from spec)

- Constructing any `Neo4jGraphRepository` issues the four `CREATE ... IF NOT EXISTS` statements (verified by the issuance test).
- A schema-statement failure produces a `WARNING` log and does not abort `__init__` (verified by the failure-tolerance test).
- Re-construction against an already-schemed database is a no-op (verified by the idempotency test + Cypher `IF NOT EXISTS` at runtime).
- All existing tests continue to pass (the tolerant fake transaction is the bridge).
- `pyright` clean, `ruff` clean, `pytest --cov` ≥ 85% in `backend/graph/`.
- Schema objects observable in a running Neo4j via `SHOW INDEXES` / `SHOW CONSTRAINTS`.
