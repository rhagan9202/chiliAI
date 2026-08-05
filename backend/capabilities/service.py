"""Capability registry service used by APIs and workflow validation."""

from __future__ import annotations

from collections.abc import Sequence

from capabilities.models import (
    CapabilityExecutionEnvelope,
    CapabilityManifest,
    CapabilityPage,
    CapabilityQuery,
    JsonValue,
)
from capabilities.registry import CapabilityRegistry, create_default_capability_registry

_ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "analyst": 2,
    "service": 2,
    "admin": 3,
}


class CapabilityRegistryService:
    """Browse and resolve registered capabilities."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def register(self, manifest: CapabilityManifest) -> None:
        self._registry.register(manifest)

    def get(self, capability_id: str) -> CapabilityManifest | None:
        return self._registry.get(capability_id)

    def get_required(self, capability_id: str) -> CapabilityManifest:
        manifest = self.get(capability_id)
        if manifest is None:
            raise KeyError(capability_id)
        return manifest

    def has_capability(self, capability_id: str) -> bool:
        return self.get(capability_id) is not None

    def list_capabilities(self, query: CapabilityQuery | None = None) -> CapabilityPage:
        query = query or CapabilityQuery()
        filtered = [
            manifest
            for manifest in self._registry.list()
            if _matches_query(manifest, query)
        ]
        items = filtered[query.offset : query.offset + query.limit]
        return CapabilityPage(
            items=items,
            total_items=len(filtered),
            limit=query.limit,
            offset=query.offset,
        )

    def authorize(
        self,
        capability_id: str,
        *,
        actor_roles: Sequence[str],
        domain_name: str | None = None,
        environment_tag: str | None = None,
    ) -> CapabilityExecutionEnvelope:
        manifest = self.get(capability_id)
        if manifest is None:
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="capability_not_registered",
                error_message=f"Capability '{capability_id}' is not registered.",
                audit_required=False,
            )
        audit_required = manifest.permission.requires_audit
        if domain_name is not None and not _supports_domain(manifest, domain_name):
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="capability_domain_denied",
                error_message=(
                    f"Capability '{capability_id}' is not available for domain "
                    f"'{domain_name}'."
                ),
                audit_required=audit_required,
            )
        if environment_tag is not None and not _supports_environment(
            manifest,
            environment_tag,
        ):
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="capability_environment_denied",
                error_message=(
                    f"Capability '{capability_id}' is not available for environment "
                    f"'{environment_tag}'."
                ),
                audit_required=audit_required,
            )
        if not _roles_can_access(manifest, actor_roles):
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="capability_role_denied",
                error_message=(
                    f"Actor roles {list(actor_roles)} do not satisfy capability "
                    f"'{capability_id}' requirements."
                ),
                audit_required=audit_required,
            )
        return CapabilityExecutionEnvelope(
            capability_id=capability_id,
            success=True,
            output={
                "authorized": True,
                "side_effect_class": manifest.side_effect_class,
            },
            audit_required=audit_required,
        )

    def execution_success(
        self,
        capability_id: str,
        *,
        output: dict[str, JsonValue],
    ) -> CapabilityExecutionEnvelope:
        manifest = self.get_required(capability_id)
        return CapabilityExecutionEnvelope(
            capability_id=capability_id,
            success=True,
            output=output,
            audit_required=manifest.permission.requires_audit,
        )

    def execution_failure(
        self,
        capability_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> CapabilityExecutionEnvelope:
        manifest = self.get(capability_id)
        return CapabilityExecutionEnvelope(
            capability_id=capability_id,
            success=False,
            error_code=error_code,
            error_message=error_message,
            audit_required=(
                False if manifest is None else manifest.permission.requires_audit
            ),
        )


def create_default_capability_registry_service() -> CapabilityRegistryService:
    return CapabilityRegistryService(create_default_capability_registry())


def _matches_query(manifest: CapabilityManifest, query: CapabilityQuery) -> bool:
    if query.module is not None and manifest.module != query.module:
        return False
    if (
        query.side_effect_class is not None
        and manifest.side_effect_class != query.side_effect_class
    ):
        return False
    if query.domain_name is not None and not _supports_domain(manifest, query.domain_name):
        return False
    if query.role is not None and not _role_can_access(manifest, query.role):
        return False
    return True


def _supports_domain(manifest: CapabilityManifest, domain_name: str) -> bool:
    compatibility = manifest.domain_compatibility
    if domain_name in compatibility.unsupported_domains:
        return False
    return not compatibility.supported_domains or domain_name in compatibility.supported_domains


def _supports_environment(manifest: CapabilityManifest, environment_tag: str) -> bool:
    tags = manifest.domain_compatibility.environment_tags
    return not tags or environment_tag in tags


def _roles_can_access(manifest: CapabilityManifest, roles: Sequence[str]) -> bool:
    required_roles = manifest.permission.required_roles
    if not required_roles:
        return True
    return any(
        _role_meets_requirement(role, required)
        for role in roles
        for required in required_roles
    )


def _role_can_access(manifest: CapabilityManifest, role: str) -> bool:
    required_roles = manifest.permission.required_roles
    if not required_roles:
        return True
    return any(_role_meets_requirement(role, required) for required in required_roles)


def _role_meets_requirement(role: str, required: str) -> bool:
    role_level = _ROLE_HIERARCHY.get(role)
    if role_level is None:
        return False
    required_level = _ROLE_HIERARCHY.get(required)
    return required_level is not None and role_level >= required_level


__all__ = [
    "CapabilityRegistryService",
    "create_default_capability_registry_service",
]
