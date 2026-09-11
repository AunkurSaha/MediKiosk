from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.post("/{session_id}/answers", response_model=schemas.InterviewAnswer)
def create_answer(
    session_id: UUID,
    payload: schemas.InterviewAnswerCreate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.save_answer(db, str(session_id), payload, user=user)


@router.get("/{session_id}/answers", response_model=list[schemas.InterviewAnswer])
def read_answers(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, str(session_id))
    return intake.latest_answers(db, str(session_id))
