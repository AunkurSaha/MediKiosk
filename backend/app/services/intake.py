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


def get_session(db: Session, session_id: str, for_update: bool = False):
    stmt = select(models.Session).where(models.Session.id == session_id)
    if for_update:
        stmt = stmt.with_for_update()
    session = db.scalar(stmt)
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
            if (
                row.question_id.startswith(("rag_followup", "document_confirmation."))
                and row.id in by_id
            ):
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
    if summary.generated_structured_json:
        try:
            structured = schemas.StructuredClinicalSummary.model_validate_json(
                summary.generated_structured_json
            )
            if db is not None:
                verified_ids = set(
                    db.scalars(
                        select(models.FieldVerification.field_id).where(
                            models.FieldVerification.session_id == summary.session_id,
                            models.FieldVerification.field_type == "summary_statement",
                            models.FieldVerification.status == "verified",
                        )
                    )
                )
                if verified_ids:
                    by_id = {item.statement_id: item for item in structured.evidence_references}
                    for item in structured.evidence_references:
                        if item.statement_id in verified_ids:
                            item.status = "clinician_verified"
                            item.badge = "Clinician Verified"
                            item.provenance_explanation.append(
                                "Verified by the reviewing clinician; original source evidence remains linked."
                            )
                    for section in structured.sections:
                        section.evidence = [
                            by_id.get(item.statement_id, item) for item in section.evidence
                        ]
            evidence = structured.evidence_references
        except Exception:
            pass

    coverage = structured.coverage if structured else None
    packet = _pre_arrival_packet(db, summary, structured, coverage) if db is not None else None

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
        coverage=coverage,
        pre_arrival_packet=packet,
    )


def _pre_arrival_packet(db, summary, structured, coverage):
    """Assemble the doctor-only read packet from existing persisted data."""
    session = db.get(models.Session, summary.session_id)
    if session is None:
        return None
    hospital = db.get(models.Hospital, session.hospital_id) if session.hospital_id else None
    doctor = db.get(models.User, session.selected_doctor_id) if session.selected_doctor_id else None
    queue = db.scalar(
        select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session.id)
    )
    documents = list(
        db.scalars(select(models.Document).where(models.Document.session_id == session.id))
    )
    alerts = list(db.scalars(select(models.Alert).where(models.Alert.session_id == session.id)))
    routing_result = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session.id
        )
    )
    extractions = list(
        db.scalars(
            select(models.DocumentExtraction).where(
                models.DocumentExtraction.session_id == session.id
            )
        )
    )
    extractions_by_document: dict[str, list] = {}
    for extraction in extractions:
        extractions_by_document.setdefault(extraction.document_id, []).append(extraction)
    evidence_ids = select(models.ClinicalEvidence.id).where(
        models.ClinicalEvidence.session_id == session.id
    )
    conflicts = list(
        db.scalars(
            select(models.ClinicalEvidenceConflict).where(
                (models.ClinicalEvidenceConflict.evidence_a_id.in_(evidence_ids))
                | (models.ClinicalEvidenceConflict.evidence_b_id.in_(evidence_ids))
            )
        )
    )
    chief_complaint = None
    history: list[dict] = []
    packet_timeline: list[dict] = []
    if structured:
        for section in structured.sections:
            if section.section_key == "chief_complaint" and section.content_lines:
                chief_complaint = section.content_lines[0]
            history.append(
                {
                    "section": section.section_key,
                    "items": section.items,
                    "lines": section.content_lines,
                }
            )
            if section.section_key == "clinical_timeline":
                packet_timeline = [{"text": line} for line in section.content_lines]
    return schemas.PreArrivalPacket(
        packet_reference=f"mkp:{session.id}",
        visit_context={
            "session_id": session.id,
            "hospital_token": session.hospital_token,
            "language": session.language,
            "status": session.status,
        },
        facility=(
            {"id": hospital.id, "name": hospital.name, "city": hospital.city} if hospital else None
        ),
        selected_doctor=(
            {"id": session.selected_doctor_id, "name": doctor.name if doctor else None}
            if session.selected_doctor_id
            else None
        ),
        queue={"visit_token": queue.visit_token, "status": queue.status} if queue else None,
        routing={
            "hospital_id": session.hospital_id,
            "selected_doctor_id": session.selected_doctor_id,
            "routing_state": routing_result.routing_state if routing_result else None,
            "suggested_specialty": routing_result.suggested_specialty if routing_result else None,
            "protocol_version": routing_result.protocol_version if routing_result else None,
            "supporting_evidence_ids": routing_result.supporting_evidence_ids_json
            if routing_result
            else [],
            "triggered_rule_ids": routing_result.triggered_rule_ids_json if routing_result else [],
        },
        chief_complaint=chief_complaint,
        structured_history=history,
        documents=[
            {
                "document_id": item.id,
                "filename": item.original_filename,
                "document_type": item.document_type,
                "processing_status": item.processing_status,
                "extractions": [
                    {
                        "extraction_id": extraction.id,
                        "extractor": extraction.extractor,
                        "extractor_version": extraction.extractor_version,
                        "structured_data": extraction.structured_json,
                        "confidence": extraction.confidence,
                        "verification_status": extraction.verification_status,
                    }
                    for extraction in extractions_by_document.get(item.id, [])
                ],
            }
            for item in documents
        ],
        timeline=packet_timeline,
        red_flags=[
            {
                "alert_id": item.id,
                "rule_id": item.rule_id,
                "reason": item.reason,
                "priority": item.priority,
                "status": item.status,
                "triggering_facts": item.triggering_facts_json,
            }
            for item in alerts
        ],
        coverage=coverage,
        clinical_summary_id=summary.id,
        clinical_summary_status=summary.status,
        clinical_summary=structured,
        conflicts=[
            {
                "conflict_id": item.id,
                "evidence_a_id": item.evidence_a_id,
                "evidence_b_id": item.evidence_b_id,
                "reason": item.reason,
            }
            for item in conflicts
        ],
    )


