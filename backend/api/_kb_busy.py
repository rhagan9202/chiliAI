"""Helper for refusing mutations while a KB workflow is in flight."""

from __future__ import annotations

from typing import Protocol


class KbBusyError(Exception):
    """Raised when a KB-scoped mutation is attempted during an active workflow."""

    def __init__(self, knowledge_base_id: str) -> None:
        super().__init__(
            f"Knowledge base '{knowledge_base_id}' has a workflow in progress."
        )
        self.knowledge_base_id = knowledge_base_id


class WorkflowBusyTracker(Protocol):
    def is_busy(self, knowledge_base_id: str) -> bool: ...


def ensure_kb_idle(
    knowledge_base_id: str,
    *,
    tracker: WorkflowBusyTracker,
) -> None:
    if tracker.is_busy(knowledge_base_id):
        raise KbBusyError(knowledge_base_id)


__all__ = ["KbBusyError", "WorkflowBusyTracker", "ensure_kb_idle"]
