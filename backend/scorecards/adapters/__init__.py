"""Scorecard persistence adapters."""

from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.adapters.postgres import PostgresScorecardRunRepository
from scorecards.adapters.protocols import ScorecardRunRepository

__all__ = [
    "InMemoryScorecardRunRepository",
    "PostgresScorecardRunRepository",
    "ScorecardRunRepository",
]
