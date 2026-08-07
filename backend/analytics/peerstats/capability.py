"""Workflow-facing peer-analysis capability adapter for SAFE-CMS-011."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from analytics.peerstats.peer_analysis import PeerAnalysisResponse, PeerAnalysisService
from config.schema import CapabilitiesConfig

# The id the *manifest* publishes. `capabilities/registry.py` declares
# `analytics.peer_context`, and workflow definitions reference that id, so
# it is the contract; this adapter previously used `analytics.peer_analysis`,
# which no manifest declared — leaving a complete implementation unreachable
# through the registry and a registered manifest with nothing behind it.
PeerAnalysisCapabilityId = Literal["analytics.peer_context"]


class PeerAnalysisCapabilityError(RuntimeError):
    """Base exception for peer-analysis capability failures."""


class PeerAnalysisCapabilityDisabledError(PeerAnalysisCapabilityError):
    """Raised when peer-analysis is invoked for a domain without peer stats."""


class PeerAnalysisCapabilityInput(BaseModel):
    """Input payload accepted by the peer-analysis capability."""

    knowledge_base_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    metric_name: str | None = None


class PeerAnalysisCapabilityDescriptor(BaseModel):
    """Static metadata a workflow/capability registry can expose."""

    capability_id: PeerAnalysisCapabilityId = "analytics.peer_context"
    label: str = "Peer analysis"
    required_capability: Literal["peer_stats"] = "peer_stats"
    input_model: str = "PeerAnalysisCapabilityInput"
    output_model: str = "PeerAnalysisResponse"


class PeerAnalysisCapability:
    """Callable adapter around ``PeerAnalysisService``."""

    descriptor = PeerAnalysisCapabilityDescriptor()

    def __init__(self, service: PeerAnalysisService) -> None:
        self._service = service

    def execute(
        self,
        payload: PeerAnalysisCapabilityInput | Mapping[str, Any],
        *,
        capabilities: CapabilitiesConfig,
    ) -> PeerAnalysisResponse:
        """Execute peer analysis through a capability-guarded boundary."""

        if not capabilities.peer_stats:
            raise PeerAnalysisCapabilityDisabledError(
                "Capability 'analytics.peer_context' requires domain capability "
                "'peer_stats'."
            )
        request = (
            payload
            if isinstance(payload, PeerAnalysisCapabilityInput)
            else PeerAnalysisCapabilityInput.model_validate(dict(payload))
        )
        return self._service.compare_entity(
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            metric_name=request.metric_name,
        )


class PeerAnalysisCapabilityRegistry:
    """Registry exposing peer-analysis as a workflow-callable capability."""

    def __init__(self, capability: PeerAnalysisCapability) -> None:
        self._capability = capability

    def get(self, capability_id: str) -> PeerAnalysisCapabilityDescriptor:
        if capability_id != self._capability.descriptor.capability_id:
            raise KeyError(capability_id)
        return self._capability.descriptor

    def execute(
        self,
        capability_id: str,
        payload: PeerAnalysisCapabilityInput | Mapping[str, Any],
        *,
        capabilities: CapabilitiesConfig,
    ) -> PeerAnalysisResponse:
        self.get(capability_id)
        return self._capability.execute(payload, capabilities=capabilities)


def create_peer_analysis_capability_registry(
    service: PeerAnalysisService,
) -> PeerAnalysisCapabilityRegistry:
    """Create the peer-analysis capability registry for workflow callers."""

    return PeerAnalysisCapabilityRegistry(PeerAnalysisCapability(service))


__all__ = [
    "PeerAnalysisCapability",
    "PeerAnalysisCapabilityDescriptor",
    "PeerAnalysisCapabilityDisabledError",
    "PeerAnalysisCapabilityError",
    "PeerAnalysisCapabilityId",
    "PeerAnalysisCapabilityInput",
    "PeerAnalysisCapabilityRegistry",
    "create_peer_analysis_capability_registry",
]
