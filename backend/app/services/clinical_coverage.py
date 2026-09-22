"""Deterministic interview coverage derived from existing evidence and answers."""

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.coverage import (
    CoverageField,
    CoverageProvenance,
    CoverageResponse,
    DocumentAwareDemoMetrics,
    DocumentConfirmationContext,
)
from app.schemas.flow import Flow
from app.services import discrepancies, intake
from app.services.flow_registry import registry

DOCUMENT_CONFIRMATION_PREFIX = "document_confirmation."
CONTINUITY_PREFIX = "continuity."
MEDICATION_FIELDS = {"medications.any", "medications.details", "medications"}


def _answer_envelope(row: models.InterviewAnswer) -> dict:
    stored = json.loads(row.value_json) if row.value_json else None
    return (
        stored
        if isinstance(stored, dict) and "status" in stored
        else {
            "status": "answered",
            "value": stored,
        }
    )


def _latest_answers(db: Session, session_id: str) -> dict[str, models.InterviewAnswer]:
    result = {}
    from app.services import continuity

    for row in continuity.authoritative_interview_answers(db, session_id):
        if not row.question_id.startswith((DOCUMENT_CONFIRMATION_PREFIX, CONTINUITY_PREFIX)):
            result[row.field] = row
    return result


def _flow(db: Session, session_id: str) -> Flow | None:
    run = db.get(models.InterviewRun, session_id)
    if run:
        return Flow.model_validate(run.flow_snapshot)
    if intake.latest_answers(db, session_id):
        return registry()["legacy.intake"]
    return None


def _medication_evidence(db: Session, session_id: str):
    rows = list(
        db.scalars(
            select(models.ClinicalEvidence)
            .where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.source_type == "DOCUMENT",
                models.ClinicalEvidence.concept_code == "MEDICATION_MENTION",
                models.ClinicalEvidence.verification_status.notin_(("REJECTED",)),
            )
            .order_by(models.ClinicalEvidence.created_at, models.ClinicalEvidence.id)
        )
    )
    return [
        row
        for row in rows
        if not (row.metadata_json or {}).get("extraction_id")
        or (
            (extraction := db.get(models.DocumentExtraction, row.metadata_json["extraction_id"]))
            is not None
            and extraction.verification_status != "rejected"
        )
    ]


def _provenance(db: Session, row: models.ClinicalEvidence) -> CoverageProvenance:
    metadata = row.metadata_json or {}
    document = db.get(models.Document, metadata.get("document_id"))
    location = metadata.get("source_location")
    page = location.get("page") if isinstance(location, dict) else None
    bbox = location.get("bounding_box") if isinstance(location, dict) else None
    if page is None and isinstance(location, str):
        match = re.search(r"page\s*(\d+)", location, re.IGNORECASE)
        page = int(match.group(1)) if match else None
    value = row.value_json or {}
    display = " ".join(
        str(value.get(key)).strip()
        for key in ("name", "dosage", "unit", "frequency")
        if value.get(key)
    )
    return CoverageProvenance(
        evidence_id=row.id,
        source_fact_id=row.source_id,
        source_document_id=metadata.get("document_id"),
        document_filename=document.original_filename if document else None,
        page_number=page,
        bounding_box=bbox,
        ocr_provider=metadata.get("ocr_provider"),
        ocr_model=metadata.get("ocr_provider_version"),
        original_extracted_value=display or row.original_text,
        verification_state=row.verification_status,
    )


def _conflicted_fields(db: Session, session_id: str) -> set[str]:
    result = discrepancies.get_discrepancies(db, session_id)
    fields = set()
    if any(item.type.startswith("MEDICATION_") for item in result.items):
        fields.update(MEDICATION_FIELDS)
    return fields


def _coverage_applicable(question, answers) -> bool:
    """Treat unanswered branch parents as pending coverage, not exclusion."""
    for condition in question.when:
        parent = answers.get(condition.question_id)
        if parent is None or parent.status != "answered":
            continue
        if condition.operator == "equals":
            matches = (
                type(parent.value) is type(condition.value) and parent.value == condition.value
            )
        else:
            matches = isinstance(parent.value, list) and condition.value in parent.value
        if not matches:
            return False
    return True


