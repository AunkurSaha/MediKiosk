from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_auth_user, require_doctor
from app.core.errors import WorkflowError
from app.database import get_db
from app.domain.clinical_safety import EvidenceSourceType, EvidenceVerificationStatus
from app.schemas.clinical_evidence import (
    ClinicalEvidenceList,
    ClinicalEvidenceRead,
    EvidenceConflictCreate,
    EvidenceContext,
    EvidenceVerificationUpdate,
)
from app.services import clinical_evidence, intake

router = APIRouter()


def _authorized_session(db: Session, session_id: str, user: models.User) -> models.Session:
    session = intake.get_session(db, session_id)
    # Longitudinal evidence requires explicit ownership; the legacy anonymous
    # demo-session exception is not appropriate for authenticated patients.
    if user.role == "patient" and session.user_id != user.id:
        raise WorkflowError(
            "FORBIDDEN", "You do not have permission to access this clinical evidence.", 403
        )
    intake.verify_session_access(db, session, user)
    if user.role == "doctor":
        intake.require_consent(db, session_id)
    return session


def _filters(concept_code, source_type, verification_status):
    return {
        "concept_code": concept_code,
        "source_type": source_type,
        "verification_status": verification_status,
    }


@router.get("/encounters/{session_id}", response_model=ClinicalEvidenceList)
def encounter_evidence(
    session_id: str,
    concept_code: str | None = Query(default=None),
    source_type: EvidenceSourceType | None = Query(default=None),
    verification_status: EvidenceVerificationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    _authorized_session(db, session_id, user)
    rows = clinical_evidence.list_for_encounter(
        db, session_id, **_filters(concept_code, source_type, verification_status)
    )
    return ClinicalEvidenceList(items=[clinical_evidence.read(db, row) for row in rows])


@router.get("/encounters/{session_id}/context", response_model=EvidenceContext)
def encounter_context(
    session_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    _authorized_session(db, session_id, user)
    return clinical_evidence.get_verified_context(db, session_id)


@router.get("/patients/{patient_id}", response_model=ClinicalEvidenceList)
def patient_evidence(
    patient_id: str,
    concept_code: str | None = Query(default=None),
    source_type: EvidenceSourceType | None = Query(default=None),
    verification_status: EvidenceVerificationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    sessions = db.scalars(
        select(models.Session).where(models.Session.patient_id == patient_id)
    ).all()
    if not sessions:
        raise WorkflowError("NOT_FOUND", "Patient not found.", 404)
    for session in sessions:
        _authorized_session(db, session.id, user)
    rows = clinical_evidence.list_for_patient(
        db, patient_id, **_filters(concept_code, source_type, verification_status)
    )
    return ClinicalEvidenceList(items=[clinical_evidence.read(db, row) for row in rows])


@router.get("/{evidence_id}", response_model=ClinicalEvidenceRead)
def evidence_detail(
    evidence_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    row = db.get(models.ClinicalEvidence, evidence_id)
    if row is None:
        raise WorkflowError("EVIDENCE_NOT_FOUND", "Clinical evidence not found.", 404)
    _authorized_session(db, row.session_id, user)
    return clinical_evidence.read(db, row)


def _doctor_evidence(db: Session, session_id: str, evidence_id: str, user: models.User):
    _authorized_session(db, session_id, user)
    row = db.get(models.ClinicalEvidence, evidence_id)
    if row is None or row.session_id != session_id:
        raise WorkflowError("EVIDENCE_NOT_FOUND", "Clinical evidence not found.", 404)
    return row


@router.post(
    "/doctor/encounters/{session_id}/{evidence_id}/verify", response_model=ClinicalEvidenceRead
)
def verify_evidence(
    session_id: str,
    evidence_id: str,
    payload: EvidenceVerificationUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_doctor),
):
    _doctor_evidence(db, session_id, evidence_id, user)
    row = clinical_evidence.verify(db, evidence_id, user, payload.reason)
    db.commit()
    db.refresh(row)
    return clinical_evidence.read(db, row)


@router.post(
    "/doctor/encounters/{session_id}/{evidence_id}/reject", response_model=ClinicalEvidenceRead
)
def reject_evidence(
    session_id: str,
    evidence_id: str,
    payload: EvidenceVerificationUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_doctor),
):
    _doctor_evidence(db, session_id, evidence_id, user)
    row = clinical_evidence.reject(db, evidence_id, user, payload.reason)
    db.commit()
    db.refresh(row)
    return clinical_evidence.read(db, row)


@router.post(
    "/doctor/encounters/{session_id}/{evidence_id}/conflicts", response_model=ClinicalEvidenceRead
)
def conflict_evidence(
    session_id: str,
    evidence_id: str,
    payload: EvidenceConflictCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_doctor),
):
    _doctor_evidence(db, session_id, evidence_id, user)
    other = _doctor_evidence(db, session_id, payload.other_evidence_id, user)
    row, _ = clinical_evidence.mark_conflicting(db, evidence_id, other.id, user, payload.reason)
    db.commit()
    db.refresh(row)
    return clinical_evidence.read(db, row)
