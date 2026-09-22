"""Deterministic, evidence-aware rapid clinical routing.

This subsystem establishes urgency and a broad care path. It does not diagnose,
rank facilities/doctors, or replace the full clinical interview.
"""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from app import models
from app.core.errors import WorkflowError
from app.domain.clinical_safety import (
    TRUSTED_HISTORY_STATUSES,
    CareRoutingState,
    EvidenceSourceType,
    EvidenceVerificationStatus,
)
from app.schemas.adaptive import Fact
from app.schemas.clinical_evidence import ClinicalEvidenceCreate
from app.schemas.flow import Localized
from app.schemas.rapid_routing import (
    ComplaintMapping,
    RapidQuestion,
    RapidRoutingResultRead,
    RapidRoutingState,
)
from app.services import clinical_evidence, intake, red_flags
from app.services.flow_registry import registry

CONFIG_PATH = Path(__file__).resolve().parents[3] / "ai" / "rapid_routing" / "questions_v1.json"

FLOW_BY_COMPLAINT = {
    "CHEST_DISCOMFORT": "chest_pain",
    "FEVER": "fever",
    "HEADACHE": "headache",
    "BREATHING_DIFFICULTY": "cough_breathlessness",
    "ABDOMINAL_PAIN": "abdominal_pain",
    "COUGH": "cough_breathlessness",
    "JOINT_PAIN": "joint_pain",
    "OTHER": "other_complaint",
}

KEYWORDS = {
    "CHEST_DISCOMFORT": ("chest", "বুক", "सीन", "छाती"),
    "BREATHING_DIFFICULTY": ("breath", "শ্বাস", "सांस"),
    "ABDOMINAL_PAIN": ("stomach", "abdominal", "vomit", "পেট", "বমি", "पेट", "उल्टी"),
    "FEVER": ("fever", "temperature", "জ্বর", "बुखार"),
    "HEADACHE": ("headache", "head pain", "মাথাব্যথা", "सिरदर्द"),
    "COUGH": ("cough", "কাশি", "खांसी"),
    "SKIN_PROBLEM": ("skin", "rash", "চামড়া", "फुंसी", "त्वचा"),
    "INJURY": ("injury", "hurt", "accident", "আঘাত", "चोट"),
    "JOINT_PAIN": ("joint", "knee", "জয়েন্ট", "হাঁটু", "जोड़", "घुटना"),
}


@lru_cache(maxsize=1)
def config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _authorized(db, session_id, user):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    if session.status != "intake":
        raise WorkflowError("SESSION_LOCKED", "Completed intake routing cannot be changed.", 409)
    return session


def _run(db, session, create=False):
    run = db.get(models.RapidRoutingRun, session.id)
    if run is None and create:
        run = models.RapidRoutingRun(session_id=session.id, patient_id=session.patient_id)
        db.add(run)
        db.flush()
    return run


def map_complaint(db, session_id, payload, user=None):
    session = _authorized(db, session_id, user)
    run = _run(db, session, True)
    voice_metadata = {}
    if payload.source == "voice":
        from app.services.voice_candidates import verify_rapid_complaint

        candidate = verify_rapid_complaint(db, session_id, payload, run.revision)
        voice_metadata = {
            "asr_candidate_id": candidate["id"],
            "asr_provider": candidate["provider"],
            "asr_model": candidate["model"],
        }
    text = payload.translated_text or payload.original_text
    folded = text.casefold()
    category = "OTHER"
    for candidate, words in KEYWORDS.items():
        if any(word.casefold() in folded for word in words):
            category = candidate
            break
    mapping = ComplaintMapping(
        original_text=payload.original_text,
        translated_text=payload.translated_text,
        language=payload.language,
        source=payload.source,
        candidate_category=category,
        mapping_provider="deterministic_keyword_v1",
        confidence=None,
        patient_confirmed=False,
    )
    run.complaint_input_json = mapping.model_dump(mode="json") | {
        "voice_candidate_present": bool(payload.voice_candidate),
        **voice_metadata,
    }
    run.chief_complaint = None
    run.complaint_confirmed_at = None
    run.revision += 1
    run.updated_at = intake.now()
    intake.audit(
        db,
        "chief_complaint_mapped",
        session_id,
        user=user,
        metadata={"candidate": category, "provider": mapping.mapping_provider},
    )
    db.commit()
    return state(db, session_id, user)


