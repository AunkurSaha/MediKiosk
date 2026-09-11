from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_auth_user, get_current_user, get_optional_auth_user
from app.database import get_db
from app.schemas.document import (
    DocumentExtractionResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentType,
    ExtractionVerifyRequest,
)
from app.services import document_service, intake
from app.services.storage import default_storage

router = APIRouter()


@router.post("/{session_id}/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    session_id: UUID,
    file: UploadFile = File(...),
    document_type: DocumentType | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    doc = await document_service.ingest_document(
        db=db,
        session_id=str(session_id),
        file=file,
        document_type=document_type,
    )
    return doc


@router.get("/{session_id}/documents", response_model=DocumentListResponse)
def list_documents(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    docs = document_service.get_session_documents(db=db, session_id=str(session_id))
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/{session_id}/documents/{document_id}", response_model=DocumentResponse)
def get_document_detail(
    session_id: UUID,
    document_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    return document_service.get_document(db=db, session_id=str(session_id), document_id=document_id)


@router.get("/{session_id}/documents/{document_id}/file")
def get_document_file(
    session_id: UUID,
    document_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    doc = document_service.get_document(db=db, session_id=str(session_id), document_id=document_id)
    file_path = default_storage.get_file_path(doc.object_key)
    return FileResponse(
        path=str(file_path),
        media_type=doc.media_type,
        filename=doc.original_filename,
    )


@router.post(
    "/{session_id}/documents/{document_id}/extractions/{extraction_id}/verify",
    response_model=DocumentExtractionResponse,
)
def verify_document_extraction(
    session_id: UUID,
    document_id: str,
    extraction_id: str,
    payload: ExtractionVerifyRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    return document_service.verify_extraction(
        db=db,
        session_id=str(session_id),
        document_id=document_id,
        extraction_id=extraction_id,
        status=payload.status,
        user=user,
        expected_status=payload.expected_status,
        expected_version=payload.expected_version,
        notes=payload.notes,
    )
