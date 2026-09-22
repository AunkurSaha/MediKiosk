import hashlib
import json

from sqlalchemy import select

from app import models
from app.core.errors import WorkflowError
from app.services import doctor_matching, intake, location_service
from app.utils.distance import haversine_distance

PROTOCOL_VERSION = "1.1.0"
PREFERRED_CAPABILITIES = ["ICU", "LAB", "IMAGING"]


def _response(row):
    items = sorted(row.recommendations, key=lambda item: item.rank)
    return {
        "id": row.id,
        "session_id": row.session_id,
        "clinical_routing_result_id": row.clinical_routing_result_id,
        "status": row.status,
        "routing_state": row.routing_state,
        "suggested_specialty": row.suggested_specialty,
        "directory_version": row.directory_version,
        "protocol_version": row.protocol_version,
        "required_specialty": row.required_specialty,
        "required_capabilities": row.required_capabilities_json,
        "preferred_capabilities": row.preferred_capabilities_json,
        "generated_at": row.generated_at,
        "recommendations": [
            {
                "facility_id": item.facility_id,
                "facility_name": item.facility.name,
                "rank": item.rank,
                "distance_km": item.distance_km,
                "eligibility_reasons": item.eligibility_reasons_json,
                "ranking_reasons": item.ranking_reasons_json,
                "capabilities": item.facility.capabilities_json or [],
                "emergency_available": item.facility.emergency_available,
            }
            for item in items
        ],
    }


def compute(db, session_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    intake.require_consent(db, session_id)
    if session.journey_mode == "ON_SITE":
        raise WorkflowError(
            "MEDIROUTE_NOT_APPLICABLE",
            "Hospital discovery is skipped because this visit is already on site.",
            409,
        )
    routing = db.scalar(
        select(models.ClinicalRoutingResult).where(
            models.ClinicalRoutingResult.session_id == session_id
        )
    )
    if routing is None:
        raise WorkflowError("RAPID_ROUTING_REQUIRED", "Complete rapid routing first.", 409)
    location = location_service.get(db, session_id, user)
    if location is None:
        raise WorkflowError(
            "LOCATION_REQUIRED", "Choose a location before finding facilities.", 409
        )
    versions = sorted(
        set(
            db.scalars(
                select(models.Hospital.directory_version).where(
                    models.Hospital.active.is_(True), models.Hospital.is_demo.is_(True)
                )
            ).all()
        )
    )
    directory_version = versions[-1] if versions else "demo_facilities_v1"
    required_specialty = routing.suggested_specialty
    required_capabilities = ["EMERGENCY"] if routing.routing_state == "EMERGENCY" else []
    doctor_directory_state = sorted(
        tuple(row)
        for row in db.execute(
            select(
                models.DoctorProfile.doctor_user_id,
                models.DoctorProfile.directory_version,
                models.DoctorProfile.availability_revision,
                models.DoctorProfile.active,
                models.DoctorProfile.accepting_patients,
                models.DoctorProfile.availability_status,
                models.DoctorHospitalMembership.hospital_id,
                models.DoctorHospitalMembership.active,
            ).join(
                models.DoctorHospitalMembership,
                models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id,
            )
        ).all()
    )
    signature = hashlib.sha256(
        json.dumps(
            {
                "routing": routing.id,
                "location": location.id,
                "location_revision": location.revision,
                "directory": directory_version,
                "doctor_directory": doctor_directory_state,
                "protocol": PROTOCOL_VERSION,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = db.scalar(
        select(models.MediRouteResult).where(models.MediRouteResult.input_signature == signature)
    )
    if existing:
        return _response(existing)
    facilities = list(
        db.scalars(
            select(models.Hospital).where(
                models.Hospital.active.is_(True),
                models.Hospital.is_demo.is_(True),
                models.Hospital.directory_version == directory_version,
                models.Hospital.opening_status != "CLOSED",
            )
        ).all()
    )
    eligible = []
    for facility in facilities:
        capabilities = set(facility.capabilities_json or [])
        if required_specialty not in capabilities:
            continue
        if any(cap not in capabilities for cap in required_capabilities):
            continue
        if routing.routing_state == "EMERGENCY" and not facility.emergency_available:
            continue
        if (
            routing.routing_state != "EMERGENCY"
            and not doctor_matching.eligible_doctor_ids_for_facility(
                db, facility.id, required_specialty
            )
        ):
            continue
        distance_km = None
        if (
            location.latitude is not None
            and location.longitude is not None
            and facility.latitude is not None
            and facility.longitude is not None
        ):
            distance_km = haversine_distance(
                location.latitude, location.longitude, facility.latitude, facility.longitude
            )
        optional = len(capabilities.intersection(PREFERRED_CAPABILITIES))
        score = (
            optional * 10
            + (5 if facility.opening_status == "OPEN" else 0)
            - (distance_km or 0) / 100
        )
        eligible.append((facility, distance_km, score))
    eligible.sort(key=lambda item: (-item[2], item[1] is None, item[1] or 0, item[0].id))
    result = models.MediRouteResult(
        session_id=session_id,
        patient_id=session.patient_id,
        clinical_routing_result_id=routing.id,
        location_id=location.id,
        routing_state=routing.routing_state,
        suggested_specialty=routing.suggested_specialty,
        directory_version=directory_version,
        protocol_version=PROTOCOL_VERSION,
        input_signature=signature,
        required_specialty=required_specialty,
        required_capabilities_json=required_capabilities,
        preferred_capabilities_json=PREFERRED_CAPABILITIES,
        status="COMPLETED" if eligible else "NO_ELIGIBLE_FACILITY",
    )
    db.add(result)
    db.flush()
    for rank, (facility, distance, score) in enumerate(eligible, 1):
        eligibility = ["ACTIVE_FACILITY", "REQUIRED_SPECIALTY_AVAILABLE"]
        if routing.routing_state != "EMERGENCY":
            eligibility.append("ELIGIBLE_DOCTOR_AVAILABLE")
        if required_capabilities:
            eligibility.append("REQUIRED_CAPABILITY_AVAILABLE")
        if routing.routing_state == "EMERGENCY":
            eligibility.append("EMERGENCY_CAPABLE")
        ranking = ["OPEN"] if facility.opening_status == "OPEN" else []
        if distance is not None:
            ranking.append("CLOSER_ELIGIBLE_OPTION")
        db.add(
            models.MediRouteRecommendation(
                mediroute_result_id=result.id,
                facility_id=facility.id,
                rank=rank,
                distance_km=distance,
                score=score,
                eligibility_reasons_json=eligibility,
                ranking_reasons_json=ranking,
            )
        )
    intake.audit(
        db,
        "mediroute_generated",
        session_id,
        user=user,
        metadata={
            "result_id": result.id,
            "status": result.status,
            "directory_version": directory_version,
        },
    )
    db.commit()
    db.refresh(result)
    return _response(result)


def select_facility(db, session_id, facility_id, user=None):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    current = compute(db, session_id, user)
    result = db.get(models.MediRouteResult, current["id"])
    if result is None or not any(
        item.facility_id == facility_id for item in result.recommendations
    ):
        raise WorkflowError(
            "FACILITY_NOT_ELIGIBLE", "Choose an eligible recommended facility.", 422
        )
    session.hospital_id = facility_id
    session.selected_doctor_id = None
    session.updated_at = intake.now()
    intake.audit(
        db,
        "facility_selected",
        session_id,
        user=user,
        metadata={"facility_id": facility_id, "mediroute_result_id": result.id},
    )
    db.commit()
    db.refresh(session)
    return session
