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


def verify_session_access(db: Session, session: models.Session, user: models.User | None) -> None:
    """Enforce server-side authorization on clinical intake session.

    - Doctor role: permitted (doctor endpoints verify clinical consent separately).
    - Patient role:
      - If session has an owner (session.user_id), it MUST match user.id.
        If it belongs to a different user -> 403 FORBIDDEN.
      - If session has no owner (legacy demo session) and demo_enabled(), access is permitted.
    - Unauthenticated (user is None):
      - If session has an owner (session.user_id is not None) -> 401 AUTH_REQUIRED.
      - If session has no owner (legacy demo session) and demo_enabled() -> access is permitted.
      - Otherwise -> 401 AUTH_REQUIRED.
    """
    from app.core.config import demo_enabled

    if user and user.role == "doctor":
        # Historical anonymous showcase fixtures predate visit assignment. Keep
        # them usable only in explicit demo mode; every owned patient session is
        # subject to strict selected-doctor and hospital isolation below.
        if demo_enabled() and session.user_id is None and session.selected_doctor_id is None:
            return
        from app.services.doctor_routing import require_assigned_doctor

        require_assigned_doctor(db, session, user)
        return

    if user and user.role == "patient":
        if session.user_id and session.user_id != user.id:
            raise WorkflowError(
                "FORBIDDEN", "You do not have permission to access this intake session.", 403
            )
        return

    if user and user.role == "triage":
        raise WorkflowError(
            "FORBIDDEN", "Triage staff does not have direct access to patient intake sessions.", 403
        )

    # Unauthenticated caller
    if session.user_id is not None:
        raise WorkflowError(
            "AUTH_REQUIRED", "Authentication is required to access this session.", 401
        )

    if not demo_enabled():
        raise WorkflowError("AUTH_REQUIRED", "Authentication is required.", 401)


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
        all_rows = adaptive.rows(db, session_id)
        by_id = {row.id: row for row in all_rows}
        answers = [answer_response(by_id[fact.answer_id]) for fact in active.values()]
        for row in all_rows:
            if row.question_id.startswith("rag_followup") and row.id in by_id:
                answers.append(answer_response(row))
        return answers
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


def enrich_summary_schema(
    summary: models.ClinicalSummary | None, db: Session | None = None
) -> schemas.ClinicalSummary | None:
    if summary is None:
        return None
    structured = None
    evidence = None
    if db is not None:
        try:
            from app.services.clinical_summary import ClinicalSummaryService

            _, structured = ClinicalSummaryService.generate_draft(
                db, summary.session_id, draft_version=summary.draft_version or 1
            )
            evidence = structured.evidence_references
        except Exception:
            pass

    return schemas.ClinicalSummary(
        id=summary.id,
        session_id=summary.session_id,
        generated_text=summary.generated_text,
        generated_structured_json=summary.generated_structured_json,
        reviewed_text=summary.reviewed_text,
        confirmed_text=summary.confirmed_text,
        status=summary.status,
        draft_provider=summary.draft_provider or "deterministic",
        draft_version=summary.draft_version or 1,
        version=summary.version,
        generated_at=summary.generated_at,
        reviewed_by=summary.reviewed_by,
        reviewed_at=summary.reviewed_at,
        confirmed_by=summary.confirmed_by,
        confirmed_at=summary.confirmed_at,
        amended_text=summary.amended_text,
        amended_by=summary.amended_by,
        amended_at=summary.amended_at,
        amendment_notes=summary.amendment_notes,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        structured_summary=structured,
        evidence=evidence,
    )


def detail(db, session_id, doctor=False, user=None):
    from app.services import adaptive, red_flags

    session = get_session(db, session_id)
    verify_session_access(db, session, user)
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
        summary=enrich_summary_schema(summary_for(db, session_id)),
        history=adaptive.history(db, session_id, user=user),
        alerts=alert_items,
        documents=doc_items,
    )


