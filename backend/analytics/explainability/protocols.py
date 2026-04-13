"""Service-level protocols for the explainability analytics module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.explainability.service_models import ExplainabilityRequest, ExplainabilityResponse


@runtime_checkable
class ExplainabilityServiceProtocol(Protocol):
    """Service boundary for evidence-pack generation."""

    def generate(self, request: ExplainabilityRequest) -> ExplainabilityResponse: ...