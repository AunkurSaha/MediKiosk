"""Read-only deterministic continuity analysis over attributed encounter evidence."""

import json
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.schemas.flow import Localized, Option, Question
from app.services import intake

ELIGIBLE_STATUSES = ("ready_for_review", "under_review", "confirmed")
ACUTE_FIELDS = {"chief_complaint", "chief_complaint.description", "onset_duration"}
RECONFIRM_FIELDS = {"medications", "medications.any", "medications.details", "allergies"}
CONTINUITY_PREFIX = "continuity."


def continuity_question_id(evidence_id: str) -> str:
    return CONTINUITY_PREFIX + evidence_id.replace("-", "")


def _matches_target(field: str, target_field: str) -> bool:
    return (
        field == target_field
        or (target_field.startswith("medications") and field.startswith("medications"))
        or (target_field.startswith("allergies") and field.startswith("allergies"))
    )


def pending_reconfirmation(db: Session, session_id: str, target_field: str):
    """Return one stable historical item for the active matching history field.

    Only a current answer/evidence for the exact candidate suppresses this turn;
    a parent branch answer (for example ``medications.any``) does not.
    """
    if target_field not in {"medications.details", "allergies.details"}:
        return None
    current = current_evidence(db, session_id)
    answered_history = {(row.metadata_json or {}).get("historical_evidence_id") for row in current}
    for row in historical_evidence(db, session_id):
        field, concept = _canonical(row)
        if not _matches_target(field, target_field):
            continue
        if row.id in answered_history:
            continue
        # A stronger current fact for this exact history target wins.
        if any(
            _canonical(candidate)[0] == field
            and not (candidate.metadata_json or {}).get("historical_evidence_id")
            for candidate in current
        ):
            continue
        return row, schemas.ContinuityReconfirmationContext(
            target_field=target_field,
            evidence_id=row.id,
            source_session_id=row.session_id,
            historical_value=row.value_json,
            canonical_field=field,
            concept=concept,
        )
    return None


def _completed_order():
    return (
        func.coalesce(models.Session.completed_at, models.Session.created_at).desc(),
        models.Session.id.desc(),
    )


def get_prior_completed_encounters(db: Session, current_session_id: str) -> list[models.Session]:
    current = intake.get_session(db, current_session_id)
    return list(
        db.scalars(
            select(models.Session)
            .where(
                models.Session.patient_id == current.patient_id,
                models.Session.id != current.id,
                models.Session.status.in_(ELIGIBLE_STATUSES),
            )
            .order_by(*_completed_order())
        ).all()
    )


def get_most_recent_prior_encounter(db: Session, current_session_id: str) -> models.Session | None:
    encounters = get_prior_completed_encounters(db, current_session_id)
    return encounters[0] if encounters else None


def _encounter_date(session: models.Session) -> datetime | None:
    return session.completed_at or session.created_at


def _visit(db: Session, session: models.Session) -> schemas.PriorEncounter:
    hospital = db.get(models.Hospital, session.hospital_id) if session.hospital_id else None
    doctor = db.get(models.User, session.selected_doctor_id) if session.selected_doctor_id else None
    routing = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session.id
        )
    )
    return schemas.PriorEncounter(
        session_id=session.id,
        completed_at=_encounter_date(session),
        facility={"id": hospital.id, "name": hospital.name} if hospital else None,
        doctor={"id": doctor.id, "name": doctor.name} if doctor else None,
        chief_complaint=routing.chief_complaint if routing else None,
        routing_state=routing.routing_state if routing else None,
        suggested_specialty=routing.suggested_specialty if routing else None,
        completion_state=session.status,
    )


def _canonical(row: models.ClinicalEvidence) -> tuple[str, str | None]:
    metadata = row.metadata_json or {}
    field = (
        metadata.get("canonical_field")
        or row.concept_code
        or metadata.get("question_id")
        or row.stable_key
    )
    return str(field), row.concept_code


def _ref(
    row: models.ClinicalEvidence, dates: dict[str, datetime | None]
) -> schemas.ContinuityEvidenceRef:
    field, concept = _canonical(row)
    return schemas.ContinuityEvidenceRef(
        evidence_id=row.id,
        source_session_id=row.session_id,
        source_encounter_date=dates.get(row.session_id),
        source_type=row.source_type,
        canonical_field=field,
        concept=concept,
        value=row.value_json,
        verification_status=row.verification_status,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
        verified_at=row.verified_at,
    )


def historical_evidence(db: Session, current_session_id: str) -> list[models.ClinicalEvidence]:
    encounters = get_prior_completed_encounters(db, current_session_id)
    if not encounters:
        return []
    return list(
        db.scalars(
            select(models.ClinicalEvidence)
            .where(
                models.ClinicalEvidence.session_id.in_([row.id for row in encounters]),
                models.ClinicalEvidence.verification_status.notin_(("REJECTED",)),
            )
            .order_by(models.ClinicalEvidence.created_at.desc(), models.ClinicalEvidence.id.desc())
        ).all()
    )


def _current_evidence(db: Session, session_id: str) -> list[models.ClinicalEvidence]:
    return list(
        db.scalars(
            select(models.ClinicalEvidence)
            .outerjoin(
                models.InterviewAnswer,
                models.ClinicalEvidence.source_id == models.InterviewAnswer.id,
            )
            .where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.verification_status.notin_(("REJECTED",)),
            )
            .order_by(
                func.coalesce(
                    models.InterviewAnswer.created_at, models.ClinicalEvidence.created_at
                ),
                models.ClinicalEvidence.id,
            )
        ).all()
    )


def current_evidence(db: Session, session_id: str) -> list[models.ClinicalEvidence]:
    """Select the latest append-only continuity decision as current truth."""
    evidence = _current_evidence(db, session_id)
    latest_answers = {}
    for row in db.scalars(
        select(models.InterviewAnswer)
        .where(
            models.InterviewAnswer.session_id == session_id,
            models.InterviewAnswer.question_id.startswith(CONTINUITY_PREFIX),
        )
        .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
    ):
        latest_answers[row.question_id] = row.id
    active_ids = set(latest_answers.values())
    return [
        row
        for row in evidence
        if not (row.metadata_json or {}).get("historical_evidence_id")
        or row.source_id in active_ids
        or (row.metadata_json or {}).get("confirmation_answer_id") in active_ids
    ]


def authoritative_interview_answers(db: Session, session_id: str) -> list[models.InterviewAnswer]:
    """Return answers excluding stale continuity-derived configured projections."""
    answers = list(
        db.scalars(
            select(models.InterviewAnswer)
            .where(models.InterviewAnswer.session_id == session_id)
            .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
        ).all()
    )
    latest = {}
    for answer in answers:
        if answer.question_id.startswith(CONTINUITY_PREFIX):
            latest[answer.question_id] = answer.id
    if not latest:
        return answers
    evidence_by_answer = {
        row.source_id: row
        for row in db.scalars(
            select(models.ClinicalEvidence).where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.source_id.in_([answer.id for answer in answers]),
            )
        ).all()
    }
    active_continuity_ids = set(latest.values())
    return [
        answer
        for answer in answers
        if (
            (evidence := evidence_by_answer.get(answer.id)) is None
            or not (evidence.metadata_json or {}).get("confirmation_answer_id")
            or (evidence.metadata_json or {}).get("confirmation_answer_id") in active_continuity_ids
        )
    ]


def reconfirmation_context_for_question(db: Session, session_id: str, question_id: str):
    """Resolve a stable historical question ID when reopening it for correction."""
    if not question_id.startswith(CONTINUITY_PREFIX):
        return None
    compact_id = question_id.removeprefix(CONTINUITY_PREFIX)
    if len(compact_id) != 32:
        return None
    try:
        evidence_id = str(UUID(hex=compact_id))
    except ValueError:
        return None
    for row in historical_evidence(db, session_id):
        if row.id != evidence_id:
            continue
        field, concept = _canonical(row)
        if field == "allergies.details":
            target = "allergies.details"
        elif field == "medications.details":
            target = "medications.details"
        else:
            return None
        return row, schemas.ContinuityReconfirmationContext(
            target_field=target,
            evidence_id=row.id,
            source_session_id=row.session_id,
            historical_value=row.value_json,
            canonical_field=field,
            concept=concept,
        )
    return None


def build_reconfirmation_question(
    evidence: models.ClinicalEvidence, context: schemas.ContinuityReconfirmationContext
) -> Question:
    """The one deterministic question builder for forward and correction paths."""
    display = str(context.historical_value)
    is_allergy = context.target_field.startswith("allergies")
    return Question(
        question_id=continuity_question_id(evidence.id),
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
                        value="changed", label=Localized(en="Changed", bn="পরিবর্তিত", hi="बदल गया")
                    )
                ]
            ),
            Option(value="not_sure", label=Localized(en="Not sure", bn="নিশ্চিত নই", hi="पक्का नहीं")),
        ],
    )


