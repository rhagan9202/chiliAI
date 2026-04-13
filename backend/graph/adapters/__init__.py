"""Graph repository adapters."""

from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository

__all__ = ["GraphRepository", "InMemoryGraphRepository"]