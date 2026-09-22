"""Central append/provenance-oriented clinical evidence operations."""

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import WorkflowError
from app.domain.clinical_safety import (
    TRUSTED_HISTORY_STATUSES,
    EvidenceSourceType,
    EvidenceVerificationStatus,
)
from app.schemas.clinical_evidence import (
    ClinicalEvidenceCreate,
    ClinicalEvidenceRead,
    EvidenceContext,
)
from app.services import intake


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_patient(db: Session, session_id: str) -> tuple[models.Session, str]:
    session = db.get(models.Session, session_id)
    if session is None:
        raise WorkflowError("NOT_FOUND", "Session not found.", 404)
    return session, session.patient_id


def _conflict_ids(db: Session, evidence_id: str) -> list[str]:
    rows = db.scalars(
        select(models.ClinicalEvidenceConflict).where(
            or_(
                models.ClinicalEvidenceConflict.evidence_a_id == evidence_id,
                models.ClinicalEvidenceConflict.evidence_b_id == evidence_id,
            )
        )
    ).all()
    return sorted(
        row.evidence_b_id if row.evidence_a_id == evidence_id else row.evidence_a_id for row in rows
    )


def read(db: Session, row: models.ClinicalEvidence) -> ClinicalEvidenceRead:
    return ClinicalEvidenceRead(
        id=row.id,
        patient_id=row.patient_id,
        session_id=row.session_id,
        concept_code=row.concept_code,
        value=row.value_json,
        source_type=row.source_type,
        source_id=row.source_id,
        stable_key=row.stable_key,
        original_text=row.original_text,
        normalized_text=row.normalized_text,
        translated_text=row.translated_text,
        language=row.language,
        confidence=row.confidence,
        verification_status=row.verification_status,
        metadata=row.metadata_json or {},
        verified_by=row.verified_by,
        verified_at=row.verified_at,
        verification_reason=row.verification_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        conflicts_with=_conflict_ids(db, row.id),
    )


def create_evidence(db: Session, payload: ClinicalEvidenceCreate) -> models.ClinicalEvidence:
    session, patient_id = _session_patient(db, payload.session_id)
    if payload.patient_id != patient_id:
        raise WorkflowError("INVALID_EVIDENCE", "Evidence patient does not match the session.", 422)
    existing = db.scalar(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.source_type == payload.source_type.value,
            models.ClinicalEvidence.source_id == payload.source_id,
            models.ClinicalEvidence.concept_code == payload.concept_code,
            models.ClinicalEvidence.stable_key == payload.stable_key,
        )
    )
    if existing is not None:
        if existing.session_id != session.id or existing.patient_id != patient_id:
            raise WorkflowError(
                "EVIDENCE_PROVENANCE_CONFLICT", "Evidence source is already bound.", 409
            )
        return existing
    row = models.ClinicalEvidence(
        patient_id=patient_id,
        session_id=session.id,
        concept_code=payload.concept_code,
        value_json=payload.value,
        source_type=payload.source_type.value,
        source_id=payload.source_id,
        stable_key=payload.stable_key,
        original_text=payload.original_text,
        normalized_text=payload.normalized_text,
        translated_text=payload.translated_text,
        language=payload.language,
        confidence=payload.confidence,
        verification_status=payload.verification_status.value,
        metadata_json=payload.metadata,
    )
    db.add(row)
    db.flush()
    return row


def create_patient_answer_evidence(
    db: Session,
    answer: models.InterviewAnswer,
    *,
    value: Any | None = None,
    answer_status: str = "answered",
    translated_text: str | None = None,
    voice_metadata: dict[str, Any] | None = None,
    relationship_metadata: dict[str, Any] | None = None,
) -> models.ClinicalEvidence:
    session, patient_id = _session_patient(db, answer.session_id)
    source_type = (
        EvidenceSourceType.PATIENT_VOICE
        if answer.source == "voice"
        else EvidenceSourceType.PATIENT_TEXT
    )
    return create_evidence(
        db,
        ClinicalEvidenceCreate(
            patient_id=patient_id,
            session_id=session.id,
            concept_code=None,
            value=value,
            source_type=source_type,
            source_id=answer.id,
            stable_key="raw_answer",
            original_text=answer.raw_value,
            translated_text=translated_text,
            language=answer.language,
            verification_status=EvidenceVerificationStatus.PATIENT_CONFIRMED,
            metadata={
                "question_id": answer.question_id,
                "canonical_field": answer.field,
                "answer_status": answer_status,
                **(relationship_metadata or {}),
                **(voice_metadata or {}),
            },
        ),
    )


