import hashlib
import json

from sqlalchemy import select

from app import models
from app.core.errors import WorkflowError
from app.schemas.adaptive import Fact, FlowChoice, InterviewState
from app.schemas.alert import AlertSummary
from app.schemas.flow import Flow, Localized
from app.services import intake, normalization, red_flags
from app.services.flow_registry import registry
from app.services.interview_engine import InterviewEngine, validate_answer


def rows(db, session_id):
    return db.scalars(
        select(models.InterviewAnswer)
        .where(models.InterviewAnswer.session_id == session_id)
        .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
    ).all()


def flow_for(db, session_id):
    run = db.get(models.InterviewRun, session_id)
    if run:
        return Flow.model_validate(run.flow_snapshot), run
    if rows(db, session_id):
        return registry()["legacy.intake"], None
    return None, None


def engine_for(db, session_id, flow):
    questions = {q.question_id: q for _, q in flow.questions()}
    facts = {}
    normalized = normalization.for_answers(db, session_id)
    for row in rows(db, session_id):
        if row.question_id.startswith("rag_followup"):
            continue
        question = questions.get(row.question_id)
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
        facts[row.question_id] = Fact(
            answer_id=row.id,
            question_id=row.question_id,
            field=row.field,
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
    res = engine_for(db, session_id, flow).state(
        run.cursor if run else None, run.revision if run else 0
    )
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
    for row in rows(db, session_id):
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
                label=Localized(en="Clinical follow-up", bn="ক্লিনিক্যাল ফলো-আপ", hi="चिकित्सीय अनुवर्ती"),
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

    # If the deterministic state says we are complete and there's no red flag and no missing required,
    # evaluate grounded RAG follow-up candidates
    if res.is_complete and res.red_flag_alert is None and len(res.missing_required) == 0:
        try:
            from app.services.rag_integration import select_next_rag_question
            rag_result = select_next_rag_question(str(session_id), db, flow, res)
            if rag_result is not None:
                rag_question, rag_suggestion = rag_result
                new_res = res.model_copy()
                new_res.is_complete = False
                new_res.question = rag_question
                new_res.rag_suggestions = [rag_suggestion]
                return new_res
        except Exception:
            pass

    return res


def editable(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "Completed answers cannot be changed.")
    return session


def select_flow(db, session_id, payload, user=None):
    editable(db, session_id, user=user)
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
    current_state = engine.state(
        run.cursor if run else None, run.revision if run else 0
    )
    current = current_state.question
    if current is None:
        # Fallback to engine's state question if state.question is None (should not happen)
        current = engine.state(run.cursor).question
    if current is None or current.question_id != payload.question_id:
        active_state = state(db, session_id, user=user)
        if active_state.question and active_state.question.question_id == payload.question_id:
            current = active_state.question
        else:
            raise WorkflowError("QUESTION_NOT_CURRENT", "Reload the current interview question.", 409)
    if payload.language != session.language:
        raise WorkflowError("INVALID_ANSWER", "Answer language must match the session.", 422)
    candidate = None
    if payload.source == "voice":
        from app.services.voice_candidates import verify
        candidate = verify(db, session_id, payload, current)
    elif payload.voice_candidate is not None:
        raise WorkflowError("INVALID_VOICE_CANDIDATE", "Edited answers must be submitted as typed text without a voice token.", 422)
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
                "origin": "rag" if current.question_id.startswith("rag_followup") else "flow",
            },
        )
        db.flush()
    if candidate is not None:
        intake.audit(db, "voice_candidate_confirmed", session_id, user=user, metadata={
            "candidate_id": candidate["id"], "provider": candidate["provider"], "model": candidate["model"],
            "question_id": current.question_id, "language": payload.language,
            "source_answer_id": saved_answer.id if saved_answer is not None else previous.answer_id,
        })
    if not payload.question_id.startswith("rag_followup"):
        run.cursor = engine_for(db, session_id, flow).after(payload.question_id)
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
            status=json.loads(r.value_json).get("status", "answered") if r.value_json else "answered",
            value=json.loads(r.value_json).get("value", r.raw_value) if r.value_json else r.raw_value,
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

    clear_rag_question_cache(session_id)
    return state(db, session_id, user=user)


def navigate(db, session_id, payload, user=None):
    editable(db, session_id, user=user)
    flow, run = require_run(db, session_id)
    check_revision(run, payload.expected_revision)
    engine = engine_for(db, session_id, flow)
    allowed = set(engine.active) | set(engine.pending[:1])
    if payload.question_id not in allowed:
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