from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import models
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.schemas.rapid_routing import (
    ComplaintConfirmation,
    ComplaintInput,
    RapidAnswer,
    RapidRoutingState,
)
from app.services import rapid_routing

router = APIRouter()


@router.get("/{session_id}/rapid-routing", response_model=RapidRoutingState)
def get_state(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return rapid_routing.state(db, str(session_id), user)


@router.post("/{session_id}/rapid-routing/complaint/map", response_model=RapidRoutingState)
def map_complaint(
    session_id: UUID,
    payload: ComplaintInput,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return rapid_routing.map_complaint(db, str(session_id), payload, user)


@router.put("/{session_id}/rapid-routing/complaint", response_model=RapidRoutingState)
def confirm_complaint(
    session_id: UUID,
    payload: ComplaintConfirmation,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return rapid_routing.confirm_complaint(db, str(session_id), payload, user)


@router.post("/{session_id}/rapid-routing/answers", response_model=RapidRoutingState)
async def answer(
    session_id: UUID,
    payload: RapidAnswer,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    from app.services.triage_notifier import notifier

    db.info.pop("triage_events", None)
    result = await run_in_threadpool(
        rapid_routing.submit_answer, db, str(session_id), payload, user
    )
    for event in db.info.pop("triage_events", []):
        await notifier.broadcast(event)
    return result