def confirm_complaint(db, session_id, payload, user=None):
    session = _authorized(db, session_id, user)
    run = _run(db, session, True)
    if run.revision != payload.expected_revision:
        raise WorkflowError(
            "RAPID_ROUTING_CONFLICT", "Routing changed. Reload before continuing.", 409
        )
    raw = dict(run.complaint_input_json or {})
    if not raw:
        raw = {
            "original_text": payload.category,
            "translated_text": None,
            "language": session.language,
            "source": "card",
            "mapping_provider": "patient_card",
            "confidence": None,
        }
    run.chief_complaint = payload.category
    run.complaint_confirmed_at = intake.now()
    run.revision += 1
    run.updated_at = intake.now()
    evidence = clinical_evidence.create_evidence(
        db,
        ClinicalEvidenceCreate(
            patient_id=session.patient_id,
            session_id=session.id,
            concept_code="CHIEF_COMPLAINT",
            value=payload.category,
            source_type=EvidenceSourceType.PATIENT_VOICE
            if raw.get("source") == "voice"
            else EvidenceSourceType.PATIENT_TEXT,
            source_id=session.id,
            stable_key="rapid_chief_complaint",
            original_text=raw.get("original_text"),
            translated_text=raw.get("translated_text"),
            language=raw.get("language", session.language),
            verification_status=EvidenceVerificationStatus.PATIENT_CONFIRMED,
            metadata={
                "mapping_provider": raw.get("mapping_provider", "patient_card"),
                "mapping_confidence": raw.get("confidence"),
                "input_source": raw.get("source", "card"),
                "patient_confirmed": True,
                "voice_candidate_present": raw.get("voice_candidate_present", False),
                "asr_candidate_id": raw.get("asr_candidate_id"),
                "asr_provider": raw.get("asr_provider"),
                "asr_model": raw.get("asr_model"),
            },
        ),
    )
    intake.audit(
        db,
        "chief_complaint_confirmed",
        session_id,
        user=user,
        metadata={"category": payload.category, "evidence_id": evidence.id},
    )
    db.commit()
    return state(db, session_id, user)


def _questions(run):
    definition = config()["complaints"][run.chief_complaint]
    return [RapidQuestion(**q, version=config()["version"]) for q in definition["questions"]]


def _answer_rows(db, session_id):
    return list(
        db.scalars(
            select(models.InterviewAnswer)
            .where(
                models.InterviewAnswer.session_id == session_id,
                models.InterviewAnswer.question_id.like("rapid.%"),
            )
            .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
        ).all()
    )


def _trusted_evidence_fields(db, session_id):
    result = set()
    for row in clinical_evidence.list_for_encounter(db, session_id):
        if EvidenceVerificationStatus(row.verification_status) not in TRUSTED_HISTORY_STATUSES:
            continue
        metadata = row.metadata_json or {}
        if metadata.get("answer_status", "answered") != "answered":
            continue
        if metadata.get("canonical_field"):
            result.add(metadata["canonical_field"])
        if row.concept_code:
            result.add(f"concept:{row.concept_code}")
    return result


def _result_read(row):
    return RapidRoutingResultRead(
        id=row.id,
        session_id=row.session_id,
        chief_complaint=row.chief_complaint,
        routing_state=row.routing_state,
        suggested_specialty=row.suggested_specialty,
        triggered_red_flags=row.triggered_rule_ids_json or [],
        supporting_evidence_ids=row.supporting_evidence_ids_json or [],
        questions_asked=row.questions_asked_json or [],
        questions_skipped=row.questions_skipped_json or [],
        completed_at=row.completed_at,
        routing_protocol_version=row.protocol_version,
    )


