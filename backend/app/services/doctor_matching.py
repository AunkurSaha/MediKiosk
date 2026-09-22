import hashlib
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, or_, select

from app import models
from app.core.errors import WorkflowError
from app.services import intake

PROTOCOL_VERSION = "1.1.0"
CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "ai" / "doctor_matching" / "compatibility_v1.json"
)
TRUSTED_EVIDENCE = {"PATIENT_CONFIRMED", "CLINICIAN_VERIFIED"}


def eligible_doctor_ids_for_facility(db, facility_id: str, required_specialty: str) -> set[str]:
    """Return doctors that can actually be offered by the matching workflow."""
    allowed = set(compatibility()["specialties"].get(required_specialty, {}).get("eligible", []))
    if not allowed:
        return set()
    return set(
        db.scalars(
            select(models.DoctorProfile.doctor_user_id)
            .join(models.User, models.User.id == models.DoctorProfile.doctor_user_id)
            .join(
                models.DoctorHospitalMembership,
                models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id,
            )
            .outerjoin(
                models.DoctorSpecialtyMembership,
                models.DoctorSpecialtyMembership.doctor_id == models.DoctorProfile.doctor_user_id,
            )
            .where(
                models.DoctorHospitalMembership.hospital_id == facility_id,
                models.DoctorHospitalMembership.active.is_(True),
                models.User.is_active.is_(True),
                models.DoctorProfile.active.is_(True),
                models.DoctorProfile.accepting_patients.is_(True),
                models.DoctorProfile.availability_status != "OFF_DUTY",
                or_(
                    models.DoctorProfile.primary_specialty.in_(allowed),
                    models.DoctorSpecialtyMembership.specialty_code.in_(allowed),
                ),
            )
            .distinct()
        ).all()
    )


@lru_cache(maxsize=1)
def compatibility():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _current_mediroute(db, session_id, facility_id):
    row = db.scalar(
        select(models.MediRouteResult)
        .where(models.MediRouteResult.session_id == session_id)
        .order_by(models.MediRouteResult.generated_at.desc(), models.MediRouteResult.id.desc())
    )
    return (
        row
        if row and any(item.facility_id == facility_id for item in row.recommendations)
        else None
    )


def _directory_state(db, facility_id):
    profiles = db.scalars(
        select(models.DoctorProfile)
        .join(models.User, models.User.id == models.DoctorProfile.doctor_user_id)
        .join(
            models.DoctorHospitalMembership,
            models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id,
        )
        .where(
            models.DoctorHospitalMembership.hospital_id == facility_id,
            models.User.is_active.is_(True),
        )
        .order_by(models.DoctorProfile.doctor_user_id)
    ).all()
    versions = sorted({profile.directory_version for profile in profiles})
    state = sorted(
        (
            p.doctor_user_id,
            p.directory_version,
            p.availability_revision,
            p.active,
            p.accepting_patients,
            p.primary_specialty,
            p.availability_status,
            p.years_of_experience,
            p.expertise_tags_json,
            p.languages_json,
            m.active,
        )
        for p in profiles
        for m in db.scalars(
            select(models.DoctorHospitalMembership).where(
                models.DoctorHospitalMembership.doctor_id == p.doctor_user_id,
                models.DoctorHospitalMembership.hospital_id == facility_id,
            )
        )
    )
    return profiles, versions[-1] if versions else "unversioned", state


def _continuity_score(db, patient_id: str, doctor_id: str) -> int:
    """Return a continuity score based on number of completed sessions with the doctor."""
    completed_sessions = db.scalar(
        select(func.count(models.Session.id)).where(
            models.Session.patient_id == patient_id,
            models.Session.selected_doctor_id == doctor_id,
            models.Session.status == "confirmed",
        )
    )
    # Cap at 5 sessions for scoring purposes
    capped = min(completed_sessions or 0, 5)
    # Score 0 to 10: 0 for 0 sessions, 10 for 5 or more sessions
    return (capped * 10) // 5 if capped > 0 else 0


