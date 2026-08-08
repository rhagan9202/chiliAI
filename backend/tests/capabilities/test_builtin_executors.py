"""Tests for binding real services to capability ids.

`capabilities/executors.py` is the map; `builtin_executors.py` is what puts
anything in it. A manifest with no bound executor authorizes and then reports
`capability_not_executable` — truthful, but a capability nobody can run.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any
from unittest.mock import MagicMock

import pytest

from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from capabilities.builtin_executors import register_builtin_capability_executors
from capabilities.executors import clear_executors, registered_capability_ids
from capabilities.service import (
    CapabilityRegistryService,
    create_default_capability_registry_service,
)
from config.schema import CapabilitiesConfig
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.service import ConnectorService

_KB_ID = "kb-1"
_ACTOR = "operator-1"


@pytest.fixture(autouse=True)
def clear_executor_registry() -> Iterator[None]:
    clear_executors()
    yield
    clear_executors()


def _audit() -> AuditLogService:
    return AuditLogService(InMemoryAuditLogRepository())


def _connector_service() -> ConnectorService:
    return ConnectorService(InMemoryConnectorRepository())


def _bind(**overrides: Any) -> tuple[frozenset[str], CapabilityRegistryService]:
    registry = create_default_capability_registry_service()
    kwargs: dict[str, Any] = {
        "connector_service": _connector_service(),
        "rag_service": MagicMock(),
        "peer_analysis_service": MagicMock(),
        "capability_registry": registry,
        # peer_stats defaults False; analytics.peer_context is gated on it.
        "capabilities_config": CapabilitiesConfig(peer_stats=True),
        "domain_name": "medicare_fraud",
        "environment_tag": "local",
    }
    kwargs.update(overrides)
    return register_builtin_capability_executors(**kwargs), registry


def _execute(
    registry: CapabilityRegistryService,
    capability_id: str,
    payload: Mapping[str, object],
    *,
    roles: list[str] | None = None,
):
    return registry.execute(
        capability_id,
        payload=payload,
        actor_user_id=_ACTOR,
        actor_roles=roles or ["admin"],
        domain_name="medicare_fraud",
        environment_tag="local",
        knowledge_base_id=_KB_ID,
        audit_service=_audit(),
    )


def test_binds_every_capability_whose_service_is_available() -> None:
    bound, _ = _bind()

    assert "connector.sync.status" in bound
    assert "rag.query" in bound
    assert "analytics.peer_context" in bound


def test_evidence_checklist_stays_deliberately_unbound() -> None:
    """Writing a capability body is different work from running one (spec §6).

    It must report `capability_not_executable` rather than appear bound and
    fail at dispatch.
    """
    bound, registry = _bind()

    assert "evidence.checklist.generate" not in bound
    envelope = _execute(registry, "evidence.checklist.generate", {})
    assert envelope.success is False
    assert envelope.error_code == "capability_not_executable"


def test_an_absent_service_leaves_its_capability_unbound_and_says_so() -> None:
    """A missing service must produce a reportable absence.

    Binding it anyway would produce a capability that looks available and
    fails only when a workflow step dispatches it.
    """
    bound, _ = _bind(rag_service=None)

    assert "rag.query" not in bound
    assert "connector.sync.status" in bound


def test_every_bound_id_is_a_registered_manifest() -> None:
    """A typo binds an executor nothing will ever look up."""
    bound, registry = _bind()
    registered = {
        manifest.capability_id for manifest in registry.list_capabilities().items
    }

    assert bound <= registered
    assert bound <= registered_capability_ids()


def test_peer_context_output_matches_the_manifest_not_the_service() -> None:
    """The manifest is the published contract, so the binding flattens to it.

    `PeerAnalysisResponse` returns `{knowledge_base_id, entity_id, metrics: [...]}`;
    the manifest promises a flat `{entity_id, metric_name, peer_count, z_score}`.
    `peer_count` maps to `cohort_size` — the same quantity under another name —
    so the manifest promises nothing the service cannot supply.
    """
    from datetime import datetime, timezone

    from analytics.peerstats.peer_analysis import (
        PeerAnalysisResponse,
        PeerMetricComparison,
    )

    peer_service = MagicMock()
    peer_service.compare_entity.return_value = PeerAnalysisResponse(
        knowledge_base_id=_KB_ID,
        entity_id="npi-1",
        metrics=[
            PeerMetricComparison(
                metric_name="billing_amount",
                entity_type="provider",
                interval_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
                peer_group_key="provider:TN",
                entity_value=100.0,
                peer_mean=40.0,
                peer_std=10.0,
                z_score=6.0,
                signal_value=0.9,
                cohort_size=25,
                percentile=99.0,
                rationale="well above peers",
            )
        ],
    )
    _, registry = _bind(peer_analysis_service=peer_service)

    envelope = _execute(
        registry,
        "analytics.peer_context",
        {"entity_id": "npi-1", "metric_name": "billing_amount"},
    )

    assert envelope.success is True, envelope.error_message
    assert envelope.output == {
        "entity_id": "npi-1",
        "metric_name": "billing_amount",
        "peer_count": 25,
        "z_score": 6.0,
    }


def test_peer_context_reports_a_metric_the_entity_has_no_comparison_for() -> None:
    """Absent is not zero. Returning z_score=0 would read as "perfectly average"."""
    from analytics.peerstats.peer_analysis import PeerAnalysisResponse

    peer_service = MagicMock()
    peer_service.compare_entity.return_value = PeerAnalysisResponse(
        knowledge_base_id=_KB_ID, entity_id="npi-1", metrics=[]
    )
    _, registry = _bind(peer_analysis_service=peer_service)

    envelope = _execute(
        registry,
        "analytics.peer_context",
        {"entity_id": "npi-1", "metric_name": "billing_amount"},
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_execution_failed"


def test_rag_query_returns_an_answer() -> None:
    from rag.service_models import RagAnswer

    rag_service = MagicMock()
    rag_service.answer_question.return_value = RagAnswer(
        content="Because the provider bills above peers.", sources=[]
    )
    _, registry = _bind(rag_service=rag_service)

    envelope = _execute(
        registry, "rag.query", {"question": "why is this provider flagged?"}
    )

    assert envelope.success is True, envelope.error_message
    assert envelope.output


def test_rag_query_requires_a_question() -> None:
    _, registry = _bind()

    envelope = _execute(registry, "rag.query", {})

    assert envelope.success is False
    assert envelope.error_code == "capability_execution_failed"


def test_peer_context_refuses_when_the_domain_disables_peer_stats() -> None:
    """The domain capability gate is not decoration.

    A pack without peer stats has no peer signals to read, so the capability
    must refuse rather than return an empty or invented comparison.
    """
    _, registry = _bind(capabilities_config=CapabilitiesConfig(peer_stats=False))

    envelope = _execute(
        registry,
        "analytics.peer_context",
        {"entity_id": "npi-1", "metric_name": "billing_amount"},
    )

    assert envelope.success is False
    assert envelope.error_message is not None
    assert "peer_stats" in envelope.error_message


def test_the_declared_worker_set_matches_what_binding_produces() -> None:
    """Two representations of one fact must not drift.

    `WORKER_EXECUTABLE_CAPABILITY_IDS` is what the browse API reports, because
    the executor map is per-process state and the API registers nothing. This
    fails if the declaration and the actual binding disagree — which is how the
    API came to report every capability as unrunnable while the worker was
    running two.
    """
    from capabilities.builtin_executors import WORKER_EXECUTABLE_CAPABILITY_IDS

    # Exactly the services the worker supplies: rag is None there by the
    # api/_rag_bridges module-boundary constraint.
    bound, _ = _bind(rag_service=None)

    assert bound == WORKER_EXECUTABLE_CAPABILITY_IDS
