from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.adaptive import InterviewState, Navigation, Selection, Submission
from app.services import adaptive

router = APIRouter()


@router.get("/{session_id}/interview", response_model=InterviewState)
def get_state(session_id: UUID, db: Session = Depends(get_db)):
    return adaptive.state(db, str(session_id))


@router.put("/{session_id}/interview/flow", response_model=InterviewState)
def select_flow(session_id: UUID, payload: Selection, db: Session = Depends(get_db)):
    return adaptive.select_flow(db, str(session_id), payload)


@router.post("/{session_id}/interview/answers", response_model=InterviewState)
def answer(session_id: UUID, payload: Submission, db: Session = Depends(get_db)):
    return adaptive.submit(db, str(session_id), payload)


@router.put("/{session_id}/interview/cursor", response_model=InterviewState)
def navigate(session_id: UUID, payload: Navigation, db: Session = Depends(get_db)):
    return adaptive.navigate(db, str(session_id), payload)
