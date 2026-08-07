"""Coherence guards for the identifier-drift defect class.

Four instances of one mistake have shipped: an adapter whose capability id no
manifest declares, a manifest naming a module that does not exist, an event
type with no producer, and a built-in capability list naming a capability with
no manifest. Each half was individually correct and individually tested, which
is why unit tests never caught any of them.

These guards fail when the two halves disagree. The corrected value fixes
today; the recurrence is the actual problem — see
`docs/superpowers/specs/2026-08-07-execution-gap-closure-design.md` §3 D3.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import get_args

import pytest

from capabilities.service import create_default_capability_registry_service
from events.codec import EVENT_TYPE_REGISTRY

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Modules exporting a workflow-callable capability id, and the symbol holding
# it. Listed explicitly rather than discovered by scanning: a scan silently
# passes when a new adapter is added, which is the exact failure being guarded.
_ADAPTER_CAPABILITY_IDS: tuple[tuple[str, str], ...] = (
    ("connectors.status_adapter", "CONNECTOR_SYNC_STATUS_CAPABILITY_ID"),
    ("workflow_definitions.rag_adapter", "RAG_QUERY_CAPABILITY_ID"),
    ("analytics.peerstats.capability", "PeerAnalysisCapabilityId"),
)

# Event types with no worker consumer *by design*. Every entry carries who
# consumes it — an unjustified entry is how a dead event hides in an allow-list.
NOTIFICATION_ONLY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Consumed by the API's own poll loop, never through the pipeline drain.
        "config.updated",
        # Read models and SSE: published for operators and the frontend, not to
        # drive further work.
        "agent.workflow.started",
        "score_run.status_changed",
        "rag.completed",
        "llm.completed",
        "explainability.generated",
        "gnn.analyzed",
        "timeseries.analyzed",
        "identity.link_decision.recorded",
        "analysis.failed",
        "vectors.deleted",
        "embeddings.generated",
        "kb.create",
    }
)

# Declared, decodable, and constructed **nowhere** — not "published but not
# consumed", which is what the list above is for. These are types whose
# producer does not exist, so any surface documented as fed by them emits
# nothing. Closed by Plan 3 Task 4, which decides per type whether to build the
# producer or retire the surface.
KNOWN_PRODUCERLESS_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # The real-time WebSocket alert stream (G8).
        "alert.created",
        # The pipeline-progress WebSocket route, same shape as the above.
        "pipeline.progress",
        # Domain-shaped aliases that were never wired to anything.
        "claims.received",
        "claims.ingested",
    }
)


def _capability_ids() -> set[str]:
    return {
        manifest.capability_id
        for manifest in create_default_capability_registry_service()
        .list_capabilities()
        .items
    }


def _event_types_constructed_in_production_code() -> set[str]:
    """Event classes constructed anywhere outside tests, mapped to their type.

    Parses rather than greps so a class named in an import or a docstring does
    not count as a producer — the whole point is to find types that are
    *declared* everywhere and *built* nowhere.
    """

    class_to_event_type = {
        model.__name__: event_type for event_type, model in EVENT_TYPE_REGISTRY.items()
    }
    produced: set[str] = set()
    for path in _BACKEND_DIR.rglob("*.py"):
        relative = path.relative_to(_BACKEND_DIR)
        if relative.parts[0] in {"tests", ".venv"}:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                event_type = class_to_event_type.get(node.func.id)
                if event_type is not None:
                    produced.add(event_type)
    return produced


@pytest.mark.xfail(reason="G7 — closed by Task 2", strict=True)
def test_every_manifest_names_an_importable_module() -> None:
    """`module` is a browse-API filter, not documentation.

    `evidence.checklist.generate` declares `module="evidence.packs"`, which does
    not exist — the real module is `analytics.explainability`. A filter naming a
    phantom module returns a capability nobody can locate, and the value is
    surfaced to clients.
    """
    unimportable: list[str] = []
    for manifest in create_default_capability_registry_service().list_capabilities().items:
        try:
            importlib.import_module(manifest.module)
        except ImportError:
            unimportable.append(f"{manifest.capability_id} -> {manifest.module}")

    assert not unimportable, (
        f"capabilities naming modules that do not import: {unimportable}"
    )


@pytest.mark.xfail(reason="G10 — closed by Task 3", strict=True)
def test_every_capability_adapter_id_is_a_registered_manifest_id() -> None:
    """Two halves of one feature must not live under different names.

    `analytics/peerstats/capability.py` implements a complete adapter under
    `analytics.peer_analysis`, which no manifest declares, while the manifest
    declares `analytics.peer_context`, which nothing implements. Both halves are
    correct; neither is reachable.
    """
    registered = _capability_ids()
    orphans: list[str] = []
    for module_name, symbol in _ADAPTER_CAPABILITY_IDS:
        declared = getattr(importlib.import_module(module_name), symbol)
        # A Literal alias and a plain str constant both resolve here.
        for value in get_args(declared) or (declared,):
            if value not in registered:
                orphans.append(f"{module_name}.{symbol} = {value!r}")

    assert not orphans, (
        f"adapter capability ids no manifest declares, so the adapters are "
        f"unreachable through the registry: {orphans}"
    )


@pytest.mark.xfail(reason="G8 — closed by Plan 3 Task 4", strict=True)
def test_every_declared_event_type_has_a_producer_or_is_notification_only() -> None:
    """A decodable event nothing constructs is a feature that never fires.

    `alert.created` is documented as feeding the real-time WebSocket alert
    stream and is constructed nowhere outside a test, so that stream has no
    producer.
    """
    produced = _event_types_constructed_in_production_code()
    dead = sorted(
        event_type
        for event_type in EVENT_TYPE_REGISTRY
        if event_type not in produced and event_type not in NOTIFICATION_ONLY_EVENT_TYPES
    )

    assert not dead, (
        f"event types declared in the codec and constructed nowhere in "
        f"production code: {dead}"
    )


def test_the_notification_allow_list_only_names_real_event_types() -> None:
    """An allow-list entry for a type that no longer exists hides nothing.

    It does, however, make the list look maintained while quietly rotting — and
    a stale entry is how a genuinely dead event slips back in under an old name.
    """
    unknown = sorted(
        (NOTIFICATION_ONLY_EVENT_TYPES | KNOWN_PRODUCERLESS_EVENT_TYPES)
        - set(EVENT_TYPE_REGISTRY)
    )

    assert not unknown, f"allow-list names event types that do not exist: {unknown}"


def test_the_adapter_list_covers_every_module_exporting_a_capability_id() -> None:
    """The explicit list must not fall behind the code it guards.

    `_ADAPTER_CAPABILITY_IDS` is written out by hand so a new adapter cannot
    join silently — which only works if this notices when one does.
    """
    listed = {module for module, _ in _ADAPTER_CAPABILITY_IDS}
    found: set[str] = set()
    for path in _BACKEND_DIR.rglob("*.py"):
        relative = path.relative_to(_BACKEND_DIR)
        if relative.parts[0] in {"tests", ".venv"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "CAPABILITY_ID" in text or "CapabilityId" in text:
            module = ".".join(relative.with_suffix("").parts)
            # The registry and the executor map mention the words without
            # exporting an adapter id of their own.
            if module.startswith(("capabilities.", "events.")):
                continue
            found.add(module)

    assert found <= listed, (
        f"modules exporting a capability id that _ADAPTER_CAPABILITY_IDS does "
        f"not list, so their ids are unguarded: {sorted(found - listed)}"
    )


def test_the_notification_allow_list_contains_no_producerless_type() -> None:
    """The two lists mean different things and must not blur together.

    `NOTIFICATION_ONLY_EVENT_TYPES` is "published, deliberately not consumed by
    the worker". A type with no producer at all is not a notification — it is a
    surface that emits nothing — and letting one sit in this list makes the
    producer guard pass while the gap remains. That is exactly how the first
    version of this file hid `alert.created` from its own check.
    """
    produced = _event_types_constructed_in_production_code()
    smuggled = sorted(t for t in NOTIFICATION_ONLY_EVENT_TYPES if t not in produced)

    assert not smuggled, (
        f"types in the notification allow-list that nothing constructs; they "
        f"belong in KNOWN_PRODUCERLESS_EVENT_TYPES: {smuggled}"
    )
