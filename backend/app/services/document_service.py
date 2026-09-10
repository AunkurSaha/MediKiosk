import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import WorkflowError
from app.schemas.document import StructuredDocument
from app.services import intake
from app.services.document_parser import parse_document
from app.services.ocr_provider import get_ocr_provider
from app.services.storage import (
    MAX_DOCUMENT_BYTES,
    default_storage,
    validate_document_contents,
    validate_document_file,
    validate_document_media_type,
)

logger = logging.getLogger(__name__)


async def ingest_document(
    db: Session,
    session_id: str,
    file: UploadFile,
    document_type: str | None = None,
) -> models.Document:
    try:
        session = intake.get_session(db, session_id)
        if not session:
            raise WorkflowError("SESSION_NOT_FOUND", "Session not found.", 404)

        if session.status != "intake":
            raise WorkflowError(
                "SESSION_LOCKED", "Document upload is only allowed during active intake.", 409
            )

        consent = db.scalar(select(models.Consent).where(models.Consent.session_id == session_id))
        if not consent or not consent.share_with_doctor:
            raise WorkflowError("CONSENT_REQUIRED", "Doctor sharing consent is required.", 403)

        if not consent.document_processing:
            raise WorkflowError(
                "DOCUMENT_CONSENT_REQUIRED",
                "Document processing consent is required to upload medical documents.",
                403,
            )

        if document_type not in (None, "prescription", "lab_report", "other"):
            raise WorkflowError("INVALID_DOCUMENT_TYPE", "Unsupported document type.", 422)
        media_type = validate_document_media_type(file.content_type)

        # Stream file into memory enforcing byte limits
        data = bytearray()
        chunk_size = 64 * 1024
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_DOCUMENT_BYTES:
                raise WorkflowError(
                    "FILE_TOO_LARGE",
                    f"Document exceeds maximum size ({MAX_DOCUMENT_BYTES // (1024 * 1024)}MB).",
                    422,
                )

        if len(data) == 0:
            raise WorkflowError("EMPTY_FILE", "Uploaded document is empty.", 422)

        # Re-validate with actual bytes
        validate_document_file(media_type, len(data))
        validate_document_contents(bytes(data), media_type)

        doc_id = str(uuid.uuid4())
        filename = file.filename or f"document_{doc_id[:8]}"

        # Save to storage
        object_key, sha256_hash, file_size = default_storage.save_file(
            session_id=session_id,
            doc_id=doc_id,
            filename=filename,
            data=bytes(data),
        )

        try:
            doc = models.Document(
                id=doc_id,
                session_id=session_id,
                object_key=object_key,
                original_filename=filename,
                media_type=media_type,
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                document_type=document_type or "other",
                processing_status="processing",
            )
            db.add(doc)
            db.flush()

            # Execute OCR and parsing
            try:
                ocr_provider = get_ocr_provider()
                raw_text, confidence, metadata = await asyncio.wait_for(
                    ocr_provider.extract(
                        image_bytes=bytes(data),
                        media_type=media_type,
                        filename=filename,
                    ),
                    timeout=5.0,
                )
                inferred_type, doc_date, structured = parse_document(raw_text, filename)

                doc.document_type = document_type or inferred_type
                doc.document_date = doc_date
                doc.processing_status = (
                    "mock_fixture" if metadata.get("fixture_id") else "unavailable"
                )

                extraction = models.DocumentExtraction(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    session_id=session_id,
                    extractor=ocr_provider.name,
                    extractor_version=ocr_provider.version,
                    raw_text=raw_text,
                    structured_json=StructuredDocument.model_validate(structured).model_dump(
                        mode="json"
                    ),
                    confidence=confidence,
                    verification_status="unverified",
                )
                if raw_text and metadata.get("fixture_id"):
                    db.add(extraction)
                    # Flush to get the extraction ID before extracting medical facts
                    db.flush()
                    # Extract medical facts from the document extraction
                    from app.services.medical_extractor import extract_medical_facts

                    extract_medical_facts(db, extraction)

            except Exception as e:
                logger.warning(f"OCR processing failed for document {doc.id}: {type(e).__name__}")
                doc.processing_status = "failed"

            intake.audit(
                db,
                action="document_uploaded",
                entity_id=session_id,
                user=None,
                metadata={
                    "document_id": doc.id,
                    "filename": filename,
                    "file_size": file_size,
                    "sha256": sha256_hash,
                    "document_type": doc.document_type,
                },
            )

            db.commit()
        except BaseException:
            db.rollback()
            default_storage.delete_file(object_key)
            raise
        db.refresh(doc)
        return doc
    finally:
        await file.close()


def get_session_documents(db: Session, session_id: str) -> list[models.Document]:
    intake.require_consent(db, session_id)
    stmt = (
        select(models.Document)
        .where(models.Document.session_id == session_id)
        .order_by(models.Document.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_document(db: Session, session_id: str, document_id: str) -> models.Document:
    intake.require_consent(db, session_id)
    doc = db.get(models.Document, document_id)
    if not doc or doc.session_id != session_id:
        raise WorkflowError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    return doc


def verify_extraction(
    db: Session,
    session_id: str,
    document_id: str,
    extraction_id: str,
    status: str,
    user: models.User,
    expected_status: str = "unverified",
    expected_version: int = 0,
    notes: str | None = None,
) -> models.DocumentExtraction:
    session = intake.get_session(db, session_id)
    intake.require_consent(db, session_id)
    if session.status in ("confirmed", "cancelled"):
        raise WorkflowError("SESSION_LOCKED", "This record is locked.", 409)
    doc = get_document(db, session_id, document_id)
    extraction = db.get(models.DocumentExtraction, extraction_id)
    if not extraction or extraction.document_id != doc.id:
        raise WorkflowError("EXTRACTION_NOT_FOUND", "Document extraction not found.", 404)

    if (
        extraction.verification_status != expected_status
        or extraction.review_version != expected_version
    ):
        raise WorkflowError(
            "VERSION_CONFLICT", "Extraction review changed; reload before reviewing.", 409
        )
    previous = {
        "status": extraction.verification_status,
        "verified_by": extraction.verified_by,
        "verified_at": extraction.verified_at.isoformat() if extraction.verified_at else None,
        "notes": extraction.verification_notes,
    }
    extraction.verification_status = status
    extraction.review_version += 1
    extraction.verified_by = user.id
    extraction.verified_at = datetime.now(timezone.utc)
    extraction.verification_notes = notes

    intake.audit(
        db,
        action="document_extraction_verified",
        entity_id=session_id,
        user=user,
        metadata={
            "document_id": doc.id,
            "extraction_id": extraction.id,
            "status": status,
            "verified_by": user.id,
            "previous": previous,
            "notes": notes,
        },
    )

    db.commit()
    db.refresh(extraction)

    return extraction
