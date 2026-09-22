from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_patient_or_demo
from app.database import get_db
from app.schemas.doctor_matching import DoctorMatchResponse, DoctorMatchSelection
from app.services import doctor_matching

router = APIRouter()


@router.get("/{session_id}/doctor-match", response_model=DoctorMatchResponse)
def get_match(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return doctor_matching.compute(db, str(session_id), user)


@router.put("/{session_id}/doctor-match/selection", response_model=DoctorMatchResponse)
def select_match(
    session_id: UUID,
    payload: DoctorMatchSelection,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(require_patient_or_demo),
):
    return doctor_matching.select_doctor(db, str(session_id), payload.doctor_id, user)
