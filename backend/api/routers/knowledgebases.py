"""Knowledge base API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel

from api.dependencies import get_ingestion_service
from ingestion.protocols import IngestionServiceProtocol
from ingestion.service_models import DocumentReceipt, DocumentSubmission

__all__ = ["DocumentRegistrationResponse", "router"]


class DocumentRegistrationResponse(BaseModel):
	"""Response model for document registration requests."""

	documents: list[DocumentReceipt]


router = APIRouter(prefix="/knowledgebases", tags=["knowledge-bases"])

# TODO(production): Add missing CRUD endpoints:
# - GET /knowledgebases — list all knowledge bases
# - POST /knowledgebases — create a new knowledge base
# - GET /knowledgebases/{kb_id} — get KB metadata
# - DELETE /knowledgebases/{kb_id} — delete entire KB and all associated data
# - GET /knowledgebases/{kb_id}/documents — list documents in KB
# - GET /knowledgebases/{kb_id}/documents/{doc_id}/status — ingestion status
# - DELETE /knowledgebases/{kb_id}/documents/{doc_id} — remove a document


@router.post(
	"/{knowledge_base_id}/documents",
	status_code=status.HTTP_202_ACCEPTED,
	response_model=DocumentRegistrationResponse,
)
async def register_knowledge_base_documents(
	knowledge_base_id: str,
	files: list[UploadFile] = File(...),
	ingestion_service: IngestionServiceProtocol = Depends(get_ingestion_service),
) -> DocumentRegistrationResponse:
	"""Register uploaded documents and enqueue ingestion work."""
	# TODO(production): Add input validation and security hardening:
	# - Validate knowledge_base_id format (alphanumeric + dashes)
	# - Verify KB exists before accepting documents
	# - Enforce max file size (e.g. 100MB) and max file count per request
	# - Whitelist content types (reject unexpected MIME types)
	# - Add filename sanitization (prevent path traversal)
	# - Add async timeout on upload.read() for large files
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
	return DocumentRegistrationResponse(documents=receipts)
