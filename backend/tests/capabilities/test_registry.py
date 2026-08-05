from __future__ import annotations

import pytest

from capabilities.models import CapabilityQuery
from capabilities.service import create_default_capability_registry_service


def test_default_registry_exposes_safe_cms_015_derisking_capabilities() -> None:
    service = create_default_capability_registry_service()

    page = service.list_capabilities(CapabilityQuery(domain_name="medicare_fraud"))

    assert page.total_items == 5
    assert [item.capability_id for item in page.items] == [
        "analytics.peer_context",
        "connector.sync.status",
        "evidence.checklist.generate",
        "rag.query",
        "case.note.draft",
    ]
    peer_context = service.get_required("analytics.peer_context")
    assert peer_context.input_schema["type"] == "object"
    assert peer_context.output_schema["type"] == "object"
    assert peer_context.permission.required_roles == ["viewer"]
    assert peer_context.domain_compatibility.supported_domains == ["medicare_fraud"]


def test_registry_filters_by_role_domain_and_side_effect_class() -> None:
    service = create_default_capability_registry_service()

    page = service.list_capabilities(
        CapabilityQuery(
            domain_name="medicare_fraud",
            role="viewer",
            side_effect_class="read",
        )
    )

    assert {item.capability_id for item in page.items} == {
        "analytics.peer_context",
        "connector.sync.status",
        "rag.query",
    }


def test_registry_rejects_duplicate_capability_ids() -> None:
    service = create_default_capability_registry_service()
    manifest = service.get_required("rag.query")

    with pytest.raises(ValueError, match="Duplicate capability id"):
        service.register(manifest)


def test_authorize_denies_role_without_required_permission() -> None:
    service = create_default_capability_registry_service()

    envelope = service.authorize(
        "case.note.draft",
        actor_roles=["viewer"],
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is False
    assert envelope.capability_id == "case.note.draft"
    assert envelope.error_code == "capability_role_denied"
    assert envelope.audit_required is True


def test_authorize_allows_role_and_marks_side_effecting_audit_required() -> None:
    service = create_default_capability_registry_service()

    envelope = service.authorize(
        "evidence.checklist.generate",
        actor_roles=["analyst"],
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is True
    assert envelope.output == {
        "authorized": True,
        "side_effect_class": "write",
    }
    assert envelope.audit_required is True
    assert envelope.error_code is None


def test_authorize_denies_unsupported_domain() -> None:
    service = create_default_capability_registry_service()

    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["viewer"],
        domain_name="food_supply_chain",
        environment_tag="production",
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_domain_denied"
    assert envelope.error_message == (
        "Capability 'analytics.peer_context' is not available for domain "
        "'food_supply_chain'."
    )


def test_execution_envelope_helpers_attach_manifest_audit_requirement() -> None:
    service = create_default_capability_registry_service()

    success = service.execution_success(
        "case.note.draft",
        output={"draft_note": "Review provider billing.", "requires_human_approval": True},
    )
    failure = service.execution_failure(
        "rag.query",
        error_code="rag_timeout",
        error_message="RAG query timed out.",
    )

    assert success.success is True
    assert success.audit_required is True
    assert success.output == {
        "draft_note": "Review provider billing.",
        "requires_human_approval": True,
    }
    assert failure.success is False
    assert failure.audit_required is True
    assert failure.output is None
