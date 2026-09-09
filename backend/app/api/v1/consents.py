from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.put("/{session_id}/consent", response_model=schemas.Consent)
def save_consent(session_id: UUID, payload: schemas.ConsentUpdate, db: Session = Depends(get_db)):
    return intake.save_consent(db, str(session_id), payload)
