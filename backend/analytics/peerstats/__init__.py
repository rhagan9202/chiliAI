"""Cross-sectional peer-group z-score analytics."""

from __future__ import annotations

from analytics.peerstats.exceptions import (
    PeerStatsConfigurationError,
    PeerStatsError,
    PeerStatsSourceError,
)
from analytics.peerstats.capability import (
    PeerAnalysisCapability,
    PeerAnalysisCapabilityDescriptor,
    PeerAnalysisCapabilityDisabledError,
    PeerAnalysisCapabilityError,
    PeerAnalysisCapabilityInput,
    PeerAnalysisCapabilityRegistry,
    create_peer_analysis_capability_registry,
)
from analytics.peerstats.models import (
    DerivedRiskSignal,
    PeerAggregate,
)
from analytics.peerstats.service import PeerStatsService, create_peerstats_service

__all__ = [
    "DerivedRiskSignal",
    "PeerAnalysisCapability",
    "PeerAnalysisCapabilityDescriptor",
    "PeerAnalysisCapabilityDisabledError",
    "PeerAnalysisCapabilityError",
    "PeerAnalysisCapabilityInput",
    "PeerAnalysisCapabilityRegistry",
    "PeerAggregate",
    "PeerStatsConfigurationError",
    "PeerStatsError",
    "PeerStatsService",
    "PeerStatsSourceError",
    "create_peer_analysis_capability_registry",
    "create_peerstats_service",
]
