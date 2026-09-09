from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.post("", response_model=schemas.Session, status_code=201)
def create_session(payload: schemas.SessionCreate, db: Session = Depends(get_db)):
    return intake.create_session(db, payload)


@router.get("/{session_id}", response_model=schemas.SessionDetail)
def read_session(session_id: UUID, db: Session = Depends(get_db)):
    return intake.detail(db, str(session_id))


@router.post("/{session_id}/complete", response_model=schemas.Session)
def complete_session(session_id: UUID, db: Session = Depends(get_db)):
    return intake.complete(db, str(session_id))
