from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_optional_auth_user, require_patient
from app.database import get_db
from app.services import pre_arrival_packet

router = APIRouter()
handoff_router = APIRouter()


@router.post("/{session_id}/packet", response_model=schemas.PacketMetadata)
def create_packet(
    session_id: UUID, db: Session = Depends(get_db), user: models.User = Depends(require_patient)
):
    return pre_arrival_packet.get_or_create(db, str(session_id), user)


@router.get("/{session_id}/packet", response_model=schemas.PacketView)
def packet_metadata(
    session_id: UUID, db: Session = Depends(get_db), user: models.User = Depends(require_patient)
):
    return pre_arrival_packet.get_packet(db, str(session_id), user)


@router.post("/{session_id}/packet/handoff-token", response_model=schemas.HandoffTokenIssued)
def issue_handoff_token(
    session_id: UUID, db: Session = Depends(get_db), user: models.User = Depends(require_patient)
):
    return pre_arrival_packet.issue_token(db, str(session_id), user)


@router.post("/{session_id}/packet/revoke", response_model=schemas.PacketMetadata)
def revoke_packet(
    session_id: UUID, db: Session = Depends(get_db), user: models.User = Depends(require_patient)
):
    return pre_arrival_packet.revoke(db, str(session_id), user)


@handoff_router.get("/{token}", response_model=schemas.HandoffResolution | schemas.PacketView)
def resolve_handoff(
    token: str,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return pre_arrival_packet.resolve(db, token, user)
