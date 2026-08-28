from __future__ import annotations

import pathlib
from typing import cast

import pytest
import yaml

from capabilities.models import (
    CapabilityManifest,
    CapabilityPermission,
    CapabilityQuery,
)
from capabilities.registry import create_default_capability_registry
from capabilities.service import (
    CapabilityRegistryService,
    create_default_capability_registry_service,
)


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
    connector_status = service.get_required("connector.sync.status")
    connector_output_properties = cast(
        dict[str, object],
        connector_status.output_schema["properties"],
    )
    assert connector_status.module == "connectors.status_adapter"
    assert connector_output_properties == {
        "connector_id": {"type": "string"},
        "knowledge_base_id": {"type": "string"},
        "connector_name": {"type": "string"},
        "source_type": {"type": "string"},
        "connector_status": {"type": "string"},
        "sync_status": {"type": "string"},
        "run_id": {"type": ["string", "null"]},
        "last_synced_at": {"type": ["string", "null"]},
        "started_at": {"type": ["string", "null"]},
        "updated_at": {"type": ["string", "null"]},
        "counters": {"type": "object"},
        "source_cursor": {"type": ["string", "null"]},
        "ingest_correlation_id": {"type": ["string", "null"]},
        "error_message": {"type": ["string", "null"]},
    }
    assert "credentials_ref" not in connector_output_properties


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



def _manifest_permitting_no_roles() -> CapabilityManifest:
    """A manifest granting no role at all — the empty-required_roles case."""

    return CapabilityManifest(
        capability_id="test.permits.nobody",
        version="v1",
        module="tests",
        label="Permits nobody",
        description="A capability whose permission grants no role.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class="read",
        permission=CapabilityPermission(required_roles=[]),
    )



# ---------------------------------------------------------------------------
# Fail-closed authorization
#
# Every branch below used to return success. None of it was exploitable while
# nothing dispatched capabilities — these must close *before* an executor
# exists, or building the dispatcher makes all four bypasses live at once.
# ---------------------------------------------------------------------------


def test_authorize_denies_when_domain_is_not_supplied() -> None:
    """A caller that forgets the domain must not be treated as unrestricted."""
    service = create_default_capability_registry_service()

    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["analyst"],
        domain_name=None,
        environment_tag="local",
    )

    assert envelope.success is False
    assert envelope.error_code == "domain_not_supplied"


def test_authorize_denies_when_environment_is_not_supplied() -> None:
    """Omitting the environment must not silently pass the environment gate."""
    service = create_default_capability_registry_service()

    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["analyst"],
        domain_name="medicare_fraud",
        environment_tag=None,
    )

    assert envelope.success is False
    assert envelope.error_code == "environment_not_supplied"


def test_authorize_denies_a_capability_that_permits_no_roles() -> None:
    """An empty `required_roles` used to mean "everyone". It now means "nobody".

    A manifest that grants no role is either a mistake or a deliberately
    disabled capability. Reading it as "unrestricted" is the worst of the three
    possible interpretations.
    """
    service = create_default_capability_registry_service()
    manifest = _manifest_permitting_no_roles()
    service.register(manifest)

    envelope = service.authorize(
        manifest.capability_id,
        actor_roles=["admin"],
        domain_name="medicare_fraud",
        environment_tag="local",
    )

    assert envelope.success is False
    assert envelope.error_code == "no_roles_permitted"


def test_browse_hides_a_capability_that_permits_no_roles() -> None:
    """The second copy of the bypass, in `_role_can_access`.

    Closing only the authorize path would leave the browse API advertising a
    capability that can never actually be invoked.
    """
    service = create_default_capability_registry_service()
    manifest = _manifest_permitting_no_roles()
    service.register(manifest)

    listed = service.list_capabilities(CapabilityQuery(role="admin"))

    assert manifest.capability_id not in [item.capability_id for item in listed.items]


