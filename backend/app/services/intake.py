import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.errors import WorkflowError

FIELDS = ("chief_complaint", "onset_duration", "medications", "allergies", "past_history")
LABELS = ("Chief complaint", "Onset / duration", "Current medications", "Allergies", "Past history")


def now():
    return datetime.now(timezone.utc)


def audit(db, action, entity_id, user=None, metadata=None):
    db.add(
        models.AuditLog(
            actor_user_id=user.id if user else None,
            actor_type="doctor" if user else "patient",
            action=action,
            entity_type="session",
            entity_id=entity_id,
            metadata_json=metadata or {},
        )
    )


def get_session(db: Session, session_id: str):
    session = db.scalar(
        select(models.Session).where(models.Session.id == session_id).with_for_update()
    )
    if session is None:
        raise WorkflowError("NOT_FOUND", "Session not found.", 404)
    return session


def consent_for(db, session_id):
    return db.scalar(select(models.Consent).where(models.Consent.session_id == session_id))


def require_consent(db, session_id):
    consent = consent_for(db, session_id)
    if consent is None or not consent.share_with_doctor:
        raise WorkflowError("CONSENT_REQUIRED", "Consent is required before clinical intake.", 403)


def answer_response(answer):
    stored = json.loads(answer.value_json)
    envelope = (
        stored
        if isinstance(stored, dict) and "status" in stored
        else {
            "status": "answered",
            "value": stored,
        }
    )
    return schemas.InterviewAnswer(
        id=answer.id,
        session_id=answer.session_id,
        question_id=answer.question_id,
        field=answer.field,
        value=envelope["value"],
        status=envelope["status"],
        raw_value=answer.raw_value,
        source=answer.source,
        language=answer.language,
        verification_status=answer.verification_status,
        created_at=answer.created_at,
        updated_at=answer.updated_at,
    )


def latest_answers(db, session_id):
    from app.services import adaptive

    if db.get(models.InterviewRun, session_id):
        flow, run = adaptive.flow_for(db, session_id)
        active = adaptive.engine_for(db, session_id, flow).active
        by_id = {row.id: row for row in adaptive.rows(db, session_id)}
        return [answer_response(by_id[fact.answer_id]) for fact in active.values()]
    rows = db.scalars(
        select(models.InterviewAnswer)
        .where(models.InterviewAnswer.session_id == session_id)
        .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
    ).all()
    latest = {row.field: row for row in rows}
    return [answer_response(latest[field]) for field in FIELDS if field in latest]


def summary_for(db, session_id):
    return db.scalar(
        select(models.ClinicalSummary).where(models.ClinicalSummary.session_id == session_id)
    )


def detail(db, session_id, doctor=False):
    from app.services import adaptive, red_flags

    session = get_session(db, session_id)
    if doctor:
        require_consent(db, session_id)
    patient = db.get(models.Patient, session.patient_id)
    alerts = red_flags.get_session_alerts(db, session_id) if doctor else []
    alert_items = [
        schemas.AlertItem(
            id=a.id,
            session_id=a.session_id,
            rule_id=a.rule_id,
            rule_version=a.rule_version,
            priority=a.priority,
            category=a.category,
            reason=a.reason,
            triggering_facts=[
                schemas.TriggeringFact.model_validate(tf) if isinstance(tf, dict) else tf
                for tf in (a.triggering_facts_json or [])
            ],
            status=a.status,
            revision=a.revision,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
            acknowledgement_note=a.acknowledgement_note,
            created_at=a.created_at,
            updated_at=a.updated_at,
            hospital_token=session.hospital_token,
            patient_name=patient.name if patient else None,
        )
        for a in alerts
    ]
    from app.services import document_service
    docs = document_service.get_session_documents(db, session_id) if doctor else []
    doc_items = [
        schemas.DocumentResponse(
            id=d.id,
            session_id=d.session_id,
            object_key=d.object_key,
            original_filename=d.original_filename,
            media_type=d.media_type,
            file_size_bytes=d.file_size_bytes,
            sha256_hash=d.sha256_hash,
            document_type=d.document_type,
            document_date=d.document_date,
            processing_status=d.processing_status,
            created_at=d.created_at,
            updated_at=d.updated_at,
            extractions=[
                schemas.DocumentExtractionResponse(
                    id=e.id,
                    document_id=e.document_id,
                    session_id=e.session_id,
                    extractor=e.extractor,
                    extractor_version=e.extractor_version,
                    raw_text=e.raw_text,
                    structured_json=e.structured_json,
                    confidence=e.confidence,
                    verification_status=e.verification_status,
                    review_version=e.review_version,
                    verified_by=e.verified_by,
                    verified_at=e.verified_at,
                    verification_notes=e.verification_notes,
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                )
                for e in d.extractions
            ],
        )
        for d in docs
    ]
    return schemas.SessionDetail(
        session=schemas.Session.model_validate(session),
        patient=schemas.Patient.model_validate(patient),
        consent=consent_for(db, session_id),
        answers=latest_answers(db, session_id),
        summary=summary_for(db, session_id),
        history=adaptive.history(db, session_id),
        alerts=alert_items,
        documents=doc_items,
    )



