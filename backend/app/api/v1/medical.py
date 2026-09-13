from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_assigned_doctor_session
from app.database import get_db
from app.schemas.medical_fact import (
    DiscrepancyResponse,
    LabFactRecord,
    LabFactReview,
    MedicalFactsResponse,
    MedicationFactRecord,
    MedicationFactReview,
    TimelineResponse,
)
from app.services import discrepancies, medical_facts, timeline

router = APIRouter()


@router.get("/{session_id}/medical-facts", response_model=MedicalFactsResponse)
def read_medical_facts(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return medical_facts.get_current_facts(db, str(session_id))


@router.get("/{session_id}/timeline", response_model=TimelineResponse)
def read_timeline(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return timeline.get_timeline(db, str(session_id))


@router.get("/{session_id}/discrepancies", response_model=DiscrepancyResponse)
def read_discrepancies(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return discrepancies.get_discrepancies(db, str(session_id))


@router.patch(
    "/{session_id}/medical-facts/medications/{fact_id}",
    response_model=MedicationFactRecord,
)
def review_medication_fact(
    session_id: UUID,
    fact_id: UUID,
    payload: MedicationFactReview,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return medical_facts.review_medication(db, str(session_id), str(fact_id), payload, user)


@router.patch(
    "/{session_id}/medical-facts/labs/{fact_id}",
    response_model=LabFactRecord,
)
def review_lab_fact(
    session_id: UUID,
    fact_id: UUID,
    payload: LabFactReview,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return medical_facts.review_lab(db, str(session_id), str(fact_id), payload, user)
