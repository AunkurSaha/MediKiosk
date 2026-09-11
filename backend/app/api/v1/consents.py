from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.put("/{session_id}/consent", response_model=schemas.Consent)
def save_consent(
    session_id: UUID,
    payload: schemas.ConsentUpdate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.save_consent(db, str(session_id), payload, user=user)