def state(db, session_id, user=None):
    session = _authorized(db, session_id, user)
    run = _run(db, session, False)
    if run is None or not run.complaint_input_json:
        return RapidRoutingState(phase="chief_complaint", revision=run.revision if run else 0)
    if not run.chief_complaint:
        mapping_data = {
            key: value
            for key, value in run.complaint_input_json.items()
            if key in ComplaintMapping.model_fields
        }
        return RapidRoutingState(
            phase="confirm_complaint",
            revision=run.revision,
            mapping=ComplaintMapping.model_validate(mapping_data),
        )
    existing_result = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session_id
        )
    )
    answers = _answer_rows(db, session_id)
    asked = [a.question_id for a in answers]
    trusted = _trusted_evidence_fields(db, session_id)
    questions = _questions(run)
    skipped = [
        q.question_id
        for q in questions
        if q.question_id not in asked
        and any(field in trusted for field in [q.target_field, *q.equivalent_fields])
    ]
    if existing_result:
        return RapidRoutingState(
            phase="result",
            revision=run.revision,
            chief_complaint=run.chief_complaint,
            questions_asked=asked,
            questions_skipped=skipped,
            result=_result_read(existing_result),
        )
    current = next(
        (q for q in questions if q.question_id not in asked and q.question_id not in skipped), None
    )
    if current is None:
        return _finalize(db, session, run, answers, skipped)
    return RapidRoutingState(
        phase="rapid_interview",
        revision=run.revision,
        chief_complaint=run.chief_complaint,
        question=current,
        questions_asked=asked,
        questions_skipped=skipped,
    )


def submit_answer(db, session_id, payload, user=None):
    session = _authorized(db, session_id, user)
    run = _run(db, session, False)
    if run is None or not run.chief_complaint:
        raise WorkflowError(
            "COMPLAINT_CONFIRMATION_REQUIRED", "Confirm the chief complaint first.", 409
        )
    if run.revision != payload.expected_revision:
        raise WorkflowError(
            "RAPID_ROUTING_CONFLICT", "Routing changed. Reload before continuing.", 409
        )
    current = state(db, session_id, user).question
    if current is None or current.question_id != payload.question_id:
        raise WorkflowError(
            "QUESTION_NOT_CURRENT", "Reload the current rapid-routing question.", 409
        )
    if payload.language != session.language:
        raise WorkflowError("INVALID_ANSWER", "Answer language must match the session.", 422)
    value = payload.value
    if current.input_type == "boolean" and type(value) is not bool:
        raise WorkflowError("INVALID_ANSWER", "Choose yes or no.", 422)
    if current.input_type == "severity" and (type(value) is not int or not 0 <= value <= 10):
        raise WorkflowError("INVALID_ANSWER", "Severity must be an integer from 0 to 10.", 422)
    if current.input_type == "number" and type(value) not in (int, float):
        raise WorkflowError("INVALID_ANSWER", "Enter a number.", 422)
    stored_value = (
        "constant"
        if current.target_field == "hpi.timing" and value is True
        else ("intermittent" if current.target_field == "hpi.timing" else value)
    )
    answer = models.InterviewAnswer(
        session_id=session_id,
        question_id=current.question_id,
        field=current.target_field,
        value_json=json.dumps({"status": "answered", "value": stored_value}),
        raw_value=payload.raw_value,
        source=payload.source,
        language=payload.language,
        verification_status="patient_reported",
        created_at=intake.now(),
    )
    db.add(answer)
    db.flush()
    evidence = clinical_evidence.create_patient_answer_evidence(
        db,
        answer,
        value=stored_value,
        answer_status="answered",
        voice_metadata={"voice_candidate_present": bool(payload.voice_candidate)}
        if payload.source == "voice"
        else None,
    )
    evidence.concept_code = current.concept_code
    run.revision += 1
    run.updated_at = intake.now()
    intake.audit(
        db,
        "rapid_routing_answer_recorded",
        session_id,
        user=user,
        metadata={"question_id": current.question_id, "evidence_id": evidence.id},
    )
    db.commit()
    return state(db, session_id, user)


