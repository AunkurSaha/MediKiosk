from uuid import uuid4

from sqlalchemy import func, select

from app import models
from app.core.errors import WorkflowError
from app.services import doctor_matching, intake


def _case(database, specialty="CARDIOLOGY", state="ROUTINE_OPD", language="en"):
    patient = models.Patient(id=str(uuid4()), name="Doctor Match Patient")
    facility = models.Hospital(
        id=str(uuid4()),
        code=f"F-{uuid4()}",
        name="Selected Facility",
        active=True,
        is_demo=True,
        opening_status="OPEN",
        directory_version="demo_facilities_v1",
        capabilities_json=[specialty, "EMERGENCY"],
        emergency_available=True,
    )
    session = models.Session(
        id=str(uuid4()),
        patient_id=patient.id,
        hospital_id=facility.id,
        hospital_token="MATCH-1",
        language=language,
        status="intake",
    )
    database.add_all([patient, facility, session])
    database.flush()
    routing = models.ClinicalRoutingResult(
        session_id=session.id,
        patient_id=patient.id,
        chief_complaint="CHEST_DISCOMFORT" if specialty == "CARDIOLOGY" else "FEVER",
        routing_state=state,
        suggested_specialty=specialty,
        protocol_version="1.0.0",
        supporting_evidence_ids_json=[],
        triggered_rule_ids_json=[],
        questions_asked_json=[],
        questions_skipped_json=[],
        completed_at=intake.now(),
    )
    location = models.PatientRoutingLocation(
        session_id=session.id,
        patient_id=patient.id,
        source="MANUAL_LOCALITY",
        locality="Kolkata",
    )
    database.add_all(
        [
            models.Consent(
                session_id=session.id,
                voice_processing=False,
                document_processing=False,
                share_with_doctor=True,
            ),
            routing,
            location,
        ]
    )
    database.flush()
    route = models.MediRouteResult(
        session_id=session.id,
        patient_id=patient.id,
        clinical_routing_result_id=routing.id,
        location_id=location.id,
        routing_state=state,
        suggested_specialty=specialty,
        directory_version="demo_facilities_v1",
        protocol_version="1.0.0",
        input_signature=str(uuid4()).replace("-", "") + str(uuid4()).replace("-", ""),
        required_specialty=specialty,
        required_capabilities_json=["EMERGENCY"] if state == "EMERGENCY" else [],
        preferred_capabilities_json=[],
        status="COMPLETED",
    )
    database.add(route)
    database.flush()
    database.add(
        models.MediRouteRecommendation(
            mediroute_result_id=route.id,
            facility_id=facility.id,
            rank=1,
            score=1,
            eligibility_reasons_json=[],
            ranking_reasons_json=[],
        )
    )
    database.commit()
    return session, facility, routing


def _doctor(
    database,
    facility,
    specialty,
    *,
    expertise=None,
    languages=None,
    availability="AVAILABLE",
    active=True,
    accepting=True,
    experience=10,
):
    doctor_id = str(uuid4())
    database.add(models.User(id=doctor_id, name="Synthetic Doctor", role="doctor", is_active=True))
    database.flush()
    profile = models.DoctorProfile(
        doctor_user_id=doctor_id,
        display_name=f"Dr {doctor_id[-4:]}",
        department=specialty,
        primary_specialty=specialty,
        expertise_tags_json=expertise or [],
        years_of_experience=experience,
        languages_json=languages or ["en"],
        consultation_types_json=["IN_PERSON"],
        availability_status=availability,
        directory_version="test_doctors_v1",
        is_demo=True,
        active=active,
        accepting_patients=accepting,
    )
    database.add(profile)
    database.flush()
    database.add(
        models.DoctorHospitalMembership(doctor_id=doctor_id, hospital_id=facility.id, active=True)
    )
    database.commit()
    return profile


def test_specialty_and_facility_are_hard_filters(database):
    session, facility, _ = _case(database)
    cardiologist = _doctor(database, facility, "CARDIOLOGY")
    _doctor(database, facility, "DERMATOLOGY", availability="AVAILABLE", experience=40)
    other = models.Hospital(id=str(uuid4()), code=f"F-{uuid4()}", name="Other", active=True)
    database.add(other)
    database.commit()
    _doctor(database, other, "CARDIOLOGY")
    response = doctor_matching.compute(database, session.id)
    assert [item["doctor_id"] for item in response["recommendations"]] == [
        cardiologist.doctor_user_id
    ]


def test_declared_subspecialty_is_eligible(database):
    session, facility, _ = _case(database, specialty="NEUROLOGY")
    doctor = _doctor(database, facility, "GENERAL_MEDICINE")
    database.add(
        models.DoctorSpecialtyMembership(
            doctor_id=doctor.doctor_user_id, specialty_code="NEUROLOGY"
        )
    )
    database.commit()

    response = doctor_matching.compute(database, session.id)

    assert response["status"] == "COMPLETED"
    assert [item["doctor_id"] for item in response["recommendations"]] == [doctor.doctor_user_id]


