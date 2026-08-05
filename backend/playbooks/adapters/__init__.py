"""Playbook repository adapters."""

from __future__ import annotations

from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.adapters.postgres import PostgresPlaybookRepository

__all__ = ["InMemoryPlaybookRepository", "PostgresPlaybookRepository"]
