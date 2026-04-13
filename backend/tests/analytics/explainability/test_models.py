"""Tests for explainability module models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationSubgraph
from shared.types import Alert


def test_explanation_subgraph_requires_nodes() -> None:
    with pytest.raises(ValueError, match="at least one node"):
        ExplanationSubgraph(node_ids=[])


def test_explanation_context_requires_items() -> None:
    with pytest.raises(ValueError, match="at least one explanation item"):
        ExplanationContext(
            knowledge_base_id="kb-1",
            alert=Alert(
                id="alert-1",
                entity_type="provider",
                entity_id="provider-7",
                severity="high",
                title="Outlier",
                reasoning="Detected",
                created_at=datetime.now(timezone.utc),
            ),
            explanation_items=[],
            subgraph=ExplanationSubgraph(node_ids=["provider-7"]),
            confidence=0.9,
        )