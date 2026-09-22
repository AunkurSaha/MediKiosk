from uuid import uuid4

from sqlalchemy import func, select

from app import models
from app.core.errors import WorkflowError
from app.schemas.patient_routing_location import PatientRoutingLocationCreate
from app.services import location_service, mediroute
from app.utils.distance import haversine_distance


def _session(database, *, specialty="CARDIOLOGY", routing_state="ROUTINE_OPD"):
    patient = models.Patient(id=str(uuid4()), name="MediRoute Patient")
    session = models.Session(
        id=str(uuid4()),
        patient_id=patient.id,
        hospital_token="ROUTE-1",
        language="en",
        status="intake",
    )
    database.add_all([patient, session])
    database.flush()
    database.add_all(
        [
            models.Consent(
                session_id=session.id,
                voice_processing=False,
                document_processing=False,
                share_with_doctor=True,
            ),
            models.ClinicalRoutingResult(
                session_id=session.id,
                patient_id=patient.id,
                chief_complaint="CHEST_DISCOMFORT",
                routing_state=routing_state,
                suggested_specialty=specialty,
                protocol_version="1.0.0",
                supporting_evidence_ids_json=[],
                triggered_rule_ids_json=[],
                questions_asked_json=[],
                questions_skipped_json=[],
                completed_at=mediroute.intake.now(),
            ),
        ]
    )
    database.commit()
    return session


def _facility(
    database, code, capabilities, *, active=True, emergency=False, lat=None, lon=None, doctor=True
):
    row = models.Hospital(
        code=code,
        name=f"Facility {code}",
        active=active,
        is_demo=True,
        opening_status="OPEN",
        directory_version="demo_facilities_v1",
        capabilities_json=capabilities,
        emergency_available=emergency,
        latitude=lat,
        longitude=lon,
    )
    database.add(row)
    database.commit()
    clinical_specialties = [
        item for item in capabilities if item not in {"EMERGENCY", "ICU", "LAB", "IMAGING"}
    ]
    if doctor and clinical_specialties:
        doctor_id = str(uuid4())
        database.add(
            models.User(id=doctor_id, name=f"Doctor {code}", role="doctor", is_active=True)
        )
        database.flush()
        database.add(
            models.DoctorProfile(
                doctor_user_id=doctor_id,
                display_name=f"Doctor {code}",
                primary_specialty=clinical_specialties[0],
                availability_status="AVAILABLE",
                active=True,
                accepting_patients=True,
            )
        )
        database.flush()
        database.add(
            models.DoctorHospitalMembership(doctor_id=doctor_id, hospital_id=row.id, active=True)
        )
        database.commit()
    return row


def _location(database, session, **overrides):
    values = {"source": "MANUAL_LOCALITY", "locality": "Kolkata"} | overrides
    return location_service.save(database, session.id, PatientRoutingLocationCreate(**values))


def test_location_sources_persist_and_revision_does_not_audit_coordinates(database):
    session = _session(database)
    first = _location(
        database,
        session,
        source="BROWSER_GEOLOCATION",
        locality=None,
        latitude=22.57,
        longitude=88.36,
        precision="browser",
    )
    assert first.revision == 1
    second = _location(
        database,
        session,
        source="MANUAL_POSTAL_CODE",
        locality=None,
        latitude=None,
        longitude=None,
        postal_code="700001",
        precision=None,
    )
    assert second.id == first.id
    assert second.revision == 2
    audit = database.scalar(
        select(models.AuditLog)
        .where(models.AuditLog.action == "routing_location_saved")
        .order_by(models.AuditLog.created_at.desc())
    )
    assert "latitude" not in audit.metadata_json
    assert "longitude" not in audit.metadata_json


def test_hard_filters_structured_reasons_distance_and_idempotency(database):
    session = _session(database)
    eligible = _facility(database, "A", ["CARDIOLOGY", "IMAGING"], lat=22.58, lon=88.36)
    _facility(database, "B", ["DERMATOLOGY"], lat=22.57, lon=88.36)
    _facility(database, "C", ["CARDIOLOGY"], active=False, lat=22.57, lon=88.36)
    no_coordinates = _facility(database, "D", ["CARDIOLOGY"])
    _location(
        database,
        session,
        source="BROWSER_GEOLOCATION",
        locality=None,
        latitude=22.57,
        longitude=88.36,
        precision="browser",
    )

    first = mediroute.compute(database, session.id)
    second = mediroute.compute(database, session.id)
    assert first["id"] == second["id"]
    assert [item["facility_id"] for item in first["recommendations"]] == [
        eligible.id,
        no_coordinates.id,
    ]
    assert first["recommendations"][0]["distance_km"] is not None
    assert first["recommendations"][1]["distance_km"] is None
    assert "REQUIRED_SPECIALTY_AVAILABLE" in first["recommendations"][0]["eligibility_reasons"]
    assert database.scalar(select(func.count(models.MediRouteResult.id))) == 1


def test_emergency_requires_capability_and_preserves_specialty(database):
    session = _session(database, routing_state="EMERGENCY")
    _facility(database, "NO-ER", ["CARDIOLOGY"])
    emergency = _facility(database, "ER", ["CARDIOLOGY", "EMERGENCY"], emergency=True)
    _location(database, session)
    response = mediroute.compute(database, session.id)
    assert response["routing_state"] == "EMERGENCY"
    assert response["suggested_specialty"] == "CARDIOLOGY"
    assert response["required_capabilities"] == ["EMERGENCY"]
    assert [item["facility_id"] for item in response["recommendations"]] == [emergency.id]
    assert "EMERGENCY_CAPABLE" in response["recommendations"][0]["eligibility_reasons"]


def test_no_eligible_does_not_relax_and_location_change_recomputes(database):
    session = _session(database, specialty="DERMATOLOGY")
    _facility(database, "GENERAL", ["GENERAL_MEDICINE"])
    _location(database, session)
    first = mediroute.compute(database, session.id)
    assert first["status"] == "NO_ELIGIBLE_FACILITY"
    assert first["recommendations"] == []
    _location(database, session, locality="Howrah")
    second = mediroute.compute(database, session.id)
    assert second["id"] != first["id"]


def test_facility_without_an_eligible_doctor_is_not_recommended(database):
    session = _session(database)
    staffed = _facility(database, "STAFFED", ["CARDIOLOGY"])
    _facility(database, "UNSTAFFED", ["CARDIOLOGY", "IMAGING"], doctor=False)
    _location(database, session)

    response = mediroute.compute(database, session.id)

    assert [item["facility_id"] for item in response["recommendations"]] == [staffed.id]
    assert "ELIGIBLE_DOCTOR_AVAILABLE" in response["recommendations"][0]["eligibility_reasons"]


def test_selection_is_limited_to_current_recommendations_and_never_selects_doctor(database):
    session = _session(database)
    eligible = _facility(database, "ELIGIBLE", ["CARDIOLOGY"])
    arbitrary = _facility(database, "ARBITRARY", ["GENERAL_MEDICINE"])
    _location(database, session)
    mediroute.compute(database, session.id)
    try:
        mediroute.select_facility(database, session.id, arbitrary.id)
    except WorkflowError as exc:
        assert exc.code == "FACILITY_NOT_ELIGIBLE"
    else:
        raise AssertionError("arbitrary facility selection should fail")
    selected = mediroute.select_facility(database, session.id, eligible.id)
    assert selected.hospital_id == eligible.id
    assert selected.selected_doctor_id is None


def test_haversine_reference_distance():
    assert round(haversine_distance(22.5726, 88.3639, 22.5448, 88.3426), 1) == 3.8
