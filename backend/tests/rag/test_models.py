"""Tests for rag module models."""

from __future__ import annotations

import pytest

from rag.models import ContextRecord, RagGenerationResult
from rag.service_models import RagQueryRequest


def test_context_record_requires_embedding() -> None:
    with pytest.raises(ValueError, match="non-empty embedding"):
        ContextRecord(record_id="record-1", content_id="content-1", embedding=[], content="Alpha")


def test_rag_query_request_requires_question() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RagQueryRequest(knowledge_base_id="kb-1", question=" ")


def test_rag_generation_result_requires_answer() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RagGenerationResult(
            request_id="request-1",
            answer=" ",
            provider="in-memory",
            model_name="model",
        )