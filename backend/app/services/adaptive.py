import hashlib
import json
import logging

from sqlalchemy import select

from app import models
from app.core.errors import WorkflowError
from app.schemas.adaptive import Fact, FlowChoice, InterviewState
from app.schemas.alert import AlertSummary
from app.schemas.flow import Flow, Localized, Option, Question
from app.services import intake, normalization, red_flags
from app.services.flow_registry import registry
from app.services.interview_engine import InterviewEngine, validate_answer

logger = logging.getLogger(__name__)


def _enforce_non_emergency_patient_path(db, session_id, user=None):
    result = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session_id
        )
    )
    if (
        result is not None
        and result.routing_state == "EMERGENCY"
        and not (user and user.role in ("doctor", "triage"))
    ):
        raise WorkflowError(
            "EMERGENCY_BYPASS_REQUIRED",
            "Potential emergency symptoms detected. Immediate in-person clinical assessment is recommended.",
            409,
        )
    session = db.get(models.Session, session_id)
    if (
        result is not None
        and result.routing_state != "EMERGENCY"
        and session is not None
        and not session.hospital_id
        and not (user and user.role in ("doctor", "triage"))
    ):
        raise WorkflowError(
            "FACILITY_REQUIRED",
            "Select an eligible care facility before starting the full interview.",
            409,
        )


def rows(db, session_id):
    from app.services import continuity

    return continuity.authoritative_interview_answers(db, session_id)


def flow_for(db, session_id):
    run = db.get(models.InterviewRun, session_id)
    if run:
        return Flow.model_validate(run.flow_snapshot), run
    if rows(db, session_id):
        return registry()["legacy.intake"], None
    return None, None


def engine_for(db, session_id, flow):
    questions = {q.question_id: q for _, q in flow.questions()}
    questions_by_field = {q.field: q for _, q in flow.questions()}
    facts = {}
    normalized = normalization.for_answers(db, session_id)
    for row in rows(db, session_id):
        if row.question_id.startswith(("rag_followup", "document_confirmation.", "continuity.")):
            continue
        question = (
            questions_by_field.get(row.field)
            if row.question_id.startswith("rapid.")
            else questions.get(row.question_id)
        )
        if row.question_id.startswith("rapid.") and question is None:
            continue
        if question is None:
            raise WorkflowError(
                "FLOW_DATA_MISMATCH", "Saved answer is absent from the pinned flow."
            )
        stored = json.loads(row.value_json)
        envelope = (
            stored
            if isinstance(stored, dict) and "status" in stored
            else {
                "status": "answered",
                "value": stored,
            }
        )
        facts[question.question_id] = Fact(
            answer_id=row.id,
            question_id=question.question_id,
            field=question.field,
            label=question.text,
            status=envelope["status"],
            value=envelope["value"],
            raw_value=row.raw_value,
            source=row.source,
            language=row.language,
            recorded_at=row.created_at,
            normalization=normalization.enrich(row, question, normalized),
        )
    return InterviewEngine(flow, facts)