def _response(db, result):
    rows = db.execute(
        select(models.DoctorMatchRecommendation, models.DoctorProfile)
        .join(
            models.DoctorProfile,
            models.DoctorProfile.doctor_user_id == models.DoctorMatchRecommendation.doctor_id,
        )
        .where(models.DoctorMatchRecommendation.doctor_match_result_id == result.id)
        .order_by(models.DoctorMatchRecommendation.rank, models.DoctorMatchRecommendation.doctor_id)
    ).all()
    return {
        "id": result.id,
        "session_id": result.session_id,
        "facility_id": result.facility_id,
        "required_specialty": result.required_specialty,
        "directory_version": result.directory_version,
        "protocol_version": result.protocol_version,
        "status": result.status,
        "selected_doctor_id": result.selected_doctor_id,
        "generated_at": result.generated_at,
        "recommendations": [
            {
                "doctor_id": profile.doctor_user_id,
                "name": profile.display_name,
                "qualification": profile.qualification,
                "primary_specialty": profile.primary_specialty,
                "expertise_tags": profile.expertise_tags_json or [],
                "languages": profile.languages_json or [],
                "availability_status": profile.availability_status,
                "years_of_experience": profile.years_of_experience,
                "rank": recommendation.rank,
                "recommended": recommendation.rank == 1,
                "eligibility_reasons": recommendation.eligibility_reasons_json or [],
                "ranking_reasons": recommendation.ranking_reasons_json or [],
            }
            for recommendation, profile in rows
        ],
    }


