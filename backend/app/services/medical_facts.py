"""Source-linked medical fact retrieval and additive clinician review."""

from collections import Counter

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import WorkflowError
from app.schemas.medical_fact import (
    FactRevision,
    FactSource,
    FactStatusCounts,
    LabFactRecord,
    LabFactReview,
    LabValue,
    MedicalFactsResponse,
    MedicationFactRecord,
    MedicationFactReview,
    MedicationValue,
)
from app.services import intake

MEDICATION_FIELDS = (
    "name",
    "dosage",
    "unit",
    "route",
    "frequency",
    "duration",
    "start_date",
    "end_date",
    "instructions",
)
LAB_FIELDS = (
    "test_name",
    "value",
    "unit",
    "reference_range",
    "flag",
    "observation_timestamp",
)


def _original(row, fields, schema):
    return schema.model_validate({field: getattr(row, field) for field in fields})


def _revisions(db: Session, fact_type: str, fact_id: str) -> list[models.MedicalFactRevision]:
    return list(
        db.scalars(
            select(models.MedicalFactRevision)
            .where(
                models.MedicalFactRevision.fact_type == fact_type,
                models.MedicalFactRevision.fact_id == fact_id,
            )
            .order_by(models.MedicalFactRevision.version, models.MedicalFactRevision.id)
        )
    )


def _current(original, revisions):
    for revision in reversed(revisions):
        if revision.corrected_data is not None:
            return original.__class__.model_validate(revision.corrected_data)
    return original


def _source(db: Session, row) -> FactSource:
    extraction = (
        db.get(models.DocumentExtraction, row.document_extraction_id)
        if row.document_extraction_id
        else None
    )
    document = db.get(models.Document, extraction.document_id) if extraction else None
    return FactSource(
        source_type="document",
        source_id=extraction.id if extraction else row.id,
        document_id=document.id if document else None,
        extraction_id=extraction.id if extraction else None,
        document_filename=document.original_filename if document else None,
        raw_text=row.source_text,
        source_location=row.source_location,
    )


def _revision_responses(rows):
    return [
        FactRevision(
            id=row.id,
            version=row.version,
            review_status=row.review_status,
            corrected_data=row.corrected_data,
            reviewer_id=row.reviewer_id,
            review_notes=row.review_notes,
            reviewed_at=row.reviewed_at,
        )
        for row in rows
    ]


def medication_record(db: Session, row: models.MedicationFact) -> MedicationFactRecord:
    revisions = _revisions(db, "medication", row.id)
    original = _original(row, MEDICATION_FIELDS, MedicationValue)
    return MedicationFactRecord(
        id=row.id,
        original=original,
        current=_current(original, revisions),
        source=_source(db, row),
        verification_status=row.verification_status,
        review_version=row.review_version,
        verified_by=row.verified_by,
        verified_at=row.verified_at,
        verification_notes=row.verification_notes,
        revisions=_revision_responses(revisions),
    )


def lab_record(db: Session, row: models.LabFact) -> LabFactRecord:
    revisions = _revisions(db, "lab", row.id)
    original = _original(row, LAB_FIELDS, LabValue)
    return LabFactRecord(
        id=row.id,
        original=original,
        current=_current(original, revisions),
        source=_source(db, row),
        verification_status=row.verification_status,
        review_version=row.review_version,
        verified_by=row.verified_by,
        verified_at=row.verified_at,
        verification_notes=row.verification_notes,
        revisions=_revision_responses(revisions),
    )


def _source_is_active(db: Session, row) -> bool:
    if not row.document_extraction_id:
        return True
    extraction = db.get(models.DocumentExtraction, row.document_extraction_id)
    return extraction is not None and extraction.verification_status != "rejected"