def project_normalization_evidence(
    db: Session, normalization: models.NormalizationResult
) -> list[models.ClinicalEvidence]:
    answer = db.get(models.InterviewAnswer, normalization.source_answer_id)
    if answer is None:
        return []
    session, patient_id = _session_patient(db, normalization.session_id)
    result = normalization.result_json or {}
    rows = []
    for fact in result.get("facts", []):
        concept = fact.get("normalized_concept") or fact.get("concept")
        if not concept:
            continue
        rows.append(
            create_evidence(
                db,
                ClinicalEvidenceCreate(
                    patient_id=patient_id,
                    session_id=session.id,
                    concept_code=concept,
                    value=fact.get("normalized_value"),
                    source_type=(
                        EvidenceSourceType.PATIENT_VOICE
                        if answer.source == "voice"
                        else EvidenceSourceType.PATIENT_TEXT
                    ),
                    source_id=answer.id,
                    stable_key=f"normalized:{concept}",
                    original_text=answer.raw_value,
                    normalized_text=fact.get("normalized_display"),
                    language=answer.language,
                    confidence=fact.get("confidence"),
                    verification_status=EvidenceVerificationStatus.PATIENT_CONFIRMED,
                    metadata={
                        "normalization_id": normalization.id,
                        "provider": normalization.provider,
                        "provider_version": normalization.provider_version,
                        "schema_version": normalization.schema_version,
                        "policy_version": normalization.policy_version,
                        "certainty": fact.get("certainty"),
                        "polarity": fact.get("polarity", "present"),
                        "evidence": fact.get("evidence"),
                    },
                ),
            )
        )
    return rows


def create_document_evidence(
    db: Session,
    fact: models.MedicationFact | models.LabFact,
    extraction: models.DocumentExtraction,
) -> models.ClinicalEvidence:
    session, patient_id = _session_patient(db, fact.session_id)
    if isinstance(fact, models.MedicationFact):
        concept, entity_type = "MEDICATION_MENTION", "medication"
        value = {
            key: getattr(fact, key)
            for key in ("name", "dosage", "unit", "frequency", "route", "duration")
        }
    else:
        concept, entity_type = "LAB_OBSERVATION", "lab_observation"
        value = {
            key: getattr(fact, key)
            for key in ("test_name", "value", "unit", "reference_range", "flag")
        }
    return create_evidence(
        db,
        ClinicalEvidenceCreate(
            patient_id=patient_id,
            session_id=session.id,
            concept_code=concept,
            value=value,
            source_type=EvidenceSourceType.DOCUMENT,
            source_id=fact.id,
            stable_key=entity_type,
            original_text=fact.source_text or extraction.raw_text,
            confidence=extraction.confidence,
            verification_status=EvidenceVerificationStatus.UNVERIFIED,
            metadata={
                "document_id": extraction.document_id,
                "extraction_id": extraction.id,
                "entity_type": entity_type,
                "source_location": fact.source_location,
                "ocr_provider": extraction.extractor,
                "ocr_provider_version": extraction.extractor_version,
                "ocr_confidence": extraction.confidence,
            },
        ),
    )


def _rule_concept(rule_id: str) -> str:
    return "RED_FLAG_" + re.sub(r"[^A-Z0-9]+", "_", rule_id.upper()).strip("_")


