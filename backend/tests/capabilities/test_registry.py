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
