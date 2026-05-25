"""Resolve a primary KB id into the full read scope for the domain.

The dual-graph contract allows reads to span a primary (transactional) KB
plus a domain-level reference (policy) KB. This module is the single point
of policy for assembling the read scope at the API handler boundary.
"""

from __future__ import annotations

import logging
from typing import Protocol

from config.schema import DomainConfig

logger = logging.getLogger(__name__)


class KnowledgeBaseExistenceCheck(Protocol):
    """Minimal protocol the resolver uses to verify a reference KB exists.

    The full `KnowledgeBaseRepository` (api._kb_store) satisfies this protocol
    because it has a `get(knowledge_base_id) -> KnowledgeBase | None` method.
    Tests can supply a smaller stub.
    """

    def get(self, knowledge_base_id: str) -> object | None: ...


def resolve_kb_scope(
    primary_kb_id: str,
    domain_config: DomainConfig,
    kb_repository: KnowledgeBaseExistenceCheck,
) -> list[str]:
    """Return the list of KB IDs that reads should span for this request.

    - If the domain has no ``default_reference_kb_id``, returns ``[primary]``.
    - If the primary IS the reference KB (the analyst is querying the policy
      KB itself), returns ``[primary]`` only — no self-attach loop.
    - If the reference KB is configured but doesn't exist, logs a WARNING and
      returns ``[primary]`` only. The app keeps running with degraded behavior.
    - Otherwise returns ``[primary, reference]`` in that order.

    Args:
        primary_kb_id: The active KB the analyst selected for the request.
        domain_config: The loaded domain configuration.
        kb_repository: An existence check against the KB metadata store.

    Returns:
        Ordered list of KB IDs that downstream protocols should read across.
    """
    reference_id = domain_config.default_reference_kb_id
    if reference_id is None:
        return [primary_kb_id]
    if reference_id == primary_kb_id:
        return [primary_kb_id]
    if kb_repository.get(reference_id) is None:
        logger.warning(
            "Configured default_reference_kb_id=%r does not exist; "
            "falling back to primary-only scope (primary=%r)",
            reference_id,
            primary_kb_id,
        )
        return [primary_kb_id]
    return [primary_kb_id, reference_id]


__all__ = ["KnowledgeBaseExistenceCheck", "resolve_kb_scope"]
