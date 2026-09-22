from uuid import uuid4

from sqlalchemy import select

from app import models
from app.domain.clinical_safety import EvidenceSourceType, EvidenceVerificationStatus
from app.schemas.clinical_evidence import ClinicalEvidenceCreate
from app.services import clinical_evidence


def _session(database):
    patient = models.Patient(id=str(uuid4()), name="Rapid Routing Patient")
    session = models.Session(
        id=str(uuid4()),
        patient_id=patient.id,
        hospital_token="RAPID-1",
        language="en",
        status="intake",
    )
    database.add_all([patient, session])
    database.flush()
    database.add(
        models.Consent(
            session_id=session.id,
            voice_processing=True,
            document_processing=False,
            share_with_doctor=True,
        )
    )
    database.commit()
    return session


def _map_and_confirm(
    client,
    session_id,
    text="My chest hurts when I walk",
    category="CHEST_DISCOMFORT",
    source="typed",
):
    mapped = client.post(
        f"/api/sessions/{session_id}/rapid-routing/complaint/map",
        json={"original_text": text, "language": "en", "source": source},
    )
    assert mapped.status_code == 200
    assert mapped.json()["phase"] == "confirm_complaint"
    return client.put(
        f"/api/sessions/{session_id}/rapid-routing/complaint",
        json={
            "category": category,
            "confirmed": True,
            "expected_revision": mapped.json()["revision"],
        },
    )