def create_session(db, payload, user=None):
    session_id = str(payload.id)
    existing = db.get(models.Session, session_id)
    if existing:
        verify_session_access(db, existing, user)
        patient = db.get(models.Patient, existing.patient_id)
        if (
            existing.hospital_token != payload.hospital_token
            or existing.language != payload.language
            or patient.name != payload.patient.name
            or patient.gender != payload.patient.gender
            or patient.age_years != payload.patient.age_years
            or patient.height_cm != payload.patient.height_cm
            or patient.weight_kg != payload.patient.weight_kg
            or patient.demo_abha_id != payload.patient.demo_abha_id
        ):
            raise WorkflowError("ID_CONFLICT", "This intake ID is already in use.")
        return existing
    patient = models.Patient(**payload.patient.model_dump())
    db.add(patient)
    db.flush()
    owner_id = user.id if user and user.role == "patient" else None
    session = models.Session(
        id=session_id,
        patient_id=patient.id,
        user_id=owner_id,
        hospital_id=payload.hospital_id,
        hospital_token=payload.hospital_token,
        language=payload.language,
        status="intake",
    )
    db.add(session)
    audit(db, "session_created", session_id, user=user)
    db.commit()
    db.refresh(session)
    return session


def save_consent(db, session_id, payload, user=None):
    session = get_session(db, session_id)
    verify_session_access(db, session, user)
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
        user=user,
        metadata={"share_with_doctor": payload.share_with_doctor, "text_version": 1},
    )
    db.commit()
    db.refresh(consent)
    return consent


def save_answer(db, session_id, payload, user=None):
    session = get_session(db, session_id)
    verify_session_access(db, session, user)
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
    audit(db, "answer_recorded", session_id, user=user, metadata={"field": payload.field})
    db.flush()
    from app.services import normalization
    from app.services.flow_registry import registry

    legacy_flow = registry()["legacy.intake"]
    question = next(q for _, q in legacy_flow.questions() if q.question_id == answer.question_id)
    db.commit()
    normalization.persist_committed(db, answer, question, legacy_flow)
    db.refresh(answer)
    return answer_response(answer)


def complete(db, session_id, user=None):
    session = get_session(db, session_id)
    verify_session_access(db, session, user)
    require_consent(db, session_id)
    if session.status in ("ready_for_review", "under_review", "confirmed"):
        return session
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "This session cannot be completed.")
    from app.services import adaptive
    from app.services.clinical_summary import ClinicalSummaryService

    history = adaptive.history(db, session_id, user=user)
    if db.get(models.InterviewRun, session_id):
        if not adaptive.state(db, session_id, user=user).is_complete:
            raise WorkflowError("ANSWERS_REQUIRED", "Address all applicable questions first.", 422)
    else:
        answers = {a.field: a.value for a in latest_answers(db, session_id)}
        if any(field not in answers for field in FIELDS):
            raise WorkflowError(
                "ANSWERS_REQUIRED", "Complete all five history questions first.", 422
            )

    draft_text, structured_summary = ClinicalSummaryService.generate_draft(
        db, session_id, draft_version=1, user=user
    )
    db.add(
        models.ClinicalSummary(
            session_id=session_id,
            generated_text=draft_text,
            generated_structured_json=history.model_dump_json()
            if history
            else structured_summary.model_dump_json(),
            reviewed_text=draft_text,
            status="generated",
            draft_provider="deterministic",
            draft_version=1,
            generated_at=now(),
            version=1,
        )
    )
    if session.user_id is None and not db.get(models.InterviewRun, session_id):
        from app.services.doctor_routing import (
            DEMO_DOCTOR_A,
            DEMO_HOSPITAL_A,
            ensure_demo_routing_data,
        )

        ensure_demo_routing_data(db)
        session.hospital_id = session.hospital_id or DEMO_HOSPITAL_A
        session.selected_doctor_id = session.selected_doctor_id or DEMO_DOCTOR_A
    if not session.hospital_id or not session.selected_doctor_id:
        raise WorkflowError(
            "ROUTING_REQUIRED",
            "Choose a hospital and an available doctor before completing the intake.",
            409,
        )
    session.status = "ready_for_review"
    session.completed_at = now()
    from app.services.doctor_routing import enqueue_completed_session

    enqueue_completed_session(db, session)
    audit(db, "intake_completed", session_id, user=user)
    db.commit()
    db.refresh(session)
    return session


def get_summary(db: Session, session_id: str) -> schemas.ClinicalSummary:
    get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.", 404)
    enriched = enrich_summary_schema(summary, db=db)
    assert enriched is not None
    return enriched


def review_summary(db, session_id, payload, user, confirm=False):
    session = get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")
    if confirm and summary.status == "confirmed" and payload.expected_version == summary.version:
        return enrich_summary_schema(summary)
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
        summary.confirmed_text = summary.reviewed_text
        session.status = "confirmed"
        audit(db, "summary_confirmed", session_id, user, {"version": summary.version})
    else:
        summary.version += 1
        summary.reviewed_text = payload.reviewed_text
        summary.status = "reviewed"
        summary.reviewed_by = user.id
        summary.reviewed_at = now()
        session.status = "under_review"
        notes = getattr(payload, "review_notes", None)
        db.add(
            models.SummaryRevision(
                summary_id=summary.id,
                version=summary.version,
                revision_type="edit",
                actor_type="DOCTOR",
                reviewed_text=summary.reviewed_text,
                actor_user_id=user.id,
                review_notes=notes,
            )
        )
        audit(db, "summary_reviewed", session_id, user, {"version": summary.version})
    db.commit()
    db.refresh(summary)
    return enrich_summary_schema(summary)


def regenerate_summary(db, session_id, payload, user) -> schemas.ClinicalSummary:
    session = get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")
    if summary.status == "confirmed" or session.status in ("confirmed", "cancelled"):
        raise WorkflowError("CONFIRMED_IMMUTABLE", "The confirmed record is read-only.")
    if summary.version != payload.expected_version:
        raise WorkflowError("VERSION_CONFLICT", "Another edit was saved. Reload the record.")

    has_manual_edits = bool(
        summary.reviewed_text
        and summary.generated_text
        and summary.reviewed_text.strip() != summary.generated_text.strip()
    )
    if has_manual_edits and not getattr(payload, "confirm_replacement", False):
        raise WorkflowError(
            "CONFIRM_REPLACEMENT_REQUIRED",
            "Manual doctor edits exist. Confirm replacement to overwrite with a regenerated draft.",
            409,
        )

    from app.services.clinical_summary import ClinicalSummaryService

    next_draft_version = (summary.draft_version or 1) + 1
    draft_text, structured_summary = ClinicalSummaryService.generate_draft(
        db, session_id, draft_version=next_draft_version, user=user
    )

    summary.version += 1
    summary.draft_version = next_draft_version
    summary.generated_text = draft_text
    summary.generated_structured_json = structured_summary.model_dump_json()
    summary.reviewed_text = draft_text
    summary.status = "reviewed"
    summary.reviewed_by = user.id
    summary.reviewed_at = now()
    session.status = "under_review"

    notes = (
        getattr(payload, "review_notes", None)
        or "Regenerated draft from structured clinical sources"
    )
    db.add(
        models.SummaryRevision(
            summary_id=summary.id,
            version=summary.version,
            revision_type="regenerate",
            actor_type="DOCTOR",
            reviewed_text=draft_text,
            actor_user_id=user.id,
            review_notes=notes,
            structured_snapshot=structured_summary.model_dump(mode="json"),
        )
    )
    audit(
        db,
        "summary_regenerated",
        session_id,
        user,
        {"version": summary.version, "draft_version": summary.draft_version},
    )
    db.commit()
    db.refresh(summary)
    return enrich_summary_schema(summary)


def get_summary_revisions(db, session_id) -> list[schemas.SummaryRevisionRecord]:
    get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")

    persisted = list(
        db.scalars(
            select(models.SummaryRevision)
            .where(models.SummaryRevision.summary_id == summary.id)
            .order_by(models.SummaryRevision.version.asc(), models.SummaryRevision.created_at.asc())
        )
    )

    records: list[schemas.SummaryRevisionRecord] = []

    has_v1 = any(r.version == 1 for r in persisted)
    if not has_v1 and summary.generated_text:
        records.append(
            schemas.SummaryRevisionRecord(
                id=f"initial-{summary.id}",
                summary_id=summary.id,
                version=1,
                revision_type="initial_draft",
                actor_type="SYSTEM",
                actor_user_id=None,
                actor_name="System Generator",
                reviewed_text=summary.generated_text,
                review_notes="Initial deterministic draft generated upon intake completion",
                structured_snapshot=None,
                created_at=summary.generated_at or summary.created_at or now(),
            )
        )

    for r in persisted:
        actor_name = None
        if r.actor_user_id:
            u = db.get(models.User, r.actor_user_id)
            actor_name = u.name if u else r.actor_user_id
        elif r.actor_type == "SYSTEM":
            actor_name = "System Generator"

        records.append(
            schemas.SummaryRevisionRecord(
                id=r.id,
                summary_id=r.summary_id,
                version=r.version,
                revision_type=r.revision_type or "edit",
                actor_type=r.actor_type or "DOCTOR",
                actor_user_id=r.actor_user_id,
                actor_name=actor_name,
                reviewed_text=r.reviewed_text,
                review_notes=r.review_notes,
                structured_snapshot=r.structured_snapshot,
                created_at=r.created_at,
            )
        )

    has_confirmed = any(r.revision_type == "confirmed" for r in records)
    if summary.status == "confirmed" and not has_confirmed:
        confirmer_name = None
        if summary.confirmed_by:
            u = db.get(models.User, summary.confirmed_by)
            confirmer_name = u.name if u else summary.confirmed_by
        records.append(
            schemas.SummaryRevisionRecord(
                id=f"confirmed-{summary.id}",
                summary_id=summary.id,
                version=summary.version,
                revision_type="confirmed",
                actor_type="DOCTOR",
                actor_user_id=summary.confirmed_by,
                actor_name=confirmer_name,
                reviewed_text=summary.confirmed_text or summary.reviewed_text or "",
                review_notes="Clinician verified and confirmed consultation summary",
                structured_snapshot=None,
                created_at=summary.confirmed_at or summary.updated_at or now(),
            )
        )

    return records


def get_summary_evidence(db, session_id) -> list[schemas.EvidenceReference]:
    get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")

    if summary.generated_structured_json:
        try:
            structured = schemas.StructuredClinicalSummary.model_validate_json(
                summary.generated_structured_json
            )
            if structured.evidence_references:
                return structured.evidence_references
        except Exception:
            pass

    from app.services.clinical_summary import ClinicalSummaryService

    _, structured = ClinicalSummaryService.generate_draft(
        db, session_id, draft_version=summary.draft_version or 1
    )
    return structured.evidence_references


def amend_summary(
    db: Session,
    session_id: str,
    payload: schemas.SummaryAmendRequest,
    user: models.User,
) -> schemas.ClinicalSummary:
    get_session(db, session_id)
    require_consent(db, session_id)
    summary = summary_for(db, session_id)
    if summary is None:
        raise WorkflowError("NOT_READY", "Complete the intake before review.")
    if summary.status not in ("confirmed", "amended"):
        raise WorkflowError(
            "NOT_CONFIRMED",
            "Only confirmed clinical summaries can receive amendments. Use draft editing for working summaries.",
            409,
        )

    if not payload.amended_text or not payload.amended_text.strip():
        raise WorkflowError("INVALID_TEXT", "Amended summary text cannot be empty.", 422)
    if not payload.amendment_notes or len(payload.amendment_notes.strip()) < 3:
        raise WorkflowError(
            "INVALID_NOTES",
            "A clinical justification note is required for an amendment.",
            422,
        )

    current_time = now()
    summary.version += 1
    summary.draft_version = (summary.draft_version or 1) + 1
    summary.amended_text = payload.amended_text
    summary.amended_by = user.id
    summary.amended_at = current_time
    summary.amendment_notes = payload.amendment_notes
    summary.status = "amended"

    db.add(
        models.SummaryRevision(
            summary_id=summary.id,
            version=summary.version,
            revision_type="amendment",
            actor_type="DOCTOR",
            reviewed_text=payload.amended_text,
            actor_user_id=user.id,
            review_notes=payload.amendment_notes,
            structured_snapshot=None,
            created_at=current_time,
        )
    )

    audit(
        db,
        "summary_amended",
        session_id,
        user,
        {
            "version": summary.version,
            "draft_version": summary.draft_version,
            "notes": payload.amendment_notes,
        },
    )

    db.commit()
    db.refresh(summary)
    return enrich_summary_schema(summary, db=db)


def get_audit_trail(db: Session, session_id: str) -> schemas.AuditTrailResponse:
    get_session(db, session_id)
    require_consent(db, session_id)

    logs = list(
        db.scalars(
            select(models.AuditLog)
            .where(models.AuditLog.entity_id == session_id)
            .order_by(models.AuditLog.created_at.asc())
        )
    )

    items = [
        schemas.AuditTrailItem(
            id=log.id,
            timestamp=log.created_at,
            actor_type=log.actor_type,
            actor_user_id=log.actor_user_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            metadata=log.metadata_json or {},
        )
        for log in logs
    ]

    return schemas.AuditTrailResponse(
        session_id=session_id,
        total=len(items),
        items=items,
    )
