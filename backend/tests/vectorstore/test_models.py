"""Tests for vectorstore module models."""

from __future__ import annotations

import pytest

from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorAuditArtifact,
    VectorDeleteResponse,
    VectorIndexRequest,
    VectorIndexReceipt,
    VectorIndexSubmission,
    VectorSearchRequest,
)


def test_vector_record_requires_embedding() -> None:
    with pytest.raises(ValueError, match="non-empty embedding"):
        VectorRecord(
            id="record-1",
            knowledge_base_id="kb-1",
            content_id="content-1",
            embedding=[],
        )


def test_vector_index_request_requires_submissions() -> None:
    with pytest.raises(ValueError, match="at least one submission"):
        VectorIndexRequest(knowledge_base_id="kb-1", submissions=[])


def test_vector_search_request_requires_query_vector() -> None:
    with pytest.raises(ValueError, match="query_vector"):
        VectorSearchRequest(knowledge_base_id="kb-1", query_vector=[])


def test_vector_index_submission_accepts_metadata() -> None:
    submission = VectorIndexSubmission(
        content_id="content-1",
        embedding=[0.1, 0.2, 0.3],
        metadata={"source": "policy", "rank": 1},
    )

    assert submission.metadata["source"] == "policy"


def test_vector_delete_response_records_deleted_count() -> None:
    response = VectorDeleteResponse(knowledge_base_id="kb-1", deleted_count=3)

    assert response.knowledge_base_id == "kb-1"
    assert response.deleted_count == 3


def test_vector_delete_response_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        VectorDeleteResponse(knowledge_base_id="kb-1", deleted_count=-1)


def test_vector_audit_artifact_summarizes_receipts() -> None:
    receipt = VectorIndexReceipt(
        knowledge_base_id="kb-1",
        record_id="record-1",
        content_id="content-1",
        dimension=2,
    )

    artifact = VectorAuditArtifact(
        request_id="request-1",
        knowledge_base_id="kb-1",
        receipts=[receipt],
    )

    assert artifact.receipt_count == 1
    assert artifact.receipts == [receipt]
    assert '"receipt_count":1' in artifact.model_dump_json()
