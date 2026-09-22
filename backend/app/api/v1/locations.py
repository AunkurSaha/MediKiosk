from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.schemas.patient_routing_location import (
    PatientRoutingLocationCreate,
    PatientRoutingLocationResponse,
)
from app.services import location_service

router = APIRouter()


@router.put("/{session_id}/routing-location", response_model=PatientRoutingLocationResponse)
def save_location(
    session_id: UUID,
    payload: PatientRoutingLocationCreate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return location_service.save(db, str(session_id), payload, user)


@router.get("/{session_id}/routing-location", response_model=PatientRoutingLocationResponse | None)
def get_location(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return location_service.get(db, str(session_id), user)
