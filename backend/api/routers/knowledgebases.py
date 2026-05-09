"""Knowledge base API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel

from api.contracts import (
	ApiEnvelope,
	KnowledgeBaseDetailResponse,
	KnowledgeBaseDocumentListResponse,
	KnowledgeBaseDocumentStatusResponse,
	KnowledgeBaseListResponse,
	WorkflowRunResponse,
)
from api.dependencies import (
	get_api_state,
	get_ingestion_service,
	get_knowledge_base_create_payload,
	get_knowledge_base_delete_payload,
	get_knowledge_base_detail_payload,
	get_knowledge_base_document_delete_payload,
	get_knowledge_base_document_status_payload,
	get_knowledge_base_documents_payload,
	get_knowledge_base_list_payload,
	get_knowledge_base_rebuild_payload,
)
from api.state import ApiState
from ingestion.protocols import IngestionServiceProtocol
from ingestion.service_models import DocumentReceipt, DocumentSubmission

__all__ = ["DocumentRegistrationResponse", "router"]


class DocumentRegistrationResponse(BaseModel):
	"""Response model for document registration requests."""

	documents: list[DocumentReceipt]


router = APIRouter(prefix="/knowledgebases", tags=["knowledge-bases"])


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
	payload: KnowledgeBaseListResponse = Depends(get_knowledge_base_list_payload),
) -> KnowledgeBaseListResponse:
	"""Return all knowledge bases visible to the current workspace."""
	return payload


@router.post("", response_model=KnowledgeBaseDetailResponse)
async def create_knowledge_base(
	payload: KnowledgeBaseDetailResponse = Depends(get_knowledge_base_create_payload),
) -> KnowledgeBaseDetailResponse:
	"""Create a knowledge base metadata record."""
	return payload


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseDetailResponse)
async def get_knowledge_base(
	payload: KnowledgeBaseDetailResponse = Depends(get_knowledge_base_detail_payload),
) -> KnowledgeBaseDetailResponse:
	"""Return one knowledge base summary and recent workflow context."""
	return payload


@router.delete("/{knowledge_base_id}", response_model=ApiEnvelope)
async def delete_knowledge_base(
	payload: ApiEnvelope = Depends(get_knowledge_base_delete_payload),
) -> ApiEnvelope:
	"""Delete one knowledge base."""
	return payload


@router.get("/{knowledge_base_id}/documents", response_model=KnowledgeBaseDocumentListResponse)
async def list_knowledge_base_documents(
	payload: KnowledgeBaseDocumentListResponse = Depends(get_knowledge_base_documents_payload),
) -> KnowledgeBaseDocumentListResponse:
	"""Return the document inventory for one knowledge base."""
	return payload


@router.get(
	"/{knowledge_base_id}/documents/{document_id}/status",
	response_model=KnowledgeBaseDocumentStatusResponse,
)
async def get_knowledge_base_document_status(
	payload: KnowledgeBaseDocumentStatusResponse = Depends(get_knowledge_base_document_status_payload),
) -> KnowledgeBaseDocumentStatusResponse:
	"""Return the ingestion timeline for one document."""
	return payload


@router.delete(
	"/{knowledge_base_id}/documents/{document_id}",
	response_model=ApiEnvelope,
)
async def delete_knowledge_base_document(
	payload: ApiEnvelope = Depends(get_knowledge_base_document_delete_payload),
) -> ApiEnvelope:
	"""Delete one source document from a knowledge base."""
	return payload


@router.post("/{knowledge_base_id}/rebuild", response_model=WorkflowRunResponse)
async def rebuild_knowledge_base(
	payload: WorkflowRunResponse = Depends(get_knowledge_base_rebuild_payload),
) -> WorkflowRunResponse:
	"""Queue a graph and index rebuild for one knowledge base."""
	return payload


@router.post(
	"/{knowledge_base_id}/documents",
	status_code=status.HTTP_202_ACCEPTED,
	response_model=DocumentRegistrationResponse,
)
async def register_knowledge_base_documents(
	knowledge_base_id: str,
	files: list[UploadFile] = File(...),
	ingestion_service: IngestionServiceProtocol = Depends(get_ingestion_service),
	state: ApiState = Depends(get_api_state),
) -> DocumentRegistrationResponse:
	"""Register uploaded documents and enqueue ingestion work."""
	submissions: list[DocumentSubmission] = []
	for upload in files:
		submissions.append(
			DocumentSubmission(
				filename=upload.filename,
				content=await upload.read(),
				content_type=upload.content_type,
			)
		)

	receipts = ingestion_service.register_documents(knowledge_base_id, submissions)
	state.register_knowledge_base_documents(knowledge_base_id, receipts, submissions)
	return DocumentRegistrationResponse(documents=receipts)
