from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_current_auth_user
from app.core.errors import WorkflowError
from app.database import get_db
from app.services import continuity, intake

router = APIRouter()


@router.get("/{session_id}/continuity", response_model=schemas.ContinuitySnapshot)
def read_continuity(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    session = intake.get_session(db, str(session_id))
    if user.role == "triage":
        raise WorkflowError("FORBIDDEN", "Triage staff do not have continuity access.", 403)
    intake.verify_session_access(db, session, user)
    if user.role == "doctor":
        intake.require_consent(db, session.id)
    return continuity.snapshot(db, session.id)