def _answer(client, session_id, state, value):
    question = state["question"]
    response = client.post(
        f"/api/sessions/{session_id}/rapid-routing/answers",
        json={
            "question_id": question["question_id"],
            "value": value,
            "raw_value": str(value),
            "source": "touch" if isinstance(value, bool) else "typed",
            "language": "en",
            "expected_revision": state["revision"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_text_mapping_requires_confirmation_and_creates_evidence(client, database):
    session = _session(database)
    mapped = client.post(
        f"/api/sessions/{session.id}/rapid-routing/complaint/map",
        json={
            "original_text": "I have been vomiting and my stomach hurts",
            "language": "en",
            "source": "typed",
        },
    )
    assert mapped.json()["mapping"]["candidate_category"] == "ABDOMINAL_PAIN"
    assert mapped.json()["phase"] == "confirm_complaint"
    assert (
        database.scalar(
            select(models.ClinicalEvidence).where(
                models.ClinicalEvidence.concept_code == "CHIEF_COMPLAINT"
            )
        )
        is None
    )
    confirmed = client.put(
        f"/api/sessions/{session.id}/rapid-routing/complaint",
        json={
            "category": "ABDOMINAL_PAIN",
            "confirmed": True,
            "expected_revision": mapped.json()["revision"],
        },
    )
    assert confirmed.status_code == 200
    evidence = database.scalar(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.concept_code == "CHIEF_COMPLAINT"
        )
    )
    assert evidence.value_json == "ABDOMINAL_PAIN"
    assert evidence.verification_status == "PATIENT_CONFIRMED"


def test_voice_metadata_is_preserved(client, database):
    session = _session(database)
    from types import SimpleNamespace

    from app.services.voice_candidates import issue

    token = issue(
        session.id,
        "rapid.chief_complaint",
        0,
        SimpleNamespace(language="bn", transcript="chest pain", provider="mock", model="fixture"),
    )
    mapped = client.post(
        f"/api/sessions/{session.id}/rapid-routing/complaint/map",
        json={
            "original_text": "chest pain",
            "translated_text": "Chest discomfort",
            "language": "bn",
            "source": "voice",
            "voice_candidate": token,
        },
    )
    confirmed = client.put(
        f"/api/sessions/{session.id}/rapid-routing/complaint",
        json={
            "category": "CHEST_DISCOMFORT",
            "confirmed": True,
            "expected_revision": mapped.json()["revision"],
        },
    )
    assert confirmed.status_code == 200
    evidence = database.scalar(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.concept_code == "CHIEF_COMPLAINT"
        )
    )
    assert evidence.source_type == "PATIENT_VOICE"
    assert evidence.translated_text == "Chest discomfort"
    assert evidence.metadata_json["voice_candidate_present"] is True
    assert evidence.metadata_json["asr_provider"] == "mock"


def test_trusted_evidence_skips_question_but_unverified_document_does_not(client, database):
    trusted_session = _session(database)
    clinical_evidence.create_evidence(
        database,
        ClinicalEvidenceCreate(
            patient_id=trusted_session.patient_id,
            session_id=trusted_session.id,
            concept_code="SYMPTOM_SEVERITY",
            value=3,
            source_type=EvidenceSourceType.PATIENT_TEXT,
            source_id=str(uuid4()),
            stable_key="existing",
            verification_status=EvidenceVerificationStatus.PATIENT_CONFIRMED,
            metadata={"canonical_field": "hpi.severity"},
        ),
    )
    database.commit()
    state = _map_and_confirm(client, trusted_session.id).json()
    assert "rapid.chest.severity" in state["questions_skipped"]
    assert state["question"]["question_id"] == "rapid.chest.breathlessness"

    unverified_session = _session(database)
    clinical_evidence.create_evidence(
        database,
        ClinicalEvidenceCreate(
            patient_id=unverified_session.patient_id,
            session_id=unverified_session.id,
            concept_code="SYMPTOM_SEVERITY",
            value=3,
            source_type=EvidenceSourceType.DOCUMENT,
            source_id=str(uuid4()),
            stable_key="ocr",
            verification_status=EvidenceVerificationStatus.UNVERIFIED,
            metadata={"canonical_field": "hpi.severity"},
        ),
    )
    database.commit()
    state = _map_and_confirm(client, unverified_session.id).json()
    assert state["question"]["question_id"] == "rapid.chest.severity"


def test_deterministic_emergency_result_persists_evidence_and_rules(client, database):
    session = _session(database)
    state = _map_and_confirm(client, session.id).json()
    state = _answer(client, session.id, state, 9)
    state = _answer(client, session.id, state, False)
    state = _answer(client, session.id, state, True)
    assert state["phase"] == "result"
    assert state["result"]["routing_state"] == "EMERGENCY"
    assert state["result"]["suggested_specialty"] == "CARDIOLOGY"
    assert "RF-CHEST-001" in state["result"]["triggered_red_flags"]
    assert state["result"]["supporting_evidence_ids"]
    recovered = client.get(f"/api/sessions/{session.id}/rapid-routing").json()
    assert recovered["result"]["id"] == state["result"]["id"]
    bypass = client.get(f"/api/sessions/{session.id}/interview")
    assert bypass.status_code == 409
    assert bypass.json()["error"]["code"] == "EMERGENCY_BYPASS_REQUIRED"


def test_routine_and_teleconsult_states(client, database):
    session = _session(database)
    state = _map_and_confirm(client, session.id).json()
    state = _answer(client, session.id, state, 2)
    state = _answer(client, session.id, state, False)
    state = _answer(client, session.id, state, False)
    assert state["result"]["routing_state"] == "ROUTINE_OPD"
    assert client.get(f"/api/sessions/{session.id}").status_code == 200
    run = database.get(models.InterviewRun, session.id)
    assert run is not None
    assert run.flow_id == "chest_pain"
    audits = database.scalars(
        select(models.AuditLog).where(
            models.AuditLog.entity_id == session.id,
            models.AuditLog.action == "interview_flow_selected",
        )
    ).all()
    assert len(audits) == 1
    cursor, revision = run.cursor, run.revision
    recovered = client.get(f"/api/sessions/{session.id}/rapid-routing").json()
    assert recovered["result"]["id"] == state["result"]["id"]
    persisted_run = database.get(models.InterviewRun, session.id)
    assert (persisted_run.cursor, persisted_run.revision) == (cursor, revision)

    skin = _session(database)
    result = _map_and_confirm(client, skin.id, "Skin rash", "SKIN_PROBLEM").json()["result"]
    assert result["routing_state"] == "TELECONSULT_MAY_BE_SUITABLE"
    assert result["suggested_specialty"] == "DERMATOLOGY"


def test_fever_temperature_from_rapid_routing_is_reused_by_adaptive_interview(client, database):
    session = _session(database)
    hospital = models.Hospital(
        id=str(uuid4()), code=f"RAPID-{uuid4()}", name="Rapid Fever Facility", active=True
    )
    database.add(hospital)
    database.commit()
    state = _map_and_confirm(client, session.id, "Fever", "FEVER").json()
    state = _answer(client, session.id, state, 38)
    state = _answer(client, session.id, state, False)
    assert state["result"]["routing_state"] == "ROUTINE_OPD"
    session.hospital_id = hospital.id
    database.commit()

    interview = client.get(f"/api/sessions/{session.id}/interview").json()
    assert interview["question"]["question_id"] == "chief_complaint.description"
    response = client.post(
        f"/api/sessions/{session.id}/interview/answers",
        json={
            "request_id": str(uuid4()),
            "expected_revision": interview["revision"],
            "question_id": "chief_complaint.description",
            "status": "answered",
            "value": "Fever since yesterday with chills and body ache.",
            "raw_value": "Fever since yesterday with chills and body ache.",
            "source": "typed",
            "language": "en",
        },
    )
    assert response.status_code == 200, response.text
    interview = response.json()
    assert interview["question"]["question_id"] != "hpi.temperature"
    assert any(
        item["question_id"] == "hpi.temperature" and item["value"] == 38
        for item in interview["active_answers"]
    )


def test_no_no_doctor_required_state_and_cross_patient_is_blocked(client, database):
    assert "NO_DOCTOR_REQUIRED" not in {
        item.value
        for item in __import__(
            "app.domain.clinical_safety", fromlist=["CareRoutingState"]
        ).CareRoutingState
    }
    owner = models.User(
        id=str(uuid4()), name="Owner", phone_number="+910000000001", role="patient", is_active=True
    )
    other = models.User(
        id=str(uuid4()), name="Other", phone_number="+910000000002", role="patient", is_active=True
    )
    database.add_all([owner, other])
    database.flush()
    session = _session(database)
    session.user_id = owner.id
    database.commit()
    from app.core.errors import WorkflowError
    from app.services import rapid_routing

    try:
        rapid_routing.state(database, session.id, other)
    except WorkflowError as exc:
        assert exc.status == 403
    else:
        raise AssertionError("cross-patient access was allowed")
