from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_optional_auth_user, require_patient_or_demo
from app.database import get_db
from app.services import doctor_routing, intake

router = APIRouter()


@router.put("/{session_id}/hospital", response_model=schemas.Session)
def choose_hospital(
    session_id: UUID,
    payload: schemas.HospitalSelection,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return doctor_routing.select_hospital(db, str(session_id), payload.hospital_id, user)


@router.get("/{session_id}/doctors", response_model=schemas.DoctorMatches)
def matched_doctors(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return doctor_routing.matches_for_session(db, str(session_id), user)


@router.put("/{session_id}/doctor", response_model=schemas.DoctorAssignment)
def choose_doctor(
    session_id: UUID,
    payload: schemas.DoctorSelection,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return doctor_routing.select_doctor(db, str(session_id), payload.doctor_id, user)


@router.post("", response_model=schemas.Session, status_code=201)
def create_session(
    payload: schemas.SessionCreate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.create_session(db, payload, user=user)


@router.get("/{session_id}", response_model=schemas.SessionDetail)
def read_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.detail(db, str(session_id), user=user)


@router.put("/{session_id}/journey-mode", response_model=schemas.Session)
def choose_journey_mode(
    session_id: UUID,
    payload: schemas.JourneyModeUpdate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return intake.update_journey_mode(db, str(session_id), payload.journey_mode, user=user)


@router.post("/{session_id}/complete", response_model=schemas.Session)
def complete_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.complete(db, str(session_id), user=user)


@router.get("/{session_id}/queue-estimate", response_model=schemas.PatientQueueEstimate)
def read_patient_queue_estimate(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return doctor_routing.patient_queue_estimate(db, str(session_id), user)


@router.post("/verify-abha", response_model=schemas.ABDMVerificationResponse)
def verify_standalone_abha(req: schemas.ABDMVerifyRequest):
    from app.services.abdm import ABDMService

    return ABDMService.verify_standalone_abha(req.abha_input, auth_method=req.auth_method)
