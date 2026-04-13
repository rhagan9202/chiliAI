"""Tests for embeddings module models."""

from __future__ import annotations

import pytest

from embeddings.models import EmbeddingItem, EmbeddingRequest
from embeddings.service_models import EmbedRequest, EmbedSubmission


def test_embedding_item_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        EmbeddingItem(id="item-1", content=" ")


def test_embedding_request_requires_items() -> None:
    with pytest.raises(ValueError, match="at least one item"):
        EmbeddingRequest(request_id="request-1", model_name="test-model", items=[])


def test_embed_request_requires_submissions() -> None:
    with pytest.raises(ValueError, match="at least one submission"):
        EmbedRequest(submissions=[])


def test_embed_submission_accepts_valid_content() -> None:
    submission = EmbedSubmission(content_id="content-1", content="Policy paragraph")

    assert submission.content_id == "content-1"