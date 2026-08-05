"""Read-only readiness aggregation service for SAFE-CMS-018."""

from __future__ import annotations

from capabilities.models import CapabilityQuery, JsonValue
from capabilities.service import CapabilityRegistryService
from connectors.models import ConnectorDefinition, ConnectorSyncRun
from connectors.service import ConnectorService
from knowledgebases.protocols import KnowledgeBaseRepository
from readiness.models import (
    ReadinessComponent,
    ReadinessIssue,
    ReadinessKnowledgeBaseSummary,
    ReadinessResponse,
)
from shared.types import KnowledgeBase
from workflow_definitions.service import WorkflowDefinitionService

_COMPONENT_LABELS: dict[str, str] = {
    "knowledge_base": "Knowledge base",
    "connectors": "Connectors",
    "workflows": "Workflows",
    "capabilities": "Capabilities",
}


class ReadinessService:
    """Aggregate KB/domain readiness from existing subsystem state."""

    def __init__(
        self,
        *,
        knowledge_base_repository: KnowledgeBaseRepository,
        connector_service: ConnectorService,
        workflow_definition_service: WorkflowDefinitionService,
        capability_registry: CapabilityRegistryService,
        active_domain_name: str,
    ) -> None:
        self._knowledge_base_repository = knowledge_base_repository
        self._connector_service = connector_service
        self._workflow_definition_service = workflow_definition_service
        self._capability_registry = capability_registry
        self._active_domain_name = active_domain_name

    def get_readiness(self, knowledge_base_id: str) -> ReadinessResponse:
        """Return aggregated readiness for one knowledge base."""

        knowledge_base = self._knowledge_base_repository.get(knowledge_base_id)
        if knowledge_base is None:
            raise KeyError(knowledge_base_id)

        components = {
            "knowledge_base": self._knowledge_base_component(knowledge_base),
            "connectors": self._connector_component(knowledge_base.id),
            "workflows": self._workflow_component(knowledge_base.id),
            "capabilities": self._capability_component(),
        }
        blockers = [
            blocker
            for component in components.values()
            for blocker in component.blockers
        ]
        warnings = [
            warning
            for component in components.values()
            for warning in component.warnings
        ]
        return ReadinessResponse(
            knowledge_base=_knowledge_base_summary(knowledge_base),
            active_domain_name=self._active_domain_name,
            ready=not blockers,
            components=components,
            blockers=blockers,
            warnings=warnings,
        )

    def _knowledge_base_component(
        self,
        knowledge_base: KnowledgeBase,
    ) -> ReadinessComponent:
        blockers: list[ReadinessIssue] = []
        warnings: list[ReadinessIssue] = []
        if knowledge_base.status != "ready":
            blockers.append(
                ReadinessIssue(
                    component="knowledge_base",
                    code="kb_not_ready",
                    message=(
                        f"Knowledge base status is '{knowledge_base.status}', "
                        "not 'ready'."
                    ),
                    action="Wait for ingestion and graph processing to finish.",
                )
            )
        if (
            knowledge_base.domain is not None
            and knowledge_base.domain != self._active_domain_name
        ):
            warnings.append(
                ReadinessIssue(
                    component="knowledge_base",
                    code="domain_mismatch",
                    message=(
                        f"Knowledge base was created under '{knowledge_base.domain}' "
                        f"while the active domain is '{self._active_domain_name}'."
                    ),
                    action="Switch domains or select a knowledge base from the active domain.",
                )
            )

        return _component(
            "knowledge_base",
            blockers=blockers,
            warnings=warnings,
            ready_summary="Knowledge base is ready.",
            blocked_summary="Knowledge base is not ready.",
            warning_summary="Knowledge base is ready with domain warnings.",
            details={
                "status": knowledge_base.status,
                "document_count": knowledge_base.document_count,
                "entity_count": knowledge_base.entity_count,
                "relationship_count": knowledge_base.relationship_count,
                "domain": knowledge_base.domain,
            },
        )

    def _connector_component(self, knowledge_base_id: str) -> ReadinessComponent:
        page = self._connector_service.list_connectors(
            knowledge_base_id=knowledge_base_id,
            limit=500,
        )
        blockers: list[ReadinessIssue] = []
        warnings: list[ReadinessIssue] = []
        completed_runs = 0
        failed_connectors: list[str] = []
        never_synced: list[str] = []

        if not page.items:
            blockers.append(
                ReadinessIssue(
                    component="connectors",
                    code="no_connectors",
                    message="No connectors are configured for this knowledge base.",
                    action="Register a connector or upload source data manually.",
                )
            )
        for connector in page.items:
            latest_run = self._latest_connector_run(connector)
            if latest_run is None:
                never_synced.append(connector.connector_id)
                continue
            if latest_run.status == "completed":
                completed_runs += 1
            elif latest_run.status == "failed":
                failed_connectors.append(connector.connector_id)

        if failed_connectors:
            blockers.append(
                ReadinessIssue(
                    component="connectors",
                    code="connector_sync_failed",
                    message=(
                        "Latest connector sync failed for: "
                        f"{', '.join(sorted(failed_connectors))}."
                    ),
                    action="Inspect the connector sync run and replay or quarantine failures.",
                )
            )
        if never_synced:
            warnings.append(
                ReadinessIssue(
                    component="connectors",
                    code="connector_never_synced",
                    message=(
                        "Connector has not synced yet: "
                        f"{', '.join(sorted(never_synced))}."
                    ),
                    action="Start a connector sync run.",
                )
            )

        return _component(
            "connectors",
            blockers=blockers,
            warnings=warnings,
            ready_summary="Connectors have completed sync runs.",
            blocked_summary="Connector state blocks readiness.",
            warning_summary="Connectors are configured with warnings.",
            details={
                "configured_count": page.total_items,
                "completed_runs": completed_runs,
                "failed_connectors": failed_connectors,
                "never_synced": never_synced,
            },
        )

    def _latest_connector_run(
        self,
        connector: ConnectorDefinition,
    ) -> ConnectorSyncRun | None:
        runs = self._connector_service.list_runs(
            connector_id=connector.connector_id,
            knowledge_base_id=connector.knowledge_base_id,
            limit=1,
        )
        return runs.items[0] if runs.items else None

    def _workflow_component(self, knowledge_base_id: str) -> ReadinessComponent:
        page = self._workflow_definition_service.list_definitions(
            knowledge_base_id=knowledge_base_id,
            limit=500,
        )
        blockers: list[ReadinessIssue] = []
        if not page.items:
            blockers.append(
                ReadinessIssue(
                    component="workflows",
                    code="no_workflows",
                    message="No workflow definitions are available for this knowledge base.",
                    action="Create or publish a workflow definition for the selected KB.",
                )
            )

        approved_count = sum(1 for definition in page.items if definition.status == "approved")
        return _component(
            "workflows",
            blockers=blockers,
            warnings=[],
            ready_summary="Workflow definitions are available.",
            blocked_summary="Workflow definitions are missing.",
            warning_summary="Workflow definitions are available with warnings.",
            details={
                "definition_count": page.total_items,
                "approved_count": approved_count,
            },
        )

    def _capability_component(self) -> ReadinessComponent:
        page = self._capability_registry.list_capabilities(
            CapabilityQuery(domain_name=self._active_domain_name)
        )
        blockers: list[ReadinessIssue] = []
        if page.total_items == 0:
            blockers.append(
                ReadinessIssue(
                    component="capabilities",
                    code="no_capabilities",
                    message=(
                        "No capabilities are registered for the active domain "
                        f"'{self._active_domain_name}'."
                    ),
                    action="Enable or register capabilities for the active domain.",
                )
            )

        return _component(
            "capabilities",
            blockers=blockers,
            warnings=[],
            ready_summary="Capabilities are available for this domain.",
            blocked_summary="No capabilities are available for this domain.",
            warning_summary="Capabilities are available with warnings.",
            details={
                "available_count": page.total_items,
                "capability_ids": [capability.capability_id for capability in page.items],
            },
        )


def _component(
    component_id: str,
    *,
    blockers: list[ReadinessIssue],
    warnings: list[ReadinessIssue],
    ready_summary: str,
    blocked_summary: str,
    warning_summary: str,
    details: dict[str, JsonValue],
) -> ReadinessComponent:
    if blockers:
        status = "blocked"
        summary = blocked_summary
    elif warnings:
        status = "warning"
        summary = warning_summary
    else:
        status = "ready"
        summary = ready_summary
    return ReadinessComponent(
        status=status,
        label=_COMPONENT_LABELS[component_id],
        summary=summary,
        blockers=blockers,
        warnings=warnings,
        details=details,
    )


def _knowledge_base_summary(
    knowledge_base: KnowledgeBase,
) -> ReadinessKnowledgeBaseSummary:
    return ReadinessKnowledgeBaseSummary(
        id=knowledge_base.id,
        name=knowledge_base.name,
        domain=knowledge_base.domain,
        status=knowledge_base.status,
        document_count=knowledge_base.document_count,
        entity_count=knowledge_base.entity_count,
        relationship_count=knowledge_base.relationship_count,
        updated_at=knowledge_base.updated_at,
        created_at=knowledge_base.created_at,
    )


__all__ = ["ReadinessService"]