def _facts(db, session, run, answers):
    facts = []
    for row in answers:
        question = next(q for q in _questions(run) if q.question_id == row.question_id)
        value = json.loads(row.value_json)["value"]
        facts.append(
            Fact(
                answer_id=row.id,
                question_id=row.question_id,
                field=row.field,
                label=question.prompt,
                status="answered",
                value=value,
                raw_value=row.raw_value,
                source=row.source,
                language=row.language,
                recorded_at=row.created_at,
            )
        )
        if question.concept_code in {"DYSPNEA", "VOMITING"} and value is True:
            word = "shortness of breath" if question.concept_code == "DYSPNEA" else "vomiting"
            facts.append(
                Fact(
                    answer_id=row.id,
                    question_id=row.question_id,
                    field="chief_complaint.description",
                    label=question.prompt,
                    status="answered",
                    value=word,
                    raw_value=word,
                    source=row.source,
                    language="en",
                    recorded_at=row.created_at,
                )
            )
    if run.chief_complaint == "BREATHING_DIFFICULTY":
        facts.append(
            Fact(
                answer_id=session.id,
                question_id="rapid.complaint",
                field="hpi.symptom",
                label=Localized(en="Chief complaint", bn="প্রধান সমস্যা", hi="मुख्य शिकायत"),
                status="answered",
                value="breathlessness",
                raw_value="breathlessness",
                source="touch",
                language="en",
                recorded_at=run.complaint_confirmed_at,
            )
        )
    return facts


def _finalize(db, session, run, answers, skipped):
    definition = config()["complaints"][run.chief_complaint]
    alerts = red_flags.evaluate_and_persist(
        db, session.id, definition.get("flow_id") or "*", _facts(db, session, run, answers)
    )
    active = [a for a in alerts if a.status in ("new", "acknowledged")]
    if any(a.priority == "emergency" for a in active):
        routing = CareRoutingState.EMERGENCY
    elif active:
        routing = CareRoutingState.URGENT
    elif run.chief_complaint == "SKIN_PROBLEM":
        routing = CareRoutingState.TELECONSULT_MAY_BE_SUITABLE
    else:
        routing = CareRoutingState.ROUTINE_OPD
    evidence_ids = list(
        db.scalars(
            select(models.ClinicalEvidence.id).where(
                models.ClinicalEvidence.session_id == session.id,
                models.ClinicalEvidence.source_id.in_([session.id, *[a.id for a in answers]]),
            )
        ).all()
    )
    # Emergency is a care-routing state, not a medical specialty. Preserve the
    # broad specialty inferred from the confirmed complaint independently.
    specialty = definition["specialty"]
    result = models.ClinicalRoutingResult(
        session_id=session.id,
        patient_id=session.patient_id,
        chief_complaint=run.chief_complaint,
        routing_state=routing.value,
        suggested_specialty=specialty,
        protocol_version=run.protocol_version,
        supporting_evidence_ids_json=evidence_ids,
        triggered_rule_ids_json=[a.rule_id for a in active],
        questions_asked_json=[a.question_id for a in answers],
        questions_skipped_json=skipped,
        completed_at=intake.now(),
    )
    db.add(result)
    db.flush()
    if routing != CareRoutingState.EMERGENCY:
        flow_id = FLOW_BY_COMPLAINT.get(run.chief_complaint)
        flow = registry().get(flow_id) if flow_id else None
        if flow is not None and db.get(models.InterviewRun, session.id) is None:
            flow_snapshot = flow.model_dump(mode="json")
            db.add(
                models.InterviewRun(
                    session_id=session.id,
                    flow_id=flow.flow_id,
                    flow_version=flow.version,
                    flow_snapshot=flow_snapshot,
                    cursor=flow_snapshot["sections"][0]["questions"][0]["question_id"],
                    revision=0,
                )
            )
            intake.audit(
                db,
                "interview_flow_selected",
                session.id,
                metadata={
                    "flow_id": flow.flow_id,
                    "version": flow.version,
                    "source": "rapid_routing",
                },
            )
    run.revision += 1
    run.updated_at = intake.now()
    intake.audit(
        db,
        "rapid_routing_completed",
        session.id,
        metadata={
            "routing_state": routing.value,
            "suggested_specialty": specialty,
            "triggered_rule_ids": result.triggered_rule_ids_json,
        },
    )
    db.commit()
    db.refresh(result)
    return RapidRoutingState(
        phase="result",
        revision=run.revision,
        chief_complaint=run.chief_complaint,
        questions_asked=result.questions_asked_json,
        questions_skipped=skipped,
        result=_result_read(result),
    )