def create_session(db, payload):
    session_id = str(payload.id)
    existing = db.get(models.Session, session_id)
    if existing:
        patient = db.get(models.Patient, existing.patient_id)
        if (
            existing.hospital_token != payload.hospital_token
            or existing.language != payload.language
            or patient.name != payload.patient.name
            or patient.demo_abha_id != payload.patient.demo_abha_id
        ):
            raise WorkflowError("ID_CONFLICT", "This intake ID is already in use.")
        return existing
    patient = models.Patient(**payload.patient.model_dump())
    db.add(patient)
    db.flush()
    session = models.Session(
        id=session_id,
        patient_id=patient.id,
        hospital_token=payload.hospital_token,
        language=payload.language,
        status="intake",
    )
    db.add(session)
    audit(db, "session_created", session_id)
    db.commit()
    db.refresh(session)
    return session


def save_consent(db, session_id, payload):
    session = get_session(db, session_id)
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "This intake is no longer editable.")
    consent = consent_for(db, session_id)
    if consent is None:
        consent = models.Consent(session_id=session_id)
        db.add(consent)
    for key, value in payload.model_dump().items():
        setattr(consent, key, value)
    consent.recorded_at = now()
    audit(
        db,
        "consent_recorded",
        session_id,
        metadata={"share_with_doctor": payload.share_with_doctor, "text_version": 1},
    )
    db.commit()
    db.refresh(consent)
    return consent


def save_answer(db, session_id, payload):
    session = get_session(db, session_id)
    require_consent(db, session_id)
    if db.get(models.InterviewRun, session_id):
        raise WorkflowError("ADAPTIVE_API_REQUIRED", "Use the versioned interview answer endpoint.")
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "Completed answers cannot be changed.")
    if payload.field != payload.question_id or payload.language != session.language:
        raise WorkflowError("INVALID_ANSWER", "Answer field or language does not match.", 422)
    # Phase 1 has no normalization provider: raw and structured text must agree.
    if payload.raw_value != payload.value:
        raise WorkflowError("INVALID_ANSWER", "Raw and structured answers must agree.", 422)
    current = next((a for a in latest_answers(db, session_id) if a.field == payload.field), None)
    if current and current.value == payload.value and current.source == payload.source:
        return current
    answer = models.InterviewAnswer(
        session_id=session_id,
        question_id=payload.question_id,
        field=payload.field,
        value_json=json.dumps(payload.value, ensure_ascii=False),
        raw_value=payload.raw_value,
        source=payload.source,
        language=payload.language,
        verification_status="patient_reported",
        created_at=now(),
        updated_at=now(),
    )
    db.add(answer)
    # Corrections append a new answer; the earlier patient wording is retained.
    session.updated_at = now()
    audit(db, "answer_recorded", session_id, metadata={"field": payload.field})
    db.flush()
    from app.services import normalization
    from app.services.flow_registry import registry

    legacy_flow = registry()["legacy.intake"]
    question = next(q for _, q in legacy_flow.questions() if q.question_id == answer.question_id)
    db.commit()
    normalization.persist_committed(db, answer, question, legacy_flow)
    db.refresh(answer)
    return answer_response(answer)


def complete(db, session_id):
    session = get_session(db, session_id)
    require_consent(db, session_id)
    if session.status in ("ready_for_review", "under_review", "confirmed"):
        return session
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "This session cannot be completed.")
    from app.services import adaptive
    from app.services.interview_engine import draft_from_history

    history = adaptive.history(db, session_id)
    if db.get(models.InterviewRun, session_id):
        if not adaptive.state(db, session_id).is_complete:
            raise WorkflowError("ANSWERS_REQUIRED", "Address all applicable questions first.", 422)
        draft = draft_from_history(history)
    else:
        answers = {a.field: a.value for a in latest_answers(db, session_id)}
        if any(field not in answers for field in FIELDS):
            raise WorkflowError(
                "ANSWERS_REQUIRED", "Complete all five history questions first.", 422
            )
        draft = "\n".join(
            f"{label} — Patient reported: {answers[field]}" for field, label in zip(FIELDS, LABELS)
        )
    db.add(
        models.ClinicalSummary(
            session_id=session_id,
            generated_text=draft,
            generated_structured_json=history.model_dump_json() if history else None,
            status="generated",
            generated_at=now(),
            version=1,
        )
    )
    session.status = "ready_for_review"
    session.completed_at = now()
    audit(db, "intake_completed", session_id)
    db.commit()
    db.refresh(session)
    return session


def review_summary(db, session_id, payload, user, confirm=False):
    session = get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")
    if confirm and summary.status == "confirmed" and payload.expected_version == summary.version:
        return summary
    if summary.status == "confirmed":
        raise WorkflowError("CONFIRMED_IMMUTABLE", "The confirmed record is read-only.")
    if summary.version != payload.expected_version:
        raise WorkflowError("VERSION_CONFLICT", "Another edit was saved. Reload the record.")
    if confirm:
        if summary.status != "reviewed" or not summary.reviewed_text:
            raise WorkflowError("REVIEW_REQUIRED", "Save the reviewed summary before confirming.")
        summary.status = "confirmed"
        summary.confirmed_by = user.id
        summary.confirmed_at = now()
        session.status = "confirmed"
        audit(db, "summary_confirmed", session_id, user, {"version": summary.version})
    else:
        summary.version += 1
        summary.reviewed_text = payload.reviewed_text
        summary.status = "reviewed"
        summary.reviewed_by = user.id
        summary.reviewed_at = now()
        session.status = "under_review"
        db.add(
            models.SummaryRevision(
                summary_id=summary.id,
                version=summary.version,
                reviewed_text=summary.reviewed_text,
                actor_user_id=user.id,
            )
        )
        audit(db, "summary_reviewed", session_id, user, {"version": summary.version})
    db.commit()
    db.refresh(summary)
    return summary