def build_pre_arrival_packet(db: Session, session_id: str) -> schemas.PreArrivalPacket:
    summary = summary_for(db, session_id)
    enriched = enrich_summary_schema(summary, db=db)
    if enriched is None or enriched.pre_arrival_packet is None:
        raise WorkflowError("PACKET_NOT_READY", "Completed summary state is required.", 409)
    return schemas.PreArrivalPacket.model_validate(enriched.pre_arrival_packet)


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
        summary=enrich_summary_schema(summary_for(db, session_id), db=db),
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
            or existing.journey_mode != payload.journey_mode
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
        journey_mode=payload.journey_mode,
        status="intake",
    )
    db.add(session)
    audit(db, "session_created", session_id, user=user)
    db.commit()
    db.refresh(session)
    return session


def update_journey_mode(db, session_id, journey_mode, user=None):
    session = get_session(db, session_id)
    verify_session_access(db, session, user)
    if session.status != "intake" or db.scalar(
        select(models.DoctorQueueEntry.id).where(models.DoctorQueueEntry.session_id == session.id)
    ):
        raise WorkflowError(
            "JOURNEY_MODE_LOCKED", "Journey type cannot change after intake submission.", 409
        )
    if session.journey_mode == journey_mode:
        return session
    previous = session.journey_mode
    session.journey_mode = journey_mode
    # A facility selected under one journey has different semantics under the
    # other. Require an explicit fresh confirmation instead of reusing it.
    session.hospital_id = None
    session.selected_doctor_id = None
    session.updated_at = now()
    audit(
        db,
        "journey_mode_changed",
        session.id,
        user=user,
        metadata={"previous": previous, "journey_mode": journey_mode},
    )
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
    from app.services import clinical_evidence

    clinical_evidence.create_patient_answer_evidence(db, answer, value=payload.value)
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
            generated_structured_json=structured_summary.model_dump_json(),
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
    if not session.hospital_id:
        raise WorkflowError(
            "ROUTING_REQUIRED",
            "Choose an eligible facility before completing the intake.",
            409,
        )
    routing = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session_id
        )
    )
    if (
        routing is not None
        and routing.routing_state != "EMERGENCY"
        and not session.selected_doctor_id
    ):
        raise WorkflowError(
            "DOCTOR_REQUIRED",
            "Choose an eligible recommended doctor before completing the intake.",
            409,
        )
    session.status = "ready_for_review"
    session.completed_at = now()
    if routing is None or routing.routing_state != "EMERGENCY":
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
        return enrich_summary_schema(summary, db=db)
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
    return enrich_summary_schema(summary, db=db)


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
    return enrich_summary_schema(summary, db=db)


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
            actor_user_id=user.id,
            reviewed_text=payload.amended_text,
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
