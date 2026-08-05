"""Capability registry service used by APIs and workflow validation."""

from __future__ import annotations

from capabilities.models import CapabilityManifest, CapabilityPage, CapabilityQuery
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


def _role_can_access(manifest: CapabilityManifest, role: str) -> bool:
    required_roles = manifest.permission.required_roles
    if not required_roles:
        return True
    role_level = _ROLE_HIERARCHY.get(role)
    if role_level is None:
        return False
    return any(
        (required_level := _ROLE_HIERARCHY.get(required)) is not None
        and role_level >= required_level
        for required in required_roles
    )


__all__ = [
    "CapabilityRegistryService",
    "create_default_capability_registry_service",
]
