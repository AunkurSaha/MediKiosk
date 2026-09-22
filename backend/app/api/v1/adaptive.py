from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import models
from app.api.deps import get_optional_auth_user
from app.database import get_db
from app.schemas.adaptive import InterviewState, Navigation, Selection, Submission
from app.schemas.coverage import CoverageResponse, DocumentAwareDemoMetrics
from app.services import adaptive, clinical_coverage, intake

router = APIRouter()


@router.get("/{session_id}/coverage", response_model=CoverageResponse)
def get_coverage(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, str(session_id))
    return clinical_coverage.coverage(db, str(session_id))


@router.get("/{session_id}/coverage/demo-metrics", response_model=DocumentAwareDemoMetrics)
def get_document_aware_demo_metrics(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    from app.core.config import demo_enabled
    from app.core.errors import WorkflowError

    if not demo_enabled():
        raise WorkflowError("FORBIDDEN", "Demo evaluation metrics are disabled.", 403)
    session = intake.get_session(db, str(session_id))
    intake.verify_session_access(db, session, user)
    return clinical_coverage.demo_metrics(db, str(session_id))


@router.get("/{session_id}/interview", response_model=InterviewState)
def get_state(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return adaptive.state(db, str(session_id), user=user)


@router.put("/{session_id}/interview/flow", response_model=InterviewState)
def select_flow(
    session_id: UUID,
    payload: Selection,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return adaptive.select_flow(db, str(session_id), payload, user=user)


@router.post("/{session_id}/interview/answers", response_model=InterviewState)
async def answer(
    session_id: UUID,
    payload: Submission,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    from app.services.triage_notifier import notifier

    db.info.pop("triage_events", None)
    result = await run_in_threadpool(adaptive.submit, db, str(session_id), payload, user=user)
    for event in db.info.pop("triage_events", []):
        await notifier.broadcast(event)
    return result


@router.put("/{session_id}/interview/cursor", response_model=InterviewState)
def navigate(
    session_id: UUID,
    payload: Navigation,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_auth_user),
):
    return adaptive.navigate(db, str(session_id), payload, user=user)
