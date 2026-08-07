"""Capability registry service used by APIs and workflow validation."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from auditlog.models import PLATFORM_TENANT_ID, AuditEventCreate
from auditlog.service import AuditLogService
from capabilities.executors import get_executor
from capabilities.models import (
    CapabilityExecutionEnvelope,
    CapabilityManifest,
    CapabilityPage,
    CapabilityQuery,
    JsonValue,
)
from capabilities.registry import CapabilityRegistry, create_default_capability_registry
from shared.utils import generate_id

logger = logging.getLogger(__name__)

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
        domain_name: str | None,
        environment_tag: str | None,
    ) -> CapabilityExecutionEnvelope:
        """Authorize one capability call, failing closed on missing context.

        ``domain_name`` and ``environment_tag`` are required keyword arguments
        with no defaults. They still accept ``None`` — a caller may genuinely
        not know them — but ``None`` denies rather than skips the gate, and the
        absent default means omitting them is a type error rather than a silent
        bypass.
        """

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
        # Fail closed on omitted context. `domain_name is not None and ...` read
        # an absent domain as "unrestricted", so a caller that simply forgot to
        # pass one skipped the domain gate entirely.
        if domain_name is None:
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="domain_not_supplied",
                error_message="Capability authorization requires a domain.",
                audit_required=audit_required,
            )
        if not _supports_domain(manifest, domain_name):
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
        if environment_tag is None:
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="environment_not_supplied",
                error_message="Capability authorization requires an environment.",
                audit_required=audit_required,
            )
        if not _supports_environment(manifest, environment_tag):
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
        if not manifest.permission.required_roles:
            # Distinct from `capability_role_denied`: the caller's roles are
            # irrelevant because the manifest grants none. That is a broken or
            # deliberately disabled capability, and an operator needs to be able
            # to tell those two situations apart.
            return CapabilityExecutionEnvelope(
                capability_id=capability_id,
                success=False,
                error_code="no_roles_permitted",
                error_message=(
                    f"Capability '{capability_id}' permits no roles, so it "
                    "cannot be invoked by anyone."
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

    def execute(
        self,
        capability_id: str,
        *,
        payload: Mapping[str, object],
        actor_user_id: str,
        actor_roles: Sequence[str],
        domain_name: str | None,
        environment_tag: str | None,
        knowledge_base_id: str | None,
        audit_service: AuditLogService,
    ) -> CapabilityExecutionEnvelope:
        """Authorize, then dispatch, then audit.

        The order is the security property. Dispatching first would mean the
        side effect had already happened by the time the envelope reported the
        call denied.

        ``actor_user_id`` is separate from ``actor_roles`` on purpose: the
        first is identity and the second is authorization context. Deriving one
        from the other would put a fabricated actor into an append-only ledger
        while the field meant for the real one sat unused.
        """

        envelope = self.authorize(
            capability_id,
            actor_roles=actor_roles,
            domain_name=domain_name,
            environment_tag=environment_tag,
        )
        if not envelope.success:
            # A refused attempt on an audited capability is exactly what the
            # ledger exists to record, so this is audited before returning.
            self._audit_execution(
                audit_service,
                envelope=envelope,
                capability_id=capability_id,
                actor_user_id=actor_user_id,
                actor_roles=actor_roles,
                knowledge_base_id=knowledge_base_id,
            )
            return envelope

        executor = get_executor(capability_id)
        if executor is None:
            outcome = self.execution_failure(
                capability_id,
                error_code="capability_not_executable",
                error_message=(
                    f"Capability '{capability_id}' is registered but has no "
                    "executor bound, so it cannot be invoked."
                ),
            )
        else:
            try:
                result = executor(payload)
            except Exception as exc:  # noqa: BLE001 - any tool failure is a failed call
                # A tool blowing up is a failed capability call, not a failed
                # workflow step. Letting it propagate would dead-letter the
                # event and lose the audit record; the caller decides what a
                # failed call means for the step.
                logger.exception(
                    "Capability execution failed capability=%s", capability_id
                )
                outcome = self.execution_failure(
                    capability_id,
                    error_code="capability_execution_failed",
                    error_message=str(exc),
                )
            else:
                outcome = self.execution_success(
                    capability_id, output=_as_output(result)
                )

        self._audit_execution(
            audit_service,
            envelope=outcome,
            capability_id=capability_id,
            actor_user_id=actor_user_id,
            actor_roles=actor_roles,
            knowledge_base_id=knowledge_base_id,
        )
        return outcome

    def _audit_execution(
        self,
        audit_service: AuditLogService,
        *,
        envelope: CapabilityExecutionEnvelope,
        capability_id: str,
        actor_user_id: str,
        actor_roles: Sequence[str],
        knowledge_base_id: str | None,
    ) -> None:
        """Record a material capability call when its manifest demands it.

        ``AuditLogService`` captures its own write failures rather than
        raising, so a broken ledger degrades to a recorded failure instead of
        discarding the work that was already done.
        """

        if not envelope.audit_required:
            return
        audit_service.record(
            AuditEventCreate(
                tenant_id=PLATFORM_TENANT_ID,
                knowledge_base_id=knowledge_base_id,
                actor_user_id=actor_user_id,
                actor_roles=list(actor_roles),
                action="capability.execute",
                resource_type="capability",
                resource_id=capability_id,
                outcome="success" if envelope.success else "failure",
                failure_reason=envelope.error_message,
                correlation_id=generate_id(),
            )
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
        # A capability granting no role is callable by nobody. Reading an empty
        # list as "everyone" is the most permissive of the three possible
        # interpretations, and it applies precisely to a manifest whose
        # permissions were never filled in.
        return False
    return any(
        _role_meets_requirement(role, required)
        for role in roles
        for required in required_roles
    )


def _role_can_access(manifest: CapabilityManifest, role: str) -> bool:
    """Browse-path counterpart of `_roles_can_access`.

    The same bypass existed in both. Closing only the authorize path would have
    left the browse API advertising a capability that can never be invoked.
    """

    required_roles = manifest.permission.required_roles
    if not required_roles:
        return False
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


def _as_output(result: Mapping[str, object]) -> dict[str, JsonValue]:
    """Normalise an executor's return value into an envelope output.

    `JsonValue` is `object`, so this is a copy rather than a conversion — its
    job is to stop a mutable mapping owned by the executor leaking into the
    envelope, where a later mutation would silently change a returned result.
    """

    return dict(result)
