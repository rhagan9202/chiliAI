"""Service-boundary protocol for peerstats."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.peerstats.service_models import (
    PeerStatsComputeRequest,
    PeerStatsComputeResponse,
)


@runtime_checkable
class PeerStatsServiceProtocol(Protocol):
    """Compute and persist peer-group z-score signals for a metric spec."""

    def compute(
        self, request: PeerStatsComputeRequest
    ) -> PeerStatsComputeResponse: ...


__all__ = ["PeerStatsServiceProtocol"]
