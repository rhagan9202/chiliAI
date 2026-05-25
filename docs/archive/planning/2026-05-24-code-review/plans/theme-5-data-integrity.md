# Theme 5 — Fix Data-Integrity Blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four data-integrity blockers — bound the monitoring dedup index, clamp GNN node scores into the `[0.0, 1.0]` contract, add a Neo4j fulltext index for entity search, and lock in the DLQ-publish ACK contract that's currently undocumented.

**Architecture:** Three sub-themes are pure code fixes; the fourth (DLQ ACK) was verified by reading `run_handler_with_retry` (`backend/agent/coordinator.py:2345-2398`) — the reviewer's claim that a DLQ-publish failure could leave an event silently ACKed is incorrect because `publish_to_dlq` is not wrapped in try/except inside `run_handler_with_retry`; if it raises, the exception propagates past the caller's `ackable.append`. The DLQ task in this plan therefore adds a docstring and a regression test that lock that contract in, rather than fixing a non-existent code bug.

**Tech Stack:** Python 3.12, Pydantic, Neo4j (Cypher fulltext), pytest

**Dependencies on other themes:** None. The four sub-themes are independent of each other and of every other theme; they can ship in any order.

---

## File Structure

**Modify (5.1 — monitoring dedup):**
- `backend/monitoring/service.py` — add eviction logic in `evaluate()`
- `backend/tests/monitoring/test_service.py` — add bounded-size test

**Modify (5.2 — GNN clamp):**
- `backend/analytics/gnn/models.py:51` — add `le=1.0`
- `backend/analytics/gnn/service.py:187-199` — normalize `_score_nodes` output
- `backend/tests/analytics/gnn/test_service.py` — add bounded-output test

**Modify (5.3 — Neo4j index):**
- `backend/graph/adapters/neo4j_adapter.py:139-159` (`_ensure_schema`) — add fulltext index
- `backend/graph/adapters/neo4j_adapter.py:408-431` (`search_entities`) — use fulltext index
- `backend/tests/graph/test_neo4j_adapter.py` (or wherever Neo4j integration tests live) — add schema + search-uses-index test

**Modify (5.4 — DLQ contract):**
- `backend/agent/coordinator.py:2345-2398` (`run_handler_with_retry`) — add docstring clause about DLQ-publish failures
- `backend/tests/agent/test_coordinator.py` (or appropriate test file) — add regression test

---

## Pre-Flight Sanity Check (do this once)

- [ ] **Baseline test pass**

```bash
cd backend && pytest --no-cov -q 2>&1 | tail -5
```

Expected: all tests pass. If any pre-existing failures, note them.

- [ ] **Confirm `_dedup_index` is unbounded**

```bash
grep -n "_dedup_index\|self\._dedup_index" backend/monitoring/service.py
```

Expected: 3 matches — line 77 (initialization), line 148 (read), line 152 (write). No `del` or eviction calls.

- [ ] **Confirm `ScoredNode.score` is unbounded**

```bash
grep -n "score:.*Field" backend/analytics/gnn/models.py
```

Expected: line 51 reads `score: float = Field(ge=0.0)` (no `le=1.0`).

- [ ] **Confirm Neo4j has no fulltext index**

```bash
grep -ni "fulltext\|FULLTEXT" backend/graph/adapters/neo4j_adapter.py
```

Expected: no matches.

---

## Sub-theme 5.1 — Bound `MonitoringService._dedup_index`

### Task 1: Write failing test that `_dedup_index` size stays bounded

**Files:**
- Modify: `backend/tests/monitoring/test_service.py` (append to existing tests)

- [ ] **Step 1: Find the existing test fixture pattern**

```bash
grep -n "MonitoringService\|_dedup_index\|def test_" backend/tests/monitoring/test_service.py | head -30
```