def compute(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    routing = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session_id
        )
    )
    if routing is None:
        raise WorkflowError("RAPID_ROUTING_REQUIRED", "Complete rapid routing first.", 409)
    if not session.hospital_id:
        raise WorkflowError("FACILITY_REQUIRED", "Select a facility before finding a doctor.", 409)
    mediroute = None
    if session.journey_mode == "PRE_ARRIVAL":
        mediroute = _current_mediroute(db, session_id, session.hospital_id)
        if mediroute is None:
            raise WorkflowError(
                "FACILITY_NOT_ELIGIBLE",
                "The selected facility is not in the current recommendation set.",
                409,
            )
        if mediroute.clinical_routing_result_id != routing.id:
            raise WorkflowError(
                "FACILITY_NOT_ELIGIBLE",
                "Refresh facility recommendations for the current routing.",
                409,
            )
    else:
        hospital = db.get(models.Hospital, session.hospital_id)
        if hospital is None or not hospital.active:
            raise WorkflowError(
                "FACILITY_NOT_AVAILABLE",
                "Confirm the hospital where you are currently located.",
                409,
            )
    profiles, directory_version, availability_revision = _directory_state(db, session.hospital_id)
    signature = hashlib.sha256(
        json.dumps(
            {
                "routing": routing.id,
                "routing_state": routing.routing_state,
                "specialty": routing.suggested_specialty,
                "complaint": routing.chief_complaint,
                "routing_protocol": routing.protocol_version,
                "session": session.id,
                "journey_mode": session.journey_mode,
                "mediroute": mediroute.id if mediroute else None,
                "facility": session.hospital_id,
                "directory": directory_version,
                "availability": availability_revision,
                "protocol": PROTOCOL_VERSION,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = db.scalar(
        select(models.DoctorMatchResult).where(
            models.DoctorMatchResult.input_signature == signature
        )
    )
    if existing is not None:
        if session.selected_doctor_id != existing.selected_doctor_id:
            session.selected_doctor_id = existing.selected_doctor_id
            db.commit()
        return _response(db, existing)
    session.selected_doctor_id = None
    status = (
        "DOCTOR_MATCHING_BYPASSED_EMERGENCY"
        if routing.routing_state == "EMERGENCY"
        else "COMPLETED"
    )
    result = models.DoctorMatchResult(
        session_id=session.id,
        patient_id=session.patient_id,
        clinical_routing_result_id=routing.id,
        mediroute_result_id=mediroute.id if mediroute else None,
        facility_id=session.hospital_id,
        required_specialty=routing.suggested_specialty,
        directory_version=directory_version,
        protocol_version=PROTOCOL_VERSION,
        input_signature=signature,
        status=status,
    )
    db.add(result)
    db.flush()
    if routing.routing_state != "EMERGENCY":
        eligible_doctor_ids = eligible_doctor_ids_for_facility(
            db, session.hospital_id, routing.suggested_specialty
        )
        expertise_targets = set(
            compatibility()["complaint_expertise"].get(routing.chief_complaint, [])
        )
        eligible = []
        memberships = set(
            db.scalars(
                select(models.DoctorHospitalMembership.doctor_id).where(
                    models.DoctorHospitalMembership.hospital_id == session.hospital_id,
                    models.DoctorHospitalMembership.active.is_(True),
                )
            ).all()
        )
        for profile in profiles:
            if (
                profile.doctor_user_id not in eligible_doctor_ids
                or profile.doctor_user_id not in memberships
                or not profile.active
                or not profile.accepting_patients
            ):
                continue
            expertise = sorted(expertise_targets.intersection(profile.expertise_tags_json or []))
            language_match = session.language in (profile.languages_json or [])
            experience = min(max(profile.years_of_experience or 0, 0), 20)
            availability = {"AVAILABLE": 10, "BUSY": 4, "UNKNOWN": 0}.get(
                profile.availability_status, 0
            )
            continuity = _continuity_score(db, session.patient_id, profile.doctor_user_id)
            components = {
                "clinical_specialty": 35,
                "expertise": 20 if expertise else 0,
                "availability": availability,
                "continuity": continuity,
                "experience": round(experience / 20 * 6),
                "language": 3 if language_match else 0,
            }
            total_score = sum(components.values())
            reasons = ["SPECIALTY_MATCH"]
            ranking = []
            if expertise:
                ranking.append("RELEVANT_EXPERTISE")
            if profile.availability_status == "AVAILABLE":
                ranking.append("AVAILABLE_FOR_CONSULTATION")
            if language_match:
                ranking.append("LANGUAGE_MATCH")
            if experience:
                ranking.append("EXPERIENCE_RELEVANT")
            if continuity:
                ranking.append("CONTINUITY_RELEVANT")
            eligible.append((profile, total_score, reasons, ranking, components))
        eligible.sort(key=lambda item: (-item[1], item[0].doctor_user_id))
        if not eligible:
            result.status = "NO_ELIGIBLE_DOCTOR"
        for rank, (profile, score, reasons, ranking, components) in enumerate(eligible, 1):
            db.add(
                models.DoctorMatchRecommendation(
                    doctor_match_result_id=result.id,
                    doctor_id=profile.doctor_user_id,
                    rank=rank,
                    score=score,
                    eligibility_reasons_json=[
                        "FACILITY_MATCH",
                        "ACTIVE",
                        "ACCEPTING_PATIENTS",
                        "CONSULTATION_TYPE_MATCH",
                        *reasons,
                    ],
                    ranking_reasons_json=ranking,
                    score_components_json=components,
                )
            )
    intake.audit(
        db,
        "doctor_recommendations_generated",
        session.id,
        user=user,
        metadata={
            "match_result_id": result.id,
            "facility_id": session.hospital_id,
            "journey_mode": session.journey_mode,
            "protocol_version": PROTOCOL_VERSION,
            "status": result.status,
        },
    )
    db.commit()
    db.refresh(result)
    return _response(db, result)


def select_doctor(db, session_id, doctor_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if session.status != "intake" or db.scalar(
        select(models.DoctorQueueEntry.id).where(models.DoctorQueueEntry.session_id == session.id)
    ):
        raise WorkflowError(
            "QUEUE_ASSIGNMENT_LOCKED", "Submitted visit assignment cannot be changed.", 409
        )
    response = compute(db, session_id, user)
    if response["status"] != "COMPLETED" or doctor_id not in {
        item["doctor_id"] for item in response["recommendations"]
    }:
        raise WorkflowError("DOCTOR_NOT_ELIGIBLE", "Choose an eligible recommended doctor.", 422)
    profile = db.get(models.DoctorProfile, doctor_id)
    doctor_user = db.get(models.User, doctor_id)
    membership = db.scalar(
        select(models.DoctorHospitalMembership).where(
            models.DoctorHospitalMembership.doctor_id == doctor_id,
            models.DoctorHospitalMembership.hospital_id == session.hospital_id,
            models.DoctorHospitalMembership.active.is_(True),
        )
    )
    if (
        profile is None
        or doctor_user is None
        or not doctor_user.is_active
        or not profile.active
        or not profile.accepting_patients
        or membership is None
    ):
        raise WorkflowError("DOCTOR_NOT_ELIGIBLE", "Choose an eligible recommended doctor.", 422)
    result = db.get(models.DoctorMatchResult, response["id"])
    session.selected_doctor_id = doctor_id
    session.updated_at = intake.now()
    result.selected_doctor_id = doctor_id
    result.selected_at = intake.now()
    intake.audit(
        db,
        "doctor_selected",
        session.id,
        user=user,
        metadata={
            "match_result_id": result.id,
            "doctor_id": doctor_id,
            "facility_id": session.hospital_id,
        },
    )
    db.commit()
    db.refresh(result)
    return _response(db, result)