def test_inactive_not_accepting_and_off_duty_are_excluded(database):
    session, facility, _ = _case(database, specialty="PULMONOLOGY")
    _doctor(database, facility, "PULMONOLOGY", active=False)
    _doctor(database, facility, "PULMONOLOGY", accepting=False)
    _doctor(database, facility, "PULMONOLOGY", availability="OFF_DUTY")
    response = doctor_matching.compute(database, session.id)
    assert response["status"] == "NO_ELIGIBLE_DOCTOR"
    assert response["recommendations"] == []


def test_expertise_availability_language_and_capped_experience_rank_only_eligible(database):
    session, facility, _ = _case(database, language="bn")
    weaker = _doctor(database, facility, "CARDIOLOGY", experience=40, availability="BUSY")
    stronger = _doctor(
        database,
        facility,
        "CARDIOLOGY",
        expertise=["CHEST_PAIN"],
        languages=["en", "bn"],
        availability="AVAILABLE",
        experience=20,
    )
    response = doctor_matching.compute(database, session.id)
    assert response["recommendations"][0]["doctor_id"] == stronger.doctor_user_id
    assert response["recommendations"][1]["doctor_id"] == weaker.doctor_user_id
    recommendation = database.scalar(
        select(models.DoctorMatchRecommendation).where(
            models.DoctorMatchRecommendation.doctor_id == stronger.doctor_user_id
        )
    )
    assert recommendation.score_components_json["experience"] == 6
    assert "RELEVANT_EXPERTISE" in recommendation.ranking_reasons_json
    assert "LANGUAGE_MATCH" in recommendation.ranking_reasons_json


def test_busy_cardiologist_remains_eligible_over_available_dermatologist(database):
    session, facility, _ = _case(database)
    cardiologist = _doctor(database, facility, "CARDIOLOGY", availability="BUSY")
    _doctor(database, facility, "DERMATOLOGY", availability="AVAILABLE")
    response = doctor_matching.compute(database, session.id)
    assert [item["doctor_id"] for item in response["recommendations"]] == [
        cardiologist.doctor_user_id
    ]


def test_deterministic_tie_break_and_idempotency(database):
    session, facility, _ = _case(database)
    first = _doctor(database, facility, "CARDIOLOGY")
    second = _doctor(database, facility, "CARDIOLOGY")
    response = doctor_matching.compute(database, session.id)
    again = doctor_matching.compute(database, session.id)
    assert response["id"] == again["id"]
    assert [item["doctor_id"] for item in response["recommendations"]] == sorted(
        [first.doctor_user_id, second.doctor_user_id]
    )
    assert database.scalar(select(func.count(models.DoctorMatchResult.id))) == 1


def test_emergency_bypasses_matching(database):
    session, facility, _ = _case(database, state="EMERGENCY")
    _doctor(database, facility, "CARDIOLOGY")
    response = doctor_matching.compute(database, session.id)
    assert response["status"] == "DOCTOR_MATCHING_BYPASSED_EMERGENCY"
    assert response["recommendations"] == []


def test_selection_validates_recommendation_and_persists_for_workspace(database):
    session, facility, _ = _case(database)
    eligible = _doctor(database, facility, "CARDIOLOGY")
    wrong = _doctor(database, facility, "DERMATOLOGY")
    doctor_matching.compute(database, session.id)
    try:
        doctor_matching.select_doctor(database, session.id, wrong.doctor_user_id)
    except WorkflowError as exc:
        assert exc.code == "DOCTOR_NOT_ELIGIBLE"
    else:
        raise AssertionError("ineligible doctor selection should fail")
    selected = doctor_matching.select_doctor(database, session.id, eligible.doctor_user_id)
    assert selected["selected_doctor_id"] == eligible.doctor_user_id
    assert database.get(models.Session, session.id).selected_doctor_id == eligible.doctor_user_id


def test_availability_revision_changes_signature(database):
    session, facility, _ = _case(database)
    profile = _doctor(database, facility, "CARDIOLOGY")
    first = doctor_matching.compute(database, session.id)
    profile.availability_status = "BUSY"
    profile.availability_revision += 1
    database.commit()
    second = doctor_matching.compute(database, session.id)
    assert second["id"] != first["id"]


def test_directory_change_invalidates_selected_doctor(database):
    session, facility, _ = _case(database)
    profile = _doctor(database, facility, "CARDIOLOGY")
    first = doctor_matching.select_doctor(database, session.id, profile.doctor_user_id)
    profile.active = False
    database.commit()
    changed = doctor_matching.compute(database, session.id)
    assert changed["id"] != first["id"]
    assert changed["status"] == "NO_ELIGIBLE_DOCTOR"
    assert changed["selected_doctor_id"] is None
    assert database.get(models.Session, session.id).selected_doctor_id is None