Read the existing fixtures (`def _service(...)` or similar — there's a helper that constructs a `MonitoringService` with stub `observation_source` and `event_bus`; reuse it).

- [ ] **Step 2: Add the failing test**

Append a new test that runs `evaluate()` with 1000 distinct `(entity_id, metric_name)` pairs spread across observations more than `dedup_window_seconds` old, and asserts the dedup index never grows beyond a bounded size (the maximum is bounded by the size of in-window observations, not by all-time observations).

```python
def test_dedup_index_evicts_entries_older_than_window() -> None:
    """Regression guard: long-running workers must not accumulate dedup
    entries beyond the dedup window. Without eviction, the dict grows
    unbounded — one entry per unique (entity_id, metric_name) ever seen.
    """
    from datetime import timedelta

    observation_source = _stub_observation_source()
    event_bus = _stub_event_bus()
    service = MonitoringService(
        observation_source,
        event_bus=event_bus,
        dedup_window_seconds=60,
    )

    # First evaluation: 500 alerts that succeed. Index has 500 entries.
    _observation_source_set_batch(
        observation_source,
        knowledge_base_id="kb-1",
        batch_id="batch-1",
        observations=_make_observations(count=500, score=0.9),
    )
    service.evaluate(
        MonitoringEvaluationRequest(
            knowledge_base_id="kb-1",
            batch_id="batch-1",
            window_minutes=5,
            min_observations_in_window=1,
            medium_threshold=0.6,
            high_threshold=0.85,
        )
    )
    assert len(service._dedup_index) == 500

    # Wait past the dedup window, then run another evaluation with
    # 500 NEW (entity_id, metric_name) pairs.
    _advance_wall_clock(service, seconds=120)
    _observation_source_set_batch(
        observation_source,
        knowledge_base_id="kb-1",
        batch_id="batch-2",
        observations=_make_observations(count=500, score=0.9, start_id=500),
    )
    service.evaluate(
        MonitoringEvaluationRequest(
            knowledge_base_id="kb-1",
            batch_id="batch-2",
            window_minutes=5,
            min_observations_in_window=1,
            medium_threshold=0.6,
            high_threshold=0.85,
        )
    )

    # After eviction at the start of evaluate(), the original 500 entries
    # (now older than the 60s window) must be gone. Only the new 500 remain.
    assert len(service._dedup_index) == 500
    assert all(
        key[0].startswith("entity-5") for key in service._dedup_index.keys()
    ), "Old entries (entity-0..entity-499) should be evicted"
```

The helper functions referenced (`_stub_observation_source`, `_stub_event_bus`, `_observation_source_set_batch`, `_make_observations`, `_advance_wall_clock`) likely already exist in the test file or need small additions. Read the existing fixtures to confirm; if `_advance_wall_clock` doesn't exist, add it as a helper that monkey-patches `utc_now` or stuffs older timestamps into the dedup index directly.

If patching `utc_now` is awkward, an alternative shape: directly populate `service._dedup_index` with stale `(now - 120s)` timestamps before the second `evaluate()` call.

- [ ] **Step 3: Run the new test and verify it fails**

```bash
cd backend && pytest tests/monitoring/test_service.py::test_dedup_index_evicts_entries_older_than_window -v
```

Expected: FAIL. After the second evaluate, the dedup index will have 1000 entries (500 stale + 500 new) because no eviction logic exists.

- [ ] **Step 4: Do not commit yet — implementation in Task 2.**

### Task 2: Add window-based eviction to `MonitoringService.evaluate`

**Files:**
- Modify: `backend/monitoring/service.py`

- [ ] **Step 1: Add eviction at the start of `evaluate()`**

In `backend/monitoring/service.py`, inside the `evaluate()` method, immediately after the `now = utc_now()` line (around line 94 — confirm via grep), add:

```python
        # Evict dedup entries older than the dedup window. Without this,
        # the dict grows unbounded in a long-running worker.
        eviction_cutoff = now - timedelta(seconds=self._dedup_window_seconds)
        self._dedup_index = {
            key: timestamp
            for key, timestamp in self._dedup_index.items()
            if timestamp >= eviction_cutoff
        }
```

The dict-comprehension assignment is O(n) on the index size and runs once per `evaluate()` call. Given the index is bounded by the eviction itself, this is amortized constant work per alert candidate over time.

- [ ] **Step 2: Run the test — passes**

```bash
cd backend && pytest tests/monitoring/test_service.py::test_dedup_index_evicts_entries_older_than_window -v
```

Expected: PASS.

- [ ] **Step 3: Run the full monitoring test suite**

```bash
cd backend && pytest tests/monitoring/ -q --no-cov 2>&1 | tail -10
```

Expected: all PASS. The existing dedup tests (the parametrized ALERT_TRANSITIONS tests, the rate-limit tests, etc.) should be unaffected.

- [ ] **Step 4: Commit**

```bash
cd backend && git add monitoring/service.py tests/monitoring/test_service.py
git commit -m "$(cat <<'EOF'
fix(monitoring): evict dedup entries older than the dedup window

MonitoringService._dedup_index previously only inserted/updated entries
and was never pruned, leaking memory in long-running workers (one entry
per unique entity_id+metric_name ever seen). evaluate() now evicts
entries older than dedup_window_seconds at the start of each call.
EOF
)"
```

---

## Sub-theme 5.2 — Clamp GNN `ScoredNode.score` into `[0.0, 1.0]`

### Task 3: Write failing test for bounded `_score_nodes` output

**Files:**
- Modify: `backend/tests/analytics/gnn/test_service.py` (append to existing tests)

- [ ] **Step 1: Find the existing analyze test pattern**

```bash
grep -n "def test_\|_score_nodes\|analyze" backend/tests/analytics/gnn/test_service.py | head -15
```

Read the existing `def test_analyze_*` tests to understand how `GnnService.analyze` is called and how `GraphSnapshot` is constructed.

- [ ] **Step 2: Add the failing test**

Append a test that constructs a dense graph (many edges with large weights, many feature dimensions with large values) and asserts every `ScoredNode.score` lands in `[0.0, 1.0]`.

```python
def test_score_nodes_output_is_clamped_to_unit_interval() -> None:
    """Regression guard: ScoredNode.score must be in [0.0, 1.0] regardless
    of input feature magnitude or edge density. Without normalization,
    downstream consumers that treat the score as a probability silently
    receive values >> 1.
    """
    # 10 nodes with large-magnitude features
    nodes = [
        GraphNodeSignal(
            entity_id=f"entity-{i}",
            feature_values=[1_000.0, 2_000.0, 3_000.0],
        )
        for i in range(10)
    ]
    # Dense edges with large weights between every pair
    edges = [
        GraphEdgeSignal(source_id=f"entity-{i}", target_id=f"entity-{j}", weight=100.0)
        for i in range(10)
        for j in range(i + 1, 10)
    ]
    snapshot = GraphSnapshot(
        knowledge_base_id="kb-1", nodes=nodes, edges=edges
    )

    snapshot_source = _stub_graph_snapshot_source(snapshot=snapshot)
    service = create_gnn_service(snapshot_source, event_bus=_stub_event_bus())
    response = service.analyze(GnnAnalysisRequest(knowledge_base_id="kb-1"))

    assert response.scored_nodes, "expected at least one scored node"
    for scored in response.scored_nodes:
        assert 0.0 <= scored.score <= 1.0, (
            f"score {scored.score} for {scored.entity_id} is outside [0,1]"
        )
```

- [ ] **Step 3: Run the new test and verify it fails**

```bash
cd backend && pytest tests/analytics/gnn/test_service.py::test_score_nodes_output_is_clamped_to_unit_interval -v
```

Expected: FAIL — either Pydantic refuses to validate `ScoredNode` (after Task 4 adds `le=1.0`) or the assertion fails. Right now, with no `le` constraint, the assertion fails because scores will be in the thousands.

- [ ] **Step 4: Do not commit yet — implementation in Task 4.**

### Task 4: Add `le=1.0` to `ScoredNode.score` and normalize `_score_nodes` output

**Files:**
- Modify: `backend/analytics/gnn/models.py:51`
- Modify: `backend/analytics/gnn/service.py:187-199`

- [ ] **Step 1: Constrain the field**

In `backend/analytics/gnn/models.py`, change line 51 from:

```python
    score: float = Field(ge=0.0)
```

to:

```python
    score: float = Field(ge=0.0, le=1.0)
```

This locks the contract at the type boundary. After this change, the test from Task 3 transitions from "assertion fails" to "Pydantic raises ValidationError when service.analyze tries to build a ScoredNode" — which is still a failure, just a different kind. That's fine; Task 4's next step fixes the producer.

- [ ] **Step 2: Normalize scores in `_score_nodes`**

In `backend/analytics/gnn/service.py`, replace the existing `_score_nodes` function (lines 187-199) with:

```python
def _score_nodes(nodes: list[GraphNodeSignal], edges: list[GraphEdgeSignal]) -> list[ScoredNode]:
    weights_by_node: dict[str, float] = {node.entity_id: 0.0 for node in nodes}
    for edge in edges:
        weights_by_node[edge.source_id] = weights_by_node.get(edge.source_id, 0.0) + edge.weight
        weights_by_node[edge.target_id] = weights_by_node.get(edge.target_id, 0.0) + edge.weight
    raw_scores = [
        (
            node.entity_id,
            _feature_magnitude(node.feature_values) + weights_by_node.get(node.entity_id, 0.0),
        )
        for node in nodes
    ]
    max_raw = max((score for _, score in raw_scores), default=0.0)
    # If every node has score 0.0, every normalized score is 0.0.
    divisor = max_raw if max_raw > 0.0 else 1.0
    return [
        ScoredNode(
            entity_id=entity_id,
            score=raw_score / divisor,
            cluster_id=_fallback_cluster_id_for_id(entity_id, nodes),
        )
        for entity_id, raw_score in raw_scores
    ]
```

Notes:
- Normalization is max-divide rather than sigmoid; max-divide preserves relative ordering and is monotonic, which is what downstream ranking consumers expect.
- `_fallback_cluster_id_for_id` is a helper that maps `entity_id` back to the corresponding `GraphNodeSignal` for cluster resolution. If `_fallback_cluster_id` currently takes a `GraphNodeSignal`, add a small adapter. Read the existing `_fallback_cluster_id` implementation (find it via grep) to decide the cleanest shape.

If keeping the existing `_fallback_cluster_id(node: GraphNodeSignal)` signature is preferred, build a node-lookup dict instead:

```python
def _score_nodes(nodes: list[GraphNodeSignal], edges: list[GraphEdgeSignal]) -> list[ScoredNode]:
    weights_by_node: dict[str, float] = {node.entity_id: 0.0 for node in nodes}
    for edge in edges:
        weights_by_node[edge.source_id] = weights_by_node.get(edge.source_id, 0.0) + edge.weight
        weights_by_node[edge.target_id] = weights_by_node.get(edge.target_id, 0.0) + edge.weight
    raw_scores: list[tuple[GraphNodeSignal, float]] = [
        (
            node,
            _feature_magnitude(node.feature_values) + weights_by_node.get(node.entity_id, 0.0),
        )
        for node in nodes
    ]
    max_raw = max((score for _, score in raw_scores), default=0.0)
    divisor = max_raw if max_raw > 0.0 else 1.0
    return [
        ScoredNode(
            entity_id=node.entity_id,
            score=raw_score / divisor,
            cluster_id=_fallback_cluster_id(node),
        )
        for node, raw_score in raw_scores
    ]
```

Choose whichever shape is consistent with the existing helper signatures; both produce the same result.

- [ ] **Step 3: Run the test — passes**

```bash
cd backend && pytest tests/analytics/gnn/test_service.py::test_score_nodes_output_is_clamped_to_unit_interval -v
```

Expected: PASS. The max-divide normalization keeps every score in `[0.0, 1.0]`.

- [ ] **Step 4: Run the full GNN test suite**

```bash
cd backend && pytest tests/analytics/gnn/ -q --no-cov 2>&1 | tail -10
```

Expected: all PASS. Existing tests that don't assert on absolute score values still pass because relative ordering is preserved.

- [ ] **Step 5: Commit**

```bash
cd backend && git add analytics/gnn/models.py analytics/gnn/service.py tests/analytics/gnn/test_service.py
git commit -m "$(cat <<'EOF'
fix(gnn): clamp ScoredNode.score into [0.0, 1.0]

The score is consumed by downstream callers (GnnNodeScore at
service.py:109,268) that treat it as a probability — but raw output
was unbounded (feature_magnitude + sum of edge weights). Add le=1.0 to
the field and normalize by the per-evaluation max in _score_nodes.
EOF
)"
```

---

## Sub-theme 5.3 — Add Neo4j fulltext index for `search_entities`

### Task 5: Add the fulltext index to `_ensure_schema`

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py:139-159` (`_ensure_schema`)

- [ ] **Step 1: Append the fulltext index statement**

In `backend/graph/adapters/neo4j_adapter.py`, update `_ensure_schema` (lines 139-159) to include the fulltext index. The updated `statements` list:

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
            "CREATE FULLTEXT INDEX entity_properties_fulltext IF NOT EXISTS "
            "FOR (e:Entity) "
            "ON EACH [e.properties_json]",
        ]
        for stmt in statements:
            try:
                with self._session() as session:
                    session.execute_write(self._run_query, stmt)
            except Neo4jError as exc:
                logger.warning("Failed to ensure Neo4j schema: %s — %s", stmt, exc)
```

The fulltext index is named `entity_properties_fulltext`. Neo4j 5+ supports the `CREATE FULLTEXT INDEX ... IF NOT EXISTS` syntax.

- [ ] **Step 2: Confirm pyright + ruff clean**

```bash
cd backend && pyright graph/adapters/neo4j_adapter.py
cd backend && ruff check graph/adapters/neo4j_adapter.py
```

Expected: 0 errors / 0 findings.

### Task 6: Rewrite `search_entities` to use the fulltext index

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py:408-431` (`search_entities`)

- [ ] **Step 1: Find the test pattern for Neo4j integration tests**

```bash
grep -n "search_entities\|@pytest.mark.integration\|def test_" backend/tests/graph/test_neo4j_adapter.py | head -20
```

If an existing `test_search_entities_*` test exists, that's your regression net. Use the same fixture pattern for any new tests.

- [ ] **Step 2: Write a failing integration test**

Append to `backend/tests/graph/test_neo4j_adapter.py`:

```python
@pytest.mark.integration
def test_search_entities_uses_fulltext_index(neo4j_adapter: Neo4jGraphRepository) -> None:
    """Regression guard: search_entities must use the fulltext index,
    not a sequential CONTAINS scan. EXPLAIN output should reference the
    NodeIndexSeekByFulltext operator.
    """
    neo4j_adapter.upsert_entities(
        knowledge_base_id="kb-1",
        entities=[
            Entity(id="provider-1", type="provider",
                   properties={"name": "Acme Medical", "npi": "1234567890"}),
            Entity(id="provider-2", type="provider",
                   properties={"name": "Brown Clinic", "npi": "0987654321"}),
        ],
    )

    # Functional: search returns the expected entity
    results = neo4j_adapter.search_entities(
        knowledge_base_ids=["kb-1"],
        query="Acme",
        limit=10,
    )
    assert len(results) == 1
    assert results[0].id == "provider-1"

    # Structural: the query plan uses the fulltext index
    with neo4j_adapter._session() as session:  # noqa: SLF001 - test-only access
        plan_result = session.run(
            "EXPLAIN CALL db.index.fulltext.queryNodes('entity_properties_fulltext', 'Acme') "
            "YIELD node WHERE node.knowledge_base_id IN ['kb-1'] "
            "RETURN node LIMIT 10"
        )
        plan_text = str(plan_result.consume().plan)
        assert "Fulltext" in plan_text, f"plan does not use fulltext index: {plan_text}"
```

The second assertion (EXPLAIN inspection) is what catches the bug: if the rewrite of `search_entities` is forgotten, the integration test will still pass the functional assertion (a sequential CONTAINS scan also finds the row) but fail the EXPLAIN assertion.

- [ ] **Step 3: Run the failing test against a live Neo4j**

```bash
cd backend && pytest tests/graph/test_neo4j_adapter.py::test_search_entities_uses_fulltext_index -v -m integration
```

Expected: FAIL — `search_entities` still uses the CONTAINS scan, so the EXPLAIN assertion fails (or the plan_text doesn't contain "Fulltext"). If the test infrastructure can't reach Neo4j locally, run `make dev` first to bring up the dev stack.

- [ ] **Step 4: Rewrite `search_entities` to use the fulltext index**

In `backend/graph/adapters/neo4j_adapter.py`, replace the `search_entities` method (lines 408-431) with:

```python
    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
    ) -> list[Entity]:
        normalized_query = query.strip()
        if normalized_query == "":
            return []

        cypher = """
        CALL db.index.fulltext.queryNodes('entity_properties_fulltext', $normalized_query)
        YIELD node, score
        WHERE node.knowledge_base_id IN $knowledge_base_ids
        RETURN node AS entity
        ORDER BY score DESC, node.entity_id
        LIMIT $limit
        """
        return self._query_entities(
            cypher,
            knowledge_base_ids=knowledge_base_ids,
            normalized_query=normalized_query,
            limit=limit,
        )
