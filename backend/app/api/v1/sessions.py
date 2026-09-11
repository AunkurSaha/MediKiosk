from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.post("", response_model=schemas.Session, status_code=201)
def create_session(
    payload: schemas.SessionCreate,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.create_session(db, payload, user=user)


@router.get("/{session_id}", response_model=schemas.SessionDetail)
def read_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.detail(db, str(session_id), user=user)


@router.post("/{session_id}/complete", response_model=schemas.Session)
def complete_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return intake.complete(db, str(session_id), user=user)


@router.post("/verify-abha", response_model=schemas.ABDMVerificationResponse)
def verify_standalone_abha(req: schemas.ABDMVerifyRequest):
    from app.services.abdm import ABDMService

    return ABDMService.verify_standalone_abha(req.abha_input, auth_method=req.auth_method)
