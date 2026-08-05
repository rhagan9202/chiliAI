"""Governance repository adapters."""

from governance.adapters.in_memory import InMemoryGovernanceEvalRepository
from governance.adapters.postgres import PostgresGovernanceEvalRepository

__all__ = ["InMemoryGovernanceEvalRepository", "PostgresGovernanceEvalRepository"]
