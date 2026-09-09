from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.post("/{session_id}/answers", response_model=schemas.InterviewAnswer)
def create_answer(
    session_id: UUID,
    payload: schemas.InterviewAnswerCreate,
    db: Session = Depends(get_db),
):
    return intake.save_answer(db, str(session_id), payload)


@router.get("/{session_id}/answers", response_model=list[schemas.InterviewAnswer])
def read_answers(session_id: UUID, db: Session = Depends(get_db)):
    intake.get_session(db, str(session_id))
    intake.require_consent(db, str(session_id))
    return intake.latest_answers(db, str(session_id))
