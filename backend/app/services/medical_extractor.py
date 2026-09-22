"""Materialize typed document facts without clinical inference or timeline generation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.document import StructuredDocument


def extract_medical_facts(db: Session, document_extraction: models.DocumentExtraction) -> None:
    # Serialize retries against the persisted source; never commit the caller.
    source = db.scalar(
        select(models.DocumentExtraction)
        .where(models.DocumentExtraction.id == document_extraction.id)
        .with_for_update()
    )
    if source is None:
        raise ValueError("A persisted document extraction is required")
    document = db.get(models.Document, source.document_id)
    if document is None or document.session_id != source.session_id:
        raise ValueError("Document extraction session does not match its source")
    structured = StructuredDocument.model_validate(source.structured_json)
    session = db.get(models.Session, source.session_id)
    if session is None or session.status in ("confirmed", "cancelled"):
        raise ValueError("Cannot materialize facts in a locked session")
    if source.verification_status == "rejected":
        return
    if structured.document_type == "prescription":
        model, values = models.MedicationFact, structured.medications
    elif structured.document_type == "lab_report":
        model, values = models.LabFact, structured.observations
    else:
        # No timeline events or clinical-note types in the current document contract.
        return
    if db.scalar(select(model.id).where(model.document_extraction_id == source.id).limit(1)):
        return
    facts = []
    for value in values:
        value_dict = value.model_dump()
        # Remove source_text and source_location from value_dict to avoid conflicts
        # with explicit parameters below
        value_dict.pop('source_text', None)
        value_dict.pop('source_location', None)
        facts.append(
            model(
                session_id=source.session_id,
                document_extraction_id=source.id,
                source_text=source.raw_text,
                source_location=None,
                verification_status="unverified",
                **value_dict,
            )
        )
    # Keep any row failure isolated from the upload and preserve its raw extraction.
    with db.begin_nested():
        db.add_all(facts)
        db.flush()
        from app.services import clinical_evidence

        for fact in facts:
            clinical_evidence.create_document_evidence(db, fact, source)