def _triggering_evidence_ids(db: Session, session_id: str, facts: list[dict]) -> list[str]:
    question_ids = {item.get("question_id") for item in facts if item.get("question_id")}
    if not question_ids:
        return []
    answer_ids = db.scalars(
        select(models.InterviewAnswer.id).where(
            models.InterviewAnswer.session_id == session_id,
            models.InterviewAnswer.question_id.in_(question_ids),
        )
    ).all()
    return list(
        db.scalars(
            select(models.ClinicalEvidence.id).where(
                models.ClinicalEvidence.source_id.in_(answer_ids),
                models.ClinicalEvidence.stable_key == "raw_answer",
            )
        ).all()
    )


def create_rule_evidence(db: Session, alert: models.Alert) -> models.ClinicalEvidence:
    session, patient_id = _session_patient(db, alert.session_id)
    facts = alert.triggering_facts_json or []
    value = {"triggered": alert.status != "resolved", "priority": alert.priority}
    metadata = {
        "rule_id": alert.rule_id,
        "rule_version": alert.rule_version,
        "reason": alert.reason,
        "category": alert.category,
        "alert_status": alert.status,
        "triggering_evidence_ids": _triggering_evidence_ids(db, alert.session_id, facts),
    }
    row = create_evidence(
        db,
        ClinicalEvidenceCreate(
            patient_id=patient_id,
            session_id=session.id,
            concept_code=_rule_concept(alert.rule_id),
            value=value,
            source_type=EvidenceSourceType.DETERMINISTIC_RULE,
            source_id=alert.id,
            stable_key="rule_result",
            verification_status=EvidenceVerificationStatus.UNVERIFIED,
            metadata=metadata,
        ),
    )
    # Alerts are versioned mutable rule outcomes. Refresh only this derived
    # projection; immutable source identity and patient provenance never change.
    if row.value_json != value or row.metadata_json != metadata:
        row.value_json = value
        row.metadata_json = metadata
        row.updated_at = _now()
        db.flush()
    return row


def _filtered_query(
    *,
    session_id: str | None = None,
    patient_id: str | None = None,
    concept_code: str | None = None,
    source_type: EvidenceSourceType | None = None,
    verification_status: EvidenceVerificationStatus | None = None,
):
    stmt = select(models.ClinicalEvidence)
    if session_id:
        stmt = stmt.where(models.ClinicalEvidence.session_id == session_id)
    if patient_id:
        stmt = stmt.where(models.ClinicalEvidence.patient_id == patient_id)
    if concept_code:
        stmt = stmt.where(models.ClinicalEvidence.concept_code == concept_code)
    if source_type:
        stmt = stmt.where(models.ClinicalEvidence.source_type == source_type.value)
    if verification_status:
        stmt = stmt.where(models.ClinicalEvidence.verification_status == verification_status.value)
    return stmt.order_by(models.ClinicalEvidence.created_at, models.ClinicalEvidence.id)


def list_for_encounter(db: Session, session_id: str, **filters) -> list[models.ClinicalEvidence]:
    _session_patient(db, session_id)
    return list(db.scalars(_filtered_query(session_id=session_id, **filters)).all())


def list_for_patient(db: Session, patient_id: str, **filters) -> list[models.ClinicalEvidence]:
    if db.get(models.Patient, patient_id) is None:
        raise WorkflowError("NOT_FOUND", "Patient not found.", 404)
    return list(db.scalars(_filtered_query(patient_id=patient_id, **filters)).all())


def get_by_concept(db: Session, session_id: str, concept_code: str):
    return list_for_encounter(db, session_id, concept_code=concept_code)


def get_previous_verified_evidence(
    db: Session, patient_id: str, excluding_current_encounter: str
) -> list[models.ClinicalEvidence]:
    return list(
        db.scalars(
            select(models.ClinicalEvidence)
            .where(
                models.ClinicalEvidence.patient_id == patient_id,
                models.ClinicalEvidence.session_id != excluding_current_encounter,
                models.ClinicalEvidence.verification_status.in_(
                    [status.value for status in TRUSTED_HISTORY_STATUSES]
                ),
            )
            .order_by(models.ClinicalEvidence.created_at.desc(), models.ClinicalEvidence.id)
        ).all()
    )


