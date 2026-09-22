from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.schemas.mediroute import FacilitySelection, MediRouteResponse
from app.schemas.session import Session as SessionSchema
from app.services import mediroute

router = APIRouter()


@router.get("/{session_id}/mediroute", response_model=MediRouteResponse)
def recommendations(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return mediroute.compute(db, str(session_id), user)


@router.put("/{session_id}/mediroute/facility", response_model=SessionSchema)
def choose_facility(
    session_id: UUID,
    payload: FacilitySelection,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return mediroute.select_facility(db, str(session_id), payload.facility_id, user)
