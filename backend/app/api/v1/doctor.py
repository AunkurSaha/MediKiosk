from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_current_user
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.get("/sessions", response_model=schemas.SessionList)
def read_doctor_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows = db.execute(
        select(models.Session, models.Patient.name)
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .join(models.Consent, models.Consent.session_id == models.Session.id)
        .where(
            models.Consent.share_with_doctor.is_(True),
            models.Session.status.in_(["ready_for_review", "under_review", "confirmed"]),
        )
        .order_by(models.Session.created_at.desc(), models.Session.id)
    ).all()
    return schemas.SessionList(
        items=[
            schemas.SessionListItem(
                **schemas.Session.model_validate(s).model_dump(), patient_name=name
            )
            for s, name in rows
        ]
    )


@router.get("/sessions/{session_id}", response_model=schemas.SessionDetail)
def read_session_detail(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    result = intake.detail(db, str(session_id), doctor=True)
    intake.audit(db, "session_viewed", str(session_id), user)
    db.commit()
    return result


@router.put("/sessions/{session_id}/summary", response_model=schemas.ClinicalSummary)
def update_summary(
    session_id: UUID,
    payload: schemas.ClinicalSummaryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.review_summary(db, str(session_id), payload, user)


@router.post("/sessions/{session_id}/summary/confirm", response_model=schemas.ClinicalSummary)
def confirm_summary(
    session_id: UUID,
    payload: schemas.SummaryConfirm,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.review_summary(db, str(session_id), payload, user, confirm=True)