def state(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    _enforce_non_emergency_patient_path(db, session_id, user)
    flow, run = flow_for(db, session_id)
    if flow is None:
        return InterviewState(
            selection_required=True,
            flows=[
                FlowChoice(
                    flow_id=f.flow_id, version=f.version, namespace=f.namespace, label=f.label
                )
                for f in registry().values()
                if f.namespace != "legacy"
            ],
        )
    engine = engine_for(db, session_id, flow)
    res = engine.state(run.cursor if run else None, run.revision if run else 0)
    if run is not None and run.cursor and run.cursor.startswith("continuity."):
        from app.services import continuity

        resolved = continuity.reconfirmation_context_for_question(db, session_id, run.cursor)
        if resolved is not None:
            evidence, context = resolved
            question = continuity.build_reconfirmation_question(evidence, context)
            latest = next(
                (
                    row
                    for row in reversed(rows(db, session_id))
                    if row.question_id == question.question_id
                ),
                None,
            )
            current_answer = None
            if latest is not None:
                stored = json.loads(latest.value_json) if latest.value_json else {}
                envelope = (
                    stored
                    if isinstance(stored, dict) and "status" in stored
                    else {"status": "answered", "value": stored}
                )
                current_answer = Fact(
                    answer_id=latest.id,
                    question_id=latest.question_id,
                    field=latest.field,
                    label=question.text,
                    status=envelope["status"],
                    value=envelope["value"],
                    raw_value=latest.raw_value,
                    source=latest.source,
                    language=latest.language,
                    recorded_at=latest.created_at,
                )
            return res.model_copy(
                update={
                    "question": question,
                    "continuity_reconfirmation": context,
                    "current_answer": current_answer,
                }
            )
    from app.services.rag_interview_planner import coverage_domains

    covered, missing_required_domains, missing_optional_domains = coverage_domains(engine)
    res.covered_domains = covered
    res.missing_required_domains = missing_required_domains
    res.missing_optional_domains = missing_optional_domains

    alerts = red_flags.get_session_alerts(db, session_id)
    active_alerts = [a for a in alerts if a.status in ("new", "acknowledged")]
    if active_alerts:
        highest = sorted(
            active_alerts,
            key=lambda a: (0 if a.priority == "emergency" else 1, a.created_at),
        )[0]
        res.red_flag_alert = AlertSummary(
            id=highest.id,
            rule_id=highest.rule_id,
            priority=highest.priority,
            category=highest.category,
            reason=highest.reason,
            created_at=highest.created_at,
        )

    # Include any previously answered RAG facts into active_answers and history
    rag_facts = []
    norm_map = normalization.for_answers(db, session_id)
    answer_rows = rows(db, session_id)
    for row in answer_rows:
        if row.question_id.startswith("rag_followup"):
            stored = json.loads(row.value_json) if row.value_json else {}
            envelope = (
                stored
                if isinstance(stored, dict) and "status" in stored
                else {"status": "answered", "value": stored}
            )
            rag_fact = Fact(
                answer_id=row.id,
                question_id=row.question_id,
                field=row.field,
                label=Localized(
                    en="Clinical follow-up", bn="ক্লিনিক্যাল ফলো-আপ", hi="चिकित्सीय अनुवर्ती"
                ),
                status=envelope.get("status", "answered"),
                value=envelope.get("value", row.raw_value),
                raw_value=row.raw_value or "",
                source=row.source,
                language=row.language,
                recorded_at=row.created_at,
                normalization=norm_map.get(row.id),
            )
            rag_facts.append(rag_fact)

    if rag_facts:
        res.active_answers.extend(rag_facts)
        if res.history and res.history.sections:
            target_sec = next((s for s in res.history.sections if s.section_id == "hpi"), None)
            if target_sec is None:
                target_sec = res.history.sections[0]
            target_sec.facts.extend(rag_facts)

    # Historical facts are never made current automatically.  At the matching
    # configured history target, offer one explicit, stable reconfirmation turn.
    if (
        not res.is_complete
        and res.question is not None
        and res.question.field in ("medications.details", "allergies.details")
        and res.current_answer is None
    ):
        from app.services import continuity

        pending_continuity = continuity.pending_reconfirmation(db, session_id, res.question.field)
        if pending_continuity is not None:
            evidence, context = pending_continuity
            display = str(context.historical_value)
            is_allergy = context.target_field.startswith("allergies")
            question = Question(
                question_id=continuity.continuity_question_id(evidence.id),
                field=context.target_field,
                type="single_choice",
                required=True,
                allow_unknown=True,
                origin="continuity",
                text=Localized(
                    en=(
                        f"At your previous visit, you reported an allergy to {display}. Is that still correct?"
                        if is_allergy
                        else f"At your previous visit, you reported taking {display}. Are you still taking it?"
                    ),
                    bn=(
                        f"আপনার আগের ভিজিটে {display} অ্যালার্জির কথা জানিয়েছিলেন। এটি কি এখনও সঠিক?"
                        if is_allergy
                        else f"আপনার আগের ভিজিটে {display} নেওয়ার কথা জানিয়েছিলেন। আপনি কি এখনও এটি নিচ্ছেন?"
                    ),
                    hi=(
                        f"आपने पिछले दौरे में {display} से एलर्जी बताई थी। क्या यह अभी भी सही है?"
                        if is_allergy
                        else f"आपने पिछले दौरे में {display} लेने की बात बताई थी। क्या आप अभी भी इसे ले रहे हैं?"
                    ),
                ),
                options=[
                    Option(value="yes", label=Localized(en="Yes", bn="হ্যাঁ", hi="हाँ")),
                    Option(value="no", label=Localized(en="No", bn="না", hi="नहीं")),
                    *(
                        []
                        if is_allergy
                        else [
                            Option(
                                value="changed",
                                label=Localized(en="Changed", bn="পরিবর্তিত", hi="बदल गया"),
                            )
                        ]
                    ),
                    Option(
                        value="not_sure",
                        label=Localized(en="Not sure", bn="নিশ্চিত নই", hi="पक्का नहीं"),
                    ),
                ],
            )
            return res.model_copy(
                update={"question": question, "continuity_reconfirmation": context}
            )

    # Document facts remain unverified evidence until this explicit patient turn.
    if (
        not res.is_complete
        and res.question is not None
        and res.question.question_id not in ("chief_complaint.description", "chief_complaint")
        and any(
            question_id in engine.active
            for question_id in ("chief_complaint.description", "chief_complaint")
        )
        and res.current_answer is None
    ):
        from app.services import clinical_coverage

        pending_confirmation = clinical_coverage.pending_medication_confirmation(db, session_id)
        if pending_confirmation is not None:
            evidence, context = pending_confirmation
            display = context.original_extracted_value
            question = Question(
                question_id=clinical_coverage.confirmation_question_id(evidence.id),
                field="medications.details",
                type="single_choice",
                required=True,
                allow_unknown=True,
                origin="document_confirmation",
                text=Localized(
                    en=f"Your uploaded document mentions {display}. Are you currently taking this medicine?",
                    bn=f"আপনার আপলোড করা নথিতে {display} উল্লেখ আছে। আপনি কি বর্তমানে এই ওষুধটি গ্রহণ করছেন?",
                    hi=f"आपके अपलोड किए गए दस्तावेज़ में {display} लिखा है। क्या आप अभी यह दवा ले रहे हैं?",
                ),
                options=[
                    Option(value="yes", label=Localized(en="Yes", bn="হ্যাঁ", hi="हाँ")),
                    Option(value="no", label=Localized(en="No", bn="না", hi="नहीं")),
                    Option(
                        value="not_sure",
                        label=Localized(en="Not sure", bn="নিশ্চিত নই", hi="पक्का नहीं"),
                    ),
                ],
            )
            return res.model_copy(update={"question": question, "document_confirmation": context})

    # RAG plans the next approved coverage field after chief-complaint acquisition.
    # The deterministic question already in ``res`` is the fail-safe fallback.
    if (
        not res.is_complete
        and res.question is not None
        and res.question.question_id != "chief_complaint.description"
        and "chief_complaint.description" in engine.active
        and res.current_answer is None
        and res.question.question_id in engine.pending
    ):
        try:
            from app.services.clinical_domains import ClinicalDomainTracker
            from app.services.question_planner import QuestionPlanner

            complaint_type = (
                "chest_pain"
                if "chest_pain" in flow.flow_id
                else "headache"
                if "headache" in flow.flow_id
                else "general"
            )
            tracker = ClinicalDomainTracker(complaint_type)
            flow_questions = {q.question_id: q for _, q in flow.questions()}
            recent_answers = []
            recent_questions = []
            persisted_fields = set()
            for row in answer_rows:
                if row.question_id.startswith("rag_followup"):
                    continue
                question = flow_questions.get(row.question_id)
                if question is None:
                    continue
                persisted_fields.add(row.field)
                tracker.record_answer(row.question_id, row.field, row.raw_value or "")
                recent_answers.append(row.raw_value or "")
                recent_questions.append(question.text.en)

            # Free-text extraction may cover a domain, but it must not masquerade
            # as a persisted structured field. This keeps required-field completion
            # deterministic while still letting the planner avoid needless repeats.
            tracker.answered_fields.intersection_update(persisted_fields)
            rag_question, rag_suggestion, _ = QuestionPlanner(
                db, flow, engine, tracker
            ).plan_next_turn(
                str(session_id),
                language=session.language,
                recent_answers=recent_answers,
                recent_questions=recent_questions,
            )
            if rag_question is not None and rag_suggestion is not None:
                new_res = res.model_copy()
                new_res.question = rag_question
                new_res.rag_suggestions = [rag_suggestion]
                applicable_ids = [q.question_id for _, q in engine.applicable]
                selected_index = applicable_ids.index(rag_question.question_id)
                new_res.previous_question_id = (
                    applicable_ids[selected_index - 1] if selected_index > 0 else None
                )
                new_res.progress = new_res.progress.model_copy(
                    update={"position": selected_index + 1}
                )
                return new_res
        except Exception as exc:
            logger.warning("RAG interview planning failed open: %s", exc)

    return res


def editable(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    _enforce_non_emergency_patient_path(db, session_id, user)
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "Completed answers cannot be changed.")
    return session


def select_flow(db, session_id, payload, user=None):
    session = editable(db, session_id, user=user)
    if user is not None and user.role == "patient" and not session.hospital_id:
        raise WorkflowError(
            "HOSPITAL_REQUIRED", "Choose a hospital before selecting a health concern.", 409
        )
    flow, run = flow_for(db, session_id)
    if flow is not None:
        if flow.flow_id != payload.flow_id:
            raise WorkflowError(
                "FLOW_LOCKED", "This intake already has a flow. Start a new intake to change it."
            )
        return state(db, session_id, user=user)
    flow = registry().get(payload.flow_id)
    if flow is None or flow.namespace == "legacy":
        raise WorkflowError(
            "INVALID_FLOW", "Choose a supported complaint or the AYUSH demonstration.", 422
        )
    run = models.InterviewRun(
        session_id=session_id,
        flow_id=flow.flow_id,
        flow_version=flow.version,
        flow_snapshot=flow.model_dump(mode="json"),
        cursor=flow.questions()[0][1].question_id,
        revision=0,
    )
    db.add(run)
    intake.audit(
        db,
        "interview_flow_selected",
        session_id,
        metadata={"flow_id": flow.flow_id, "version": flow.version},
    )
    db.commit()
    return state(db, session_id, user=user)


def require_run(db, session_id):
    flow, run = flow_for(db, session_id)
    if flow is None:
        raise WorkflowError("FLOW_REQUIRED", "Select a complaint before answering.", 422)
    if run is None:
        run = models.InterviewRun(
            session_id=session_id,
            flow_id=flow.flow_id,
            flow_version=flow.version,
            flow_snapshot=flow.model_dump(mode="json"),
            revision=0,
        )
        db.add(run)
        db.flush()
    return flow, run


def check_revision(run, expected):
    if run.revision != expected:
        raise WorkflowError(
            "INTERVIEW_CONFLICT", "This interview changed. Reload before continuing."
        )


def submit(db, session_id, payload, user=None):
    session = editable(db, session_id, user=user)
    flow, run = require_run(db, session_id)
    hashed_payload = payload.model_dump(mode="json")
    if hashed_payload["voice_candidate"] is None:
        hashed_payload.pop("voice_candidate")  # Preserve historical request hashes.
    digest = hashlib.sha256(
        json.dumps(hashed_payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    receipt = db.get(models.InterviewRequest, (session_id, str(payload.request_id)))
    if receipt:
        if receipt.payload_hash != digest:
            raise WorkflowError(
                "ID_CONFLICT", "This request ID was already used for another answer."
            )
        return state(db, session_id, user=user)
    check_revision(run, payload.expected_revision)
    engine = engine_for(db, session_id, flow)
    active_state = state(db, session_id, user=user)
    current = active_state.question
    if current is None or current.question_id != payload.question_id:
        raise WorkflowError("QUESTION_NOT_CURRENT", "Reload the current interview question.", 409)
    if payload.language != session.language:
        raise WorkflowError("INVALID_ANSWER", "Answer language must match the session.", 422)
    candidate = None
    if payload.source == "voice":
        from app.services.voice_candidates import verify

        candidate = verify(db, session_id, payload, current)
    elif payload.voice_candidate is not None:
        raise WorkflowError(
            "INVALID_VOICE_CANDIDATE",
            "Edited answers must be submitted as typed text without a voice token.",
            422,
        )
    validate_answer(current, payload)
    value = payload.model_dump(mode="json")["value"]
    previous = engine.answers.get(payload.question_id)
    saved_answer = None
    if previous is None or (
        previous.status,
        previous.model_dump(mode="json")["value"],
        previous.raw_value,
        previous.source,
    ) != (payload.status, value, payload.raw_value, payload.source):
        saved_answer = models.InterviewAnswer(
            session_id=session_id,
            question_id=current.question_id,
            field=current.field,
            value_json=json.dumps({"status": payload.status, "value": value}, ensure_ascii=False),
            raw_value=payload.raw_value,
            source=payload.source,
            language=payload.language,
            verification_status="patient_reported",
            created_at=intake.now(),
        )
        db.add(saved_answer)
        intake.audit(
            db,
            "answer_recorded",
            session_id,
            user=user,
            metadata={
                "field": current.field,
                "flow_version": flow.version,
                "origin": (
                    "continuity"
                    if current.origin == "continuity"
                    else "document_confirmation"
                    if current.origin == "document_confirmation"
                    else "rag"
                    if current.origin == "rag" or current.question_id.startswith("rag_followup")
                    else "flow"
                ),
            },
        )
        db.flush()
        from app.services import clinical_evidence

        evidence_value = (
            active_state.continuity_reconfirmation.historical_value
            if current.origin == "continuity"
            and value == "yes"
            and active_state.continuity_reconfirmation is not None
            else value
        )
        clinical_evidence.create_patient_answer_evidence(
            db,
            saved_answer,
            value=evidence_value,
            answer_status=payload.status,
            relationship_metadata=(
                {
                    "historical_evidence_id": active_state.continuity_reconfirmation.evidence_id,
                    "historical_source_session_id": active_state.continuity_reconfirmation.source_session_id,
                    "historical_value": active_state.continuity_reconfirmation.historical_value,
                    "canonical_field": active_state.continuity_reconfirmation.canonical_field,
                    "question_source": "CONTINUITY_RECONFIRMATION",
                    "continuity_decision": value,
                }
                if active_state.continuity_reconfirmation is not None
                else {
                    "document_evidence_id": active_state.document_confirmation.evidence_id,
                    "source_document_id": active_state.document_confirmation.source_document_id,
                    "source_fact_id": active_state.document_confirmation.source_fact_id,
                    "question_source": "DOCUMENT_CONFIRMATION",
                    "confirmation_decision": value,
                }
                if active_state.document_confirmation is not None
                else None
            ),
            voice_metadata=(
                {
                    "asr_candidate_id": candidate["id"],
                    "asr_provider": candidate["provider"],
                    "asr_model": candidate["model"],
                }
                if candidate is not None
                else None
            ),
        )
    if candidate is not None:
        intake.audit(
            db,
            "voice_candidate_confirmed",
            session_id,
            user=user,
            metadata={
                "candidate_id": candidate["id"],
                "provider": candidate["provider"],
                "model": candidate["model"],
                "question_id": current.question_id,
                "language": payload.language,
                "source_answer_id": saved_answer.id
                if saved_answer is not None
                else previous.answer_id,
            },
        )
    if current.origin == "document_confirmation" and value == "yes":
        _persist_confirmed_document_medication(
            db,
            session,
            flow,
            active_state.document_confirmation,
            saved_answer,
        )
    if current.origin == "continuity":
        _persist_continuity_resolution(
            db, session, flow, active_state.continuity_reconfirmation, saved_answer, value
        )
    if not payload.question_id.startswith("rag_followup"):
        updated_engine = engine_for(db, session_id, flow)
        run.cursor = (
            updated_engine.pending[0]
            if current.origin in ("rag", "document_confirmation", "continuity")
            and updated_engine.pending
            else updated_engine.after(payload.question_id)
        )
    run.revision += 1
    session.updated_at = intake.now()
    db.add(
        models.InterviewRequest(
            session_id=session_id, request_id=str(payload.request_id), payload_hash=digest
        )
    )
    db.commit()
    if saved_answer is not None:
        normalization.persist_committed(db, saved_answer, current, flow, payload.status)
    intake.get_session(db, session_id)
    active_engine = engine_for(db, session_id, flow)
    db.info.pop("triage_events", None)
    all_facts = list(active_engine.active.values()) + [
        Fact(
            answer_id=r.id,
            question_id=r.question_id,
            field=r.field,
            label=Localized(en="Clinical follow-up", bn="ক্লিনিক্যাল ফলো-আপ", hi="चिकित्सीय अनुवर्ती"),
            status=json.loads(r.value_json).get("status", "answered")
            if r.value_json
            else "answered",
            value=json.loads(r.value_json).get("value", r.raw_value)
            if r.value_json
            else r.raw_value,
            raw_value=r.raw_value or "",
            source=r.source,
            language=r.language,
            recorded_at=r.created_at,
            normalization=normalization.for_answers(db, session_id).get(r.id),
        )
        for r in rows(db, session_id)
        if r.question_id.startswith("rag_followup")
    ]
    red_flags.evaluate_and_persist(db, session_id, flow.flow_id, all_facts)
    db.commit()
    from app.services.rag_integration import clear_rag_question_cache
    from app.services.rag_interview_planner import clear_plan_cache

    clear_rag_question_cache(session_id)
    clear_plan_cache(session_id)
    return state(db, session_id, user=user)


def _persist_continuity_resolution(db, session, flow, context, confirmation_answer, decision):
    """Project an explicit continuity decision into current flow fields only.

    The source evidence remains historical.  These new patient-answer rows are
    intentionally ordinary current-session answers so coverage and summaries do
    not treat prior data as current merely because it exists.
    """
    if context is None or confirmation_answer is None or decision not in ("yes", "no"):
        return
    from app.services import clinical_evidence

    questions = {question.field: question for _, question in flow.questions()}
    is_allergy = context.target_field.startswith("allergies")
    projections = (
        (
            (
                "allergies.details",
                context.historical_value if decision == "yes" else "no",
                str(context.historical_value),
            ),
        )
        if is_allergy
        else (
            (
                "medications.details",
                context.historical_value if decision == "yes" else "no",
                str(context.historical_value),
            ),
        )
    )
    for field, value, raw_value in projections:
        question = questions.get(field)
        if question is None:
            continue
        answer = models.InterviewAnswer(
            session_id=session.id,
            question_id=question.question_id,
            field=field,
            value_json=json.dumps({"status": "answered", "value": value}, ensure_ascii=False),
            raw_value=raw_value,
            source="touch",
            language=session.language,
            verification_status="patient_reported",
            created_at=intake.now(),
        )
        db.add(answer)
        db.flush()
        clinical_evidence.create_patient_answer_evidence(
            db,
            answer,
            value=value,
            relationship_metadata={
                "historical_evidence_id": context.evidence_id,
                "historical_source_session_id": context.source_session_id,
                "historical_value": context.historical_value,
                "canonical_field": context.canonical_field,
                "question_source": "CONTINUITY_RECONFIRMATION",
                "continuity_decision": decision,
                "confirmation_answer_id": confirmation_answer.id,
            },
        )


def _persist_confirmed_document_medication(db, session, flow, context, confirmation_answer):
    """Project an explicit yes into canonical flow answers without altering OCR evidence."""
    if context is None or confirmation_answer is None:
        return
    from app.services import clinical_evidence

    questions = {question.field: question for _, question in flow.questions()}
    evidence = db.get(models.ClinicalEvidence, context.evidence_id)
    display = context.original_extracted_value
    for field, value, raw_value in (
        ("medications.any", True, "Yes"),
        ("medications.details", display, display),
        ("medications", display, display),
    ):
        question = questions.get(field)
        if question is None:
            continue
        existing = next(
            (row for row in rows(db, session.id) if row.question_id == question.question_id), None
        )
        if existing is not None:
            continue
        answer = models.InterviewAnswer(
            session_id=session.id,
            question_id=question.question_id,
            field=field,
            value_json=json.dumps({"status": "answered", "value": value}, ensure_ascii=False),
            raw_value=raw_value,
            source="touch",
            language=session.language,
            verification_status="patient_reported",
            created_at=intake.now(),
        )
        db.add(answer)
        db.flush()
        clinical_evidence.create_patient_answer_evidence(
            db,
            answer,
            value=value,
            relationship_metadata={
                "document_evidence_id": evidence.id,
                "source_document_id": context.source_document_id,
                "source_fact_id": context.source_fact_id,
                "question_source": "DOCUMENT_CONFIRMATION",
                "confirmation_decision": "yes",
                "confirmation_answer_id": confirmation_answer.id,
            },
        )


def navigate(db, session_id, payload, user=None):
    editable(db, session_id, user=user)
    flow, run = require_run(db, session_id)
    check_revision(run, payload.expected_revision)
    engine = engine_for(db, session_id, flow)
    allowed = set(engine.active) | set(engine.pending[:1])
    synthetic = None
    if payload.question_id.startswith("continuity."):
        from app.services import continuity

        synthetic = continuity.reconfirmation_context_for_question(
            db, session_id, payload.question_id
        )
    if payload.question_id not in allowed and synthetic is None:
        raise WorkflowError(
            "QUESTION_NOT_ACTIVE",
            "Only active saved answers or the next pending question may be opened.",
            422,
        )
    run.cursor = payload.question_id
    run.revision += 1
    db.commit()
    return state(db, session_id, user=user)


def history(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    flow, _ = flow_for(db, session_id)
    return engine_for(db, session_id, flow).history() if flow else None
