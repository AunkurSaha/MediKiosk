from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import WorkflowError
from app.schemas.field_verification import (
    FieldVerificationList,
    FieldVerificationRecord,
    FieldVerificationRequest,
    FieldVerificationRevisionRecord,
)
from app.services import intake


def get_verifications(db: Session, session_id: str) -> FieldVerificationList:
    # Ensure session exists
    intake.get_session(db, session_id)

    rows = db.scalars(
        select(models.FieldVerification)
        .where(models.FieldVerification.session_id == session_id)
        .order_by(models.FieldVerification.created_at.asc())
    ).all()

    items: list[FieldVerificationRecord] = []
    for r in rows:
        revisions = [
            FieldVerificationRevisionRecord.model_validate(rev)
            for rev in r.revisions
        ]
        record = FieldVerificationRecord(
            id=r.id,
            session_id=r.session_id,
            field_type=r.field_type,
            field_id=r.field_id,
            status=r.status,
            verified_by=r.verified_by,
            verified_at=r.verified_at,
            notes=r.notes,
            version=r.version,
            created_at=r.created_at,
            updated_at=r.updated_at,
            revisions=revisions,
        )
        items.append(record)

    return FieldVerificationList(items=items)


def verify_field(
    db: Session,
    session_id: str,
    request: FieldVerificationRequest,
    user: models.User,
) -> FieldVerificationRecord:
    session = intake.get_session(db, session_id)
    if session.status == "cancelled":
        raise WorkflowError("SESSION_CANCELLED", "Cannot modify cancelled session.", 409)

    now = datetime.now(timezone.utc)

    # Find existing record
    existing = db.scalar(
        select(models.FieldVerification)
        .where(
            models.FieldVerification.session_id == session_id,
            models.FieldVerification.field_type == request.field_type,
            models.FieldVerification.field_id == request.field_id,
        )
        .with_for_update()
    )

    if existing:
        if request.expected_version is not None and existing.version != request.expected_version:
            raise WorkflowError(
                "CONFLICT",
                f"Version conflict. Expected {request.expected_version}, but found {existing.version}.",
                409,
            )
        new_version = existing.version + 1
        existing.status = request.status
        existing.verified_by = user.id
        existing.verified_at = now
        existing.notes = request.notes
        existing.version = new_version
        target_record = existing
    else:
        new_version = 1
        target_record = models.FieldVerification(
            session_id=session_id,
            field_type=request.field_type,
            field_id=request.field_id,
            status=request.status,
            verified_by=user.id,
            verified_at=now,
            notes=request.notes,
            version=new_version,
        )
        db.add(target_record)
        db.flush()

    # Add append-only revision
    rev = models.FieldVerificationRevision(
        verification_id=target_record.id,
        session_id=session_id,
        version=new_version,
        status=request.status,
        actor_user_id=user.id,
        notes=request.notes,
        created_at=now,
    )
    db.add(rev)

    # If field is an interview answer, keep interview_answers.verification_status aligned
    if request.field_type == "interview_answer":
        ans = db.scalar(
            select(models.InterviewAnswer)
            .where(
                models.InterviewAnswer.session_id == session_id,
                models.InterviewAnswer.id == request.field_id,
            )
            .with_for_update()
        )
        if ans:
            if request.status == "verified":
                ans.verification_status = "clinician_verified"
            elif request.status == "flagged":
                ans.verification_status = "flagged"
            else:
                ans.verification_status = "patient_reported"

    # Audit log
    intake.audit(
        db,
        "field_verified",
        session_id,
        user,
        {
            "field_type": request.field_type,
            "field_id": request.field_id,
            "status": request.status,
            "version": new_version,
        },
    )

    db.commit()
    db.refresh(target_record)

    revisions = [
        FieldVerificationRevisionRecord.model_validate(r)
        for r in target_record.revisions
    ]
    return FieldVerificationRecord(
        id=target_record.id,
        session_id=target_record.session_id,
        field_type=target_record.field_type,
        field_id=target_record.field_id,
        status=target_record.status,
        verified_by=target_record.verified_by,
        verified_at=target_record.verified_at,
        notes=target_record.notes,
        version=target_record.version,
        created_at=target_record.created_at,
        updated_at=target_record.updated_at,
        revisions=revisions,
    )
