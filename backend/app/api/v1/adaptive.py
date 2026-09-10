from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

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
async def answer(session_id: UUID, payload: Submission, db: Session = Depends(get_db)):
    from app.services.triage_notifier import notifier

    db.info.pop("triage_events", None)
    result = await run_in_threadpool(adaptive.submit, db, str(session_id), payload)
    for event in db.info.pop("triage_events", []):
        await notifier.broadcast(event)
    return result


@router.put("/{session_id}/interview/cursor", response_model=InterviewState)
def navigate(session_id: UUID, payload: Navigation, db: Session = Depends(get_db)):
    return adaptive.navigate(db, str(session_id), payload)