def test_authorize_denies_an_unregistered_capability() -> None:
    envelope = create_default_capability_registry_service().authorize(
        "does.not.exist",
        actor_roles=["admin"],
        domain_name="medicare_fraud",
        environment_tag="local",
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_not_registered"


def test_every_shipped_manifest_permits_at_least_one_role() -> None:
    """Inverting the empty case must not silently disable a real capability."""
    service = create_default_capability_registry_service()

    for manifest in service.list_capabilities().items:
        assert manifest.permission.required_roles, (
            f"Capability '{manifest.capability_id}' permits no roles, so it is "
            "now callable by nobody."
        )


def test_authorization_context_has_no_defaults() -> None:
    """Omitting domain or environment must be a type error, not a quiet pass.

    The runtime `None` checks above are the safety net; this is the guard that
    keeps a future edit from reintroducing `= None` defaults and making the
    omission invisible again at every call site.
    """
    import inspect

    signature = inspect.signature(CapabilityRegistryService.authorize)

    for name in ("domain_name", "environment_tag"):
        parameter = signature.parameters[name]
        assert parameter.default is inspect.Parameter.empty, (
            f"`{name}` has a default, so a caller can omit the authorization "
            "context without the type checker noticing."
        )


def test_capability_adapters_require_authorization_context() -> None:
    """Same guard one layer up, where the executor will actually call in.

    An adapter that defaults the context reintroduces the bypass for every
    caller that forgets it, which is exactly how the original branches were
    reachable.
    """
    import inspect

    from connectors.status_adapter import execute_connector_sync_status_capability
    from workflow_definitions.rag_adapter import execute_rag_query_capability

    for function in (execute_rag_query_capability, execute_connector_sync_status_capability):
        signature = inspect.signature(function)
        for name in ("domain_name", "environment_tag"):
            assert signature.parameters[name].default is inspect.Parameter.empty, (
                f"{function.__name__} defaults `{name}`."
            )


def test_manifest_environment_tags_use_the_real_environment_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tag a caller passes is CHILI_ENV, so the two must agree.

    They had drifted: manifests declared support for a "test" environment that
    is not a valid CHILI_ENV at all, and omitted "local" — the default for the
    entire dev stack — and "staging". Once authorize() started failing closed
    on the environment gate, that made every capability call under the dev
    stack deny with `capability_environment_denied`.
    """
    from api.dependencies import load_chili_environment
    from shared.environments import SUPPORTED_ENVIRONMENT_TAGS

    # Through the public resolver rather than its private allow-list: this
    # asserts every declared tag is a value CHILI_ENV will actually accept.
    for tag in SUPPORTED_ENVIRONMENT_TAGS:
        monkeypatch.setenv("CHILI_ENV", tag)
        assert load_chili_environment() == tag

    for manifest in create_default_capability_registry_service().list_capabilities().items:
        tags = set(manifest.domain_compatibility.environment_tags)
        unknown = tags - set(SUPPORTED_ENVIRONMENT_TAGS)
        assert not unknown, (
            f"Capability '{manifest.capability_id}' declares environments that "
            f"CHILI_ENV can never hold: {sorted(unknown)}"
        )


def test_every_shipped_capability_is_usable_in_local_development() -> None:
    """A capability nothing can call on the dev stack is untestable by hand."""
    service = create_default_capability_registry_service()

    for manifest in service.list_capabilities().items:
        envelope = service.authorize(
            manifest.capability_id,
            actor_roles=["admin"],
            domain_name=manifest.domain_compatibility.supported_domains[0],
            environment_tag="local",
        )
        assert envelope.success is True, (
            f"'{manifest.capability_id}' cannot be invoked locally: "
            f"{envelope.error_code}"
        )


def test_every_declared_domain_matches_a_shipped_pack() -> None:
    """Domain gates are matched against ``DomainConfig.name`` by string equality.

    A name that matches no pack is not a no-op — it silently denies the
    capability for every domain, which is indistinguishable from the
    capability not existing. ``af_housing`` did exactly that to the shipped
    Air Force housing pack, whose real name is ``department_air_force_housing``.
    """
    defaults = pathlib.Path(__file__).resolve().parents[2] / "config" / "defaults"
    shipped = {
        yaml.safe_load(path.read_text())["domain"]["name"]
        for path in defaults.glob("*.yaml")
    }

    declared = {
        domain
        for capability in create_default_capability_registry().list()
        for domain in capability.domain_compatibility.supported_domains
    }

    assert declared <= shipped, (
        f"capability manifests name domains that no pack defines: {sorted(declared - shipped)}; "
        f"shipped packs are {sorted(shipped)}"
    )


def test_the_housing_pack_has_usable_capabilities() -> None:
    """The shipped housing pack must not resolve to an empty capability list."""
    supported = [
        capability.capability_id
        for capability in create_default_capability_registry().list()
        if "department_air_force_housing"
        in capability.domain_compatibility.supported_domains
    ]

    assert supported, "the housing pack resolves to zero capabilities"
