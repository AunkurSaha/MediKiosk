from sqlalchemy import select

from app import models
from app.services import intake


def save(db, session_id, payload, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    row = db.scalar(
        select(models.PatientRoutingLocation).where(
            models.PatientRoutingLocation.session_id == session_id
        )
    )
    if row is None:
        row = models.PatientRoutingLocation(session_id=session_id, patient_id=session.patient_id)
        db.add(row)
    else:
        row.revision += 1
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.captured_at = intake.now()
    db.flush()
    intake.audit(
        db,
        "routing_location_saved",
        session_id,
        user=user,
        metadata={"location_id": row.id, "source": row.source, "revision": row.revision},
    )
    db.commit()
    db.refresh(row)
    return row


def get(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    return db.scalar(
        select(models.PatientRoutingLocation).where(
            models.PatientRoutingLocation.session_id == session_id
        )
    )