def get_current_facts(db: Session, session_id: str) -> MedicalFactsResponse:
    intake.get_session(db, session_id)
    intake.require_consent(db, session_id)
    medication_rows = [
        row
        for row in db.scalars(
            select(models.MedicationFact)
            .where(models.MedicationFact.session_id == session_id)
            .order_by(
                models.MedicationFact.name,
                models.MedicationFact.created_at,
                models.MedicationFact.id,
            )
        )
        if _source_is_active(db, row)
    ]
    lab_rows = [
        row
        for row in db.scalars(
            select(models.LabFact)
            .where(models.LabFact.session_id == session_id)
            .order_by(models.LabFact.test_name, models.LabFact.created_at, models.LabFact.id)
        )
        if _source_is_active(db, row)
    ]
    medications = [medication_record(db, row) for row in medication_rows]
    labs = [lab_record(db, row) for row in lab_rows]
    counts = Counter(item.verification_status for item in [*medications, *labs])
    return MedicalFactsResponse(
        medications=[item for item in medications if item.verification_status != "rejected"],
        labs=[item for item in labs if item.verification_status != "rejected"],
        rejected_medications=[
            item for item in medications if item.verification_status == "rejected"
        ],
        rejected_labs=[item for item in labs if item.verification_status == "rejected"],
        counts=FactStatusCounts(
            unverified=counts["unverified"],
            verified=counts["verified"],
            rejected=counts["rejected"],
        ),
    )


def _review(
    db: Session,
    session_id: str,
    fact_id: str,
    payload,
    user: models.User,
    *,
    fact_type: str,
    model,
    fields,
    value_schema,
    response_builder,
):
    session = intake.get_session(db, session_id)
    intake.require_consent(db, session_id)
    if session.status in ("confirmed", "cancelled"):
        raise WorkflowError(
            "SESSION_LOCKED", "Confirmed or cancelled facts require an amendment workflow."
        )
    row = db.scalar(
        select(model).where(model.id == fact_id, model.session_id == session_id).with_for_update()
    )
    if row is None:
        raise WorkflowError("FACT_NOT_FOUND", "Medical fact not found.", 404)
    if not _source_is_active(db, row):
        raise WorkflowError(
            "SOURCE_REJECTED", "Facts from a rejected extraction cannot be reviewed."
        )
    if row.review_version != payload.expected_version:
        raise WorkflowError("FACT_VERSION_CONFLICT", "This fact changed. Reload before reviewing.")
    if payload.status == "rejected" and payload.correction is not None:
        raise WorkflowError(
            "INVALID_FACT_REVIEW", "A rejected fact cannot also carry a correction.", 422
        )

    original = _original(row, fields, value_schema)
    prior = _revisions(db, fact_type, row.id)
    current = _current(original, prior)
    corrected = None
    if payload.correction is not None:
        merged = current.model_dump(mode="json")
        merged.update(payload.correction.model_dump(mode="json", exclude_unset=True))
        try:
            corrected = value_schema.model_validate(merged)
        except ValidationError as error:
            raise WorkflowError(
                "INVALID_FACT_CORRECTION", "Corrected fact fields are invalid.", 422
            ) from error

    reviewed_at = intake.now()
    version = row.review_version + 1
    effective = corrected or (current if current != original else None)
    db.add(
        models.MedicalFactRevision(
            session_id=session_id,
            fact_type=fact_type,
            fact_id=row.id,
            version=version,
            review_status=payload.status,
            original_data=original.model_dump(mode="json"),
            corrected_data=effective.model_dump(mode="json") if effective else None,
            reviewer_id=user.id,
            review_notes=payload.notes,
            reviewed_at=reviewed_at,
        )
    )
    row.review_version = version
    row.verification_status = payload.status
    row.verified_by = user.id
    row.verified_at = reviewed_at
    row.verification_notes = payload.notes
    row.updated_at = reviewed_at
    intake.audit(
        db,
        "medical_fact_reviewed",
        session_id,
        user,
        metadata={
            "fact_id": row.id,
            "fact_type": fact_type,
            "version": version,
            "status": payload.status,
        },
    )
    db.commit()
    db.refresh(row)
    return response_builder(db, row)


def review_medication(
    db: Session,
    session_id: str,
    fact_id: str,
    payload: MedicationFactReview,
    user: models.User,
) -> MedicationFactRecord:
    return _review(
        db,
        session_id,
        fact_id,
        payload,
        user,
        fact_type="medication",
        model=models.MedicationFact,
        fields=MEDICATION_FIELDS,
        value_schema=MedicationValue,
        response_builder=medication_record,
    )


def review_lab(
    db: Session,
    session_id: str,
    fact_id: str,
    payload: LabFactReview,
    user: models.User,
) -> LabFactRecord:
    return _review(
        db,
        session_id,
        fact_id,
        payload,
        user,
        fact_type="lab",
        model=models.LabFact,
        fields=LAB_FIELDS,
        value_schema=LabValue,
        response_builder=lab_record,
    )