def _value(value):
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def _explicit_negative(row: models.ClinicalEvidence) -> bool:
    value = row.value_json
    if value is False or (
        isinstance(value, str) and value.strip().casefold() in {"no", "none", "stopped"}
    ):
        return True
    return False


def _item(key, historical, current, dates) -> schemas.ContinuityItem:
    historic = [_ref(row, dates) for row in historical]
    present = [_ref(row, dates) for row in current]
    source = historic[0] if historic else None
    field, concept = _canonical((historical or current)[0])
    if not historical:
        status = "NEW"
    elif not current or field in ACUTE_FIELDS:
        status = "HISTORICAL_ONLY"
        present = [] if field in ACUTE_FIELDS else present
    elif any((row.metadata_json or {}).get("continuity_decision") == "not_sure" for row in current):
        status = "UNKNOWN_CURRENT_STATUS"
    elif any(_explicit_negative(row) for row in current):
        status = "CONFLICTED" if "allerg" in field.casefold() else "RESOLVED"
    elif _value(historical[0].value_json) == _value(current[-1].value_json):
        status = "UNCHANGED"
    else:
        status = "CHANGED"
    return schemas.ContinuityItem(
        canonical_field=field,
        concept=concept,
        historical_value=historical[0].value_json if historical else None,
        current_value=current[-1].value_json if current and status != "HISTORICAL_ONLY" else None,
        status=status,
        historical_evidence_refs=historic,
        current_evidence_refs=present,
        source_session_id=source.source_session_id if source else None,
        source_date=source.source_encounter_date if source else None,
    )


def compare_encounter_evidence(db: Session, current_session_id: str) -> schemas.ContinuityChangeSet:
    prior = historical_evidence(db, current_session_id)
    current = current_evidence(db, current_session_id)
    dates = {
        session.id: _encounter_date(session)
        for session in get_prior_completed_encounters(db, current_session_id)
    }
    dates[current_session_id] = intake.get_session(db, current_session_id).created_at
    historical_by_key, current_by_key = defaultdict(list), defaultdict(list)
    for row in prior:
        historical_by_key[_canonical(row)[0]].append(row)
    for row in current:
        current_by_key[_canonical(row)[0]].append(row)
    buckets = {
        "NEW": [],
        "CHANGED": [],
        "UNCHANGED": [],
        "RESOLVED": [],
        "CONFLICTED": [],
        "HISTORICAL_ONLY": [],
        "UNKNOWN_CURRENT_STATUS": [],
    }
    for key in sorted(set(historical_by_key) | set(current_by_key)):
        item = _item(key, historical_by_key[key], current_by_key[key], dates)
        buckets[item.status].append(item)
    return schemas.ContinuityChangeSet(
        new=buckets["NEW"],
        changed=buckets["CHANGED"],
        unchanged=buckets["UNCHANGED"],
        resolved=buckets["RESOLVED"],
        conflicted=buckets["CONFLICTED"],
        historical_unconfirmed=buckets["HISTORICAL_ONLY"],
        unknown_current_status=buckets["UNKNOWN_CURRENT_STATUS"],
    )


def snapshot(db: Session, current_session_id: str) -> schemas.ContinuitySnapshot:
    current = intake.get_session(db, current_session_id)
    prior_sessions = get_prior_completed_encounters(db, current_session_id)
    dates = {row.id: _encounter_date(row) for row in prior_sessions}
    evidence = historical_evidence(db, current_session_id)
    changes = compare_encounter_evidence(db, current_session_id)
    requires = [
        item
        for item in changes.historical_unconfirmed
        if item.canonical_field in RECONFIRM_FIELDS
        or "MEDICATION" in (item.concept or "")
        or "ALLERG" in (item.concept or "")
    ]
    latest = prior_sessions[0] if prior_sessions else None
    historical_refs = [_ref(row, dates) for row in evidence]
    current_date = _encounter_date(current)
    current_refs = [
        _ref(row, {current.id: current_date}) for row in current_evidence(db, current.id)
    ]
    timeline = sorted(
        historical_refs + current_refs,
        key=lambda item: (
            item.source_encounter_date.isoformat() if item.source_encounter_date else "",
            item.created_at.isoformat() if item.created_at else "",
            item.source_session_id,
            item.evidence_id,
        ),
    )
    return schemas.ContinuitySnapshot(
        current_session_id=current.id,
        previous_session_id=latest.id if latest else None,
        previous_visit=_visit(db, latest) if latest else None,
        historical_evidence=historical_refs,
        longitudinal_timeline=timeline,
        changes=changes,
        requires_reconfirmation=requires,
    )