def get_verified_context(db: Session, session_id: str) -> EvidenceContext:
    rows = list_for_encounter(db, session_id)
    converted = [(row, read(db, row)) for row in rows]
    return EvidenceContext(
        verified=[
            item for row, item in converted if row.verification_status == "CLINICIAN_VERIFIED"
        ],
        patient_confirmed=[
            item for row, item in converted if row.verification_status == "PATIENT_CONFIRMED"
        ],
        unverified_documents=[
            item
            for row, item in converted
            if row.source_type == "DOCUMENT" and row.verification_status == "UNVERIFIED"
        ],
        deterministic_rules=[
            item for row, item in converted if row.source_type == "DETERMINISTIC_RULE"
        ],
        conflicting=[item for row, item in converted if row.verification_status == "CONFLICTING"],
    )


def _transition(
    db: Session,
    evidence_id: str,
    status: EvidenceVerificationStatus,
    user: models.User,
    reason: str | None,
) -> models.ClinicalEvidence:
    row = db.scalar(
        select(models.ClinicalEvidence)
        .where(models.ClinicalEvidence.id == evidence_id)
        .with_for_update()
    )
    if row is None:
        raise WorkflowError("EVIDENCE_NOT_FOUND", "Clinical evidence not found.", 404)
    old_status = row.verification_status
    row.verification_status = status.value
    row.verified_by = user.id
    row.verified_at = _now()
    row.verification_reason = reason
    row.updated_at = row.verified_at
    intake.audit(
        db,
        "clinical_evidence_verification_changed",
        row.session_id,
        user=user,
        metadata={
            "evidence_id": row.id,
            "old_status": old_status,
            "new_status": status.value,
            "reason": reason,
        },
    )
    db.flush()
    return row


def verify(db: Session, evidence_id: str, user: models.User, reason: str | None = None):
    return _transition(db, evidence_id, EvidenceVerificationStatus.CLINICIAN_VERIFIED, user, reason)


def reject(db: Session, evidence_id: str, user: models.User, reason: str | None = None):
    return _transition(db, evidence_id, EvidenceVerificationStatus.REJECTED, user, reason)


def mark_conflicting(
    db: Session,
    evidence_id: str,
    other_evidence_id: str,
    user: models.User,
    reason: str,
) -> tuple[models.ClinicalEvidence, models.ClinicalEvidence]:
    if evidence_id == other_evidence_id:
        raise WorkflowError("INVALID_CONFLICT", "Evidence cannot conflict with itself.", 422)
    rows = [db.get(models.ClinicalEvidence, item) for item in (evidence_id, other_evidence_id)]
    if any(row is None for row in rows):
        raise WorkflowError("EVIDENCE_NOT_FOUND", "Clinical evidence not found.", 404)
    left, right = rows
    if left.patient_id != right.patient_id:
        raise WorkflowError(
            "INVALID_CONFLICT", "Conflicting evidence must belong to one patient.", 422
        )
    a_id, b_id = sorted((left.id, right.id))
    conflict = db.scalar(
        select(models.ClinicalEvidenceConflict).where(
            models.ClinicalEvidenceConflict.evidence_a_id == a_id,
            models.ClinicalEvidenceConflict.evidence_b_id == b_id,
        )
    )
    if conflict is None:
        db.add(
            models.ClinicalEvidenceConflict(
                evidence_a_id=a_id,
                evidence_b_id=b_id,
                reason=reason,
                created_by=user.id,
            )
        )
    for row in (left, right):
        _transition(db, row.id, EvidenceVerificationStatus.CONFLICTING, user, reason)
    return left, right


def apply_source_verification(
    db: Session, source_id: str, status: str, user: models.User, reason: str | None
) -> None:
    mapped = {
        "verified": EvidenceVerificationStatus.CLINICIAN_VERIFIED,
        "rejected": EvidenceVerificationStatus.REJECTED,
    }.get(status)
    if mapped is None:
        return
    rows = db.scalars(
        select(models.ClinicalEvidence).where(models.ClinicalEvidence.source_id == source_id)
    ).all()
    for row in rows:
        _transition(db, row.id, mapped, user, reason)