def coverage(db: Session, session_id: str) -> CoverageResponse:
    session = intake.get_session(db, session_id)
    flow = _flow(db, session_id)
    if flow is None:
        return CoverageResponse(
            session_id=session.id,
            required=0,
            confirmed=0,
            document_supported_unconfirmed=0,
            conflicted=0,
            missing=0,
            not_applicable=0,
            fields=[],
        )
    from app.services.adaptive import engine_for

    engine = engine_for(db, session_id, flow)
    answers = _latest_answers(db, session_id)
    medication_evidence = _medication_evidence(db, session_id)
    medication_provenance = [_provenance(db, row) for row in medication_evidence]
    conflicted = _conflicted_fields(db, session_id)
    fields = []
    for _, question in flow.questions():
        is_applicable = _coverage_applicable(question, engine.answers)
        answer = answers.get(question.field)
        if not is_applicable:
            state = "NOT_APPLICABLE"
        elif question.field in conflicted:
            state = "CONFLICTED"
        elif answer is not None and _answer_envelope(answer)["status"] in (
            "answered",
            "unknown",
            "not_reported",
        ):
            state = "CONFIRMED"
        elif question.field in MEDICATION_FIELDS and medication_evidence:
            state = "DOCUMENT_SUPPORTED_UNCONFIRMED"
        else:
            state = "MISSING"
        fields.append(
            CoverageField(
                field=question.field,
                label=question.text.en,
                required=question.required,
                applicable=is_applicable,
                state=state,
                patient_answer_id=answer.id if answer else None,
                provenance=medication_provenance
                if question.field in MEDICATION_FIELDS and medication_evidence
                else [],
            )
        )
    return CoverageResponse(
        session_id=session.id,
        required=sum(item.required and item.applicable for item in fields),
        confirmed=sum(
            item.required and item.applicable and item.state == "CONFIRMED" for item in fields
        ),
        document_supported_unconfirmed=sum(
            item.state == "DOCUMENT_SUPPORTED_UNCONFIRMED" for item in fields
        ),
        conflicted=sum(item.state == "CONFLICTED" for item in fields),
        missing=sum(item.state == "MISSING" for item in fields),
        not_applicable=sum(item.state == "NOT_APPLICABLE" for item in fields),
        fields=fields,
    )


def pending_medication_confirmation(
    db: Session, session_id: str
) -> tuple[models.ClinicalEvidence, DocumentConfirmationContext] | None:
    answered_ids = {
        (row.metadata_json or {}).get("document_evidence_id")
        for row in db.scalars(
            select(models.ClinicalEvidence).where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.verification_status == "PATIENT_CONFIRMED",
            )
        )
    }
    for row in _medication_evidence(db, session_id):
        if row.id in answered_ids:
            continue
        provenance = _provenance(db, row)
        return row, DocumentConfirmationContext(
            target_field="medications.details",
            evidence_id=row.id,
            source_fact_id=row.source_id,
            source_document_id=provenance.source_document_id,
            document_filename=provenance.document_filename,
            page_number=provenance.page_number,
            bounding_box=provenance.bounding_box,
            ocr_provider=provenance.ocr_provider,
            ocr_model=provenance.ocr_model,
            original_extracted_value=provenance.original_extracted_value or "Medication mention",
            verification_state=row.verification_status,
        )
    return None


def confirmation_question_id(evidence_id: str) -> str:
    return DOCUMENT_CONFIRMATION_PREFIX + evidence_id.replace("-", "")


def demo_metrics(db: Session, session_id: str) -> DocumentAwareDemoMetrics:
    flow = _flow(db, session_id)
    if flow is None:
        baseline = 0
    else:
        from app.services.adaptive import engine_for

        baseline = len(engine_for(db, session_id, flow).applicable)
    confirmation_answers = list(
        db.scalars(
            select(models.InterviewAnswer).where(
                models.InterviewAnswer.session_id == session_id,
                models.InterviewAnswer.question_id.startswith(DOCUMENT_CONFIRMATION_PREFIX),
            )
        )
    )
    projected_answer_ids = {
        row.source_id
        for row in db.scalars(
            select(models.ClinicalEvidence).where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.verification_status == "PATIENT_CONFIRMED",
            )
        )
        if (row.metadata_json or {}).get("confirmation_answer_id")
    }
    with_context = max(0, baseline - len(projected_answer_ids)) + len(confirmation_answers)
    return DocumentAwareDemoMetrics(
        session_id=session_id,
        questions_without_document_context=baseline,
        questions_with_document_context=with_context,
        questions_avoided=max(0, baseline - with_context),
        confirmation_questions_added=len(confirmation_answers),
    )