```

Key changes from the old implementation:
- `CALL db.index.fulltext.queryNodes(...)` replaces `MATCH ... WHERE ... CONTAINS`. This is the indexed lookup.
- The kb-id filter is applied as a `WHERE` clause AFTER the fulltext seek — the index seek is the hot path, the kb-id filter is a cheap predicate on the seeked rows.
- Results are ordered by Lucene relevance `score DESC` first, then by `entity_id` for stable ties.
- The `toLower()` wrapper is dropped because the fulltext index is case-insensitive by default.
- The `coalesce(entity.properties_json, "")` guard is dropped because the fulltext index ignores documents with no indexed value.

- [ ] **Step 5: Run the integration test — passes**

```bash
cd backend && pytest tests/graph/test_neo4j_adapter.py::test_search_entities_uses_fulltext_index -v -m integration
```

Expected: PASS. Both the functional and EXPLAIN assertions hold.

- [ ] **Step 6: Run the full Neo4j adapter test suite**

```bash
cd backend && pytest tests/graph/test_neo4j_adapter.py -v -m integration 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add graph/adapters/neo4j_adapter.py tests/graph/test_neo4j_adapter.py
git commit -m "$(cat <<'EOF'
fix(graph): use Neo4j fulltext index for entity property search

search_entities previously ran a `toLower(properties_json) CONTAINS`
scan over every entity in the KB — a sequential scan with no index.
Create entity_properties_fulltext during _ensure_schema and rewrite
search_entities to use db.index.fulltext.queryNodes. Includes an
integration test that asserts the query plan uses the fulltext index.
EOF
)"
```

---

## Sub-theme 5.4 — Lock in the DLQ-publish ACK contract

### Task 7: Document and test the existing DLQ contract

**Background:** The reviewer flagged `ackable.append(delivery)` (line 2510) as ACKing events even when DLQ publish failed. Verification by reading `run_handler_with_retry` (lines 2345-2398) refutes this: `publish_to_dlq` is called at line 2397 WITHOUT a try/except wrapper. If it raises, the exception propagates past the function's return, past the caller's `ackable.append`, and out of `drain_ingestion_events`. The unconditional `ackable.append` is safe because it is only reached when `run_handler_with_retry` returned (which means: handler succeeded OR DLQ-publish succeeded). The contract is correct; it's just undocumented.

**Files:**
- Modify: `backend/agent/coordinator.py` — add docstring clause on `run_handler_with_retry`
- Modify: `backend/tests/agent/test_coordinator.py` (find the appropriate test file via grep) — add regression test

- [ ] **Step 1: Find the right test file**

```bash
ls backend/tests/agent/ && grep -ln "run_handler_with_retry\|publish_to_dlq" backend/tests/agent/*.py
```

Expected: at least one file references `run_handler_with_retry`. Use that file; if none does, append to `backend/tests/agent/test_coordinator.py`.

- [ ] **Step 2: Extend the docstring on `run_handler_with_retry`**

In `backend/agent/coordinator.py`, replace the existing docstring (lines 2354-2357) with:

```python
async def run_handler_with_retry(
    handler: Callable[[], int],
    *,
    event: AnyEvent,
    event_bus: EventBus,
    retry_policy: RetryPolicy,
    sleep: Callable[[float], "asyncio.Future[None] | object"] = asyncio.sleep,
    on_failure: Callable[[BaseException], None] | None = None,
) -> int:
    """Run ``handler`` with exponential-backoff retry and DLQ on exhaustion.

    ``sleep`` is injected so unit tests can avoid waiting on the event loop.

    ACK contract: this function returns the handler's processed-count when
    the handler succeeded OR when retries are exhausted AND ``publish_to_dlq``
    succeeded (returning ``0``). If ``publish_to_dlq`` itself raises (e.g.,
    the event bus is unreachable), the exception propagates to the caller
    so the caller does NOT ACK the delivery and the event remains
    pending in the underlying stream. Callers that unconditionally ACK
    after a successful return are therefore safe; callers that ACK
    inside a broad exception handler must not catch and swallow DLQ
    publish failures.
    """
```

The added paragraph makes the previously-implicit contract explicit. Future maintainers see the rule immediately.

- [ ] **Step 3: Add a regression test for the contract**

Append to the chosen test file:

```python
async def test_dlq_publish_failure_propagates_and_does_not_ack() -> None:
    """Regression guard: when retries are exhausted AND publish_to_dlq
    raises, the exception must propagate to the caller so the delivery
    is NOT ACKed.
    """
    from agent.coordinator import run_handler_with_retry
    from events.protocols import RetryPolicy

    def always_fails() -> int:
        raise RuntimeError("handler always raises")

    event_bus = _make_event_bus_that_fails_on_dlq()
    event = _make_test_event()

    with pytest.raises(EventBusError) as excinfo:
        await run_handler_with_retry(
            always_fails,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=2, initial_delay_seconds=0.0),
            sleep=_no_op_sleep,
        )

    assert "DLQ publish failed" in str(excinfo.value) or "dlq" in str(excinfo.value).lower()


def _make_event_bus_that_fails_on_dlq() -> EventBus:
    """Stub event bus whose publish_to_dlq always raises."""
    bus = MagicMock(spec=EventBus)
    bus.publish_to_dlq.side_effect = EventBusError("DLQ publish failed")
    return bus
```

The exact names — `EventBusError`, `RetryPolicy`, the event factory — depend on what the existing test fixtures provide. Read the file's existing imports + helpers and adapt. If `EventBusError` doesn't exist, use the actual exception type raised by the Redis adapter (e.g., `redis.exceptions.ConnectionError`); the point is "any exception raised by `publish_to_dlq` must propagate."

- [ ] **Step 4: Run the test — passes**

```bash
cd backend && pytest tests/agent/<chosen_file>.py::test_dlq_publish_failure_propagates_and_does_not_ack -v
```

Expected: PASS. The current code already meets the contract; this test pins it in place against future refactors.

- [ ] **Step 5: Run the full agent test suite**

```bash
cd backend && pytest tests/agent/ -q --no-cov 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd backend && git add agent/coordinator.py tests/agent/<chosen_file>.py
git commit -m "$(cat <<'EOF'
docs(agent): document and pin run_handler_with_retry DLQ ACK contract

run_handler_with_retry's behavior on DLQ-publish failure was correct
but undocumented: if publish_to_dlq raises, the exception propagates so
the caller does not ACK the delivery. Add a docstring clause making
this explicit and a regression test that locks the contract in.

This addresses the data-integrity review item that flagged ackable.append
as potentially ACKing events on DLQ failure; verification confirmed the
contract is structurally correct.
EOF
)"
```

---

## Task 8: Final verification across all four sub-themes

**Files:** none (verification only)

- [ ] **Step 1: Full backend test suite + coverage**

```bash
cd backend && pytest --cov 2>&1 | tail -20
```

Expected: all tests pass; coverage ≥ 85% on `monitoring/`, `analytics/gnn/`, `graph/adapters/`, `agent/`.

- [ ] **Step 2: pyright clean**

```bash
cd backend && pyright . 2>&1 | tail -5
```

Expected: 0 errors.

- [ ] **Step 3: ruff clean on touched files**

```bash
cd backend && ruff check monitoring/service.py analytics/gnn/models.py analytics/gnn/service.py graph/adapters/neo4j_adapter.py agent/coordinator.py
```

Expected: no findings.

- [ ] **Step 4: Confirm the dedup index has no permanent insertion site**

```bash
grep -n "_dedup_index" backend/monitoring/service.py
```

Expected: 5 matches now — initialization, eviction read/write (Task 2), the existing read (line 148), and the existing write (line 152). The eviction site is the new one.

- [ ] **Step 5: Confirm `ScoredNode.score` has `le=1.0`**

```bash
grep -n "score:.*Field" backend/analytics/gnn/models.py
```

Expected: line 51 reads `score: float = Field(ge=0.0, le=1.0)`.

- [ ] **Step 6: Confirm the fulltext index is in the schema**

```bash
grep -i "fulltext" backend/graph/adapters/neo4j_adapter.py
```

Expected: at least two matches — the CREATE FULLTEXT in `_ensure_schema`, and the queryNodes call in `search_entities`.

---

## Acceptance Criteria — Sign-off Checklist

- [ ] `MonitoringService._dedup_index` size stays bounded after long-running evaluations; new test in `tests/monitoring/test_service.py` proves it.
- [ ] `ScoredNode.score` has `Field(ge=0.0, le=1.0)`; new test in `tests/analytics/gnn/test_service.py` proves the bound holds for arbitrary graphs.
- [ ] `_ensure_schema` creates `entity_properties_fulltext`; `search_entities` calls `db.index.fulltext.queryNodes`; new integration test asserts the EXPLAIN plan uses the fulltext index.
- [ ] `run_handler_with_retry`'s docstring documents the DLQ-publish ACK contract; new test pins the propagation behavior.
- [ ] `pytest --cov` ≥ 85% on `monitoring/`, `analytics/gnn/`, `graph/adapters/`, `agent/`.
- [ ] `pyright` clean, `ruff check` clean on all touched files.

## Scope Discipline

- **Do NOT** refactor `MonitoringService` to use Postgres-backed dedup. Reading `backend/monitoring/adapters/` confirms there is no Postgres `alert_history` lookup path; bounded in-memory eviction is the right local fix. Postgres-backed dedup would be a separate redesign.
- **Do NOT** apply `tanh`/sigmoid normalization to GNN scores. Max-divide preserves relative ranking and is what downstream consumers expect; sigmoid would compress ranks at the high end.
- **Do NOT** redesign the Neo4j search API. Keep the same signature (`knowledge_base_ids`, `query`, `limit`) and the same return type. Only the Cypher and the index change.
- **Do NOT** add try/except wrapping around `publish_to_dlq` in `run_handler_with_retry`. The current behavior (propagate) is correct; wrapping it would silently drop events.
- **Do NOT** address the `delete_by_source_document` count-then-delete race or the `delete_knowledge_base` race. Those are in Theme 6 (follow-ups).
- **Do NOT** address the four other Neo4j queries in the file that use `toLower` or `CONTAINS`. Those queries already use the `knowledge_base_id`-indexed lookup — the bug is specific to `search_entities` because it has no other index to lean on.
