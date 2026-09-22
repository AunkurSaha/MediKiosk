import json
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.domain.clinical_safety import (
    CareRoutingState,
    EvidenceSourceType,
    EvidenceVerificationStatus,
)
from app.schemas.clinical_evidence import ClinicalEvidenceCreate
from app.services import clinical_evidence, medical_extractor, red_flags
from app.services.sms_provider import get_sms_provider

DOCTOR = {"X-Demo-Doctor": "true"}
TRIAGE = {"X-Demo-Triage": "true"}


def _session(database, *, patient_id=None, session_id=None, user_id=None):
    patient_id = patient_id or str(uuid4())
    session_id = session_id or str(uuid4())
    if database.get(models.Patient, patient_id) is None:
        database.add(models.Patient(id=patient_id, name="Evidence Test Patient"))
    row = models.Session(
        id=session_id,
        patient_id=patient_id,
        user_id=user_id,
        hospital_token=f"E-{session_id[:8]}",
        language="en",
        status="intake",
    )
    database.add(row)
    database.flush()
    return row


def _evidence(database, session, **overrides):
    payload = {
        "patient_id": session.patient_id,
        "session_id": session.id,
        "concept_code": "CHEST_PAIN",
        "value": True,
        "source_type": EvidenceSourceType.PATIENT_TEXT,
        "source_id": str(uuid4()),
        "original_text": "Chest pain",
        "language": "en",
        "verification_status": EvidenceVerificationStatus.PATIENT_CONFIRMED,
    }
    payload.update(overrides)
    return clinical_evidence.create_evidence(database, ClinicalEvidenceCreate(**payload))


def _patient_token(client, phone):
    assert client.post("/api/auth/otp/request", json={"phone_number": phone}).status_code == 200
    otp = get_sms_provider().get_last_dev_otp(phone)
    response = client.post("/api/auth/otp/verify", json={"phone_number": phone, "otp": otp})
    assert response.status_code == 200
    return response.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_safety_states_are_frozen_without_no_doctor_required():
    assert {item.value for item in CareRoutingState} == {
        "EMERGENCY",
        "URGENT",
        "ROUTINE_OPD",
        "TELECONSULT_MAY_BE_SUITABLE",
    }


def test_patient_text_and_voice_evidence_preserve_provenance(database):
    session = _session(database)
    text_answer = models.InterviewAnswer(
        id=str(uuid4()),
        session_id=session.id,
        question_id="chief",
        field="chief_complaint",
        value_json=json.dumps({"status": "answered", "value": "Chest pain"}),
        raw_value="Chest pain",
        source="typed",
        language="en",
        verification_status="patient_reported",
    )
    voice_answer = models.InterviewAnswer(
        id=str(uuid4()),
        session_id=session.id,
        question_id="exertion",
        field="hpi.exertion",
        value_json=json.dumps({"status": "answered", "value": True}),
        raw_value="হাঁটলে ব্যথাটা বাড়ে",
        source="voice",
        language="bn",
        verification_status="patient_reported",
    )
    database.add_all([text_answer, voice_answer])
    database.flush()
    text = clinical_evidence.create_patient_answer_evidence(
        database, text_answer, value="Chest pain"
    )
    duplicate = clinical_evidence.create_patient_answer_evidence(
        database, text_answer, value="Chest pain"
    )
    voice = clinical_evidence.create_patient_answer_evidence(
        database,
        voice_answer,
        value=True,
        translated_text="Pain increases while walking",
        voice_metadata={"asr_provider": "mock", "asr_model": "fixture"},
    )
    assert text.source_type == "PATIENT_TEXT"
    assert duplicate.id == text.id
    assert voice.source_type == "PATIENT_VOICE"
    assert voice.original_text == "হাঁটলে ব্যথাটা বাড়ে"
    assert voice.translated_text == "Pain increases while walking"
    assert voice.verification_status == "PATIENT_CONFIRMED"


def test_document_evidence_is_unverified_and_idempotent(database):
    session = _session(database)
    document = models.Document(
        id=str(uuid4()),
        session_id=session.id,
        object_key="evidence/test.pdf",
        original_filename="test.pdf",
        media_type="application/pdf",
        file_size_bytes=10,
        sha256_hash="a" * 64,
        document_type="prescription",
        processing_status="completed",
    )
    extraction = models.DocumentExtraction(
        id=str(uuid4()),
        document_id=document.id,
        session_id=session.id,
        extractor="mock",
        extractor_version="1",
        raw_text="Metformin 500 mg",
        structured_json={
            "document_type": "prescription",
            "medications": [{"name": "Metformin", "dosage": "500", "unit": "mg"}],
            "observations": [],
            "allergies": [],
        },
        confidence=0.8,
        verification_status="unverified",
    )
    database.add_all([document, extraction])
    database.flush()
    medical_extractor.extract_medical_facts(database, extraction)
    medical_extractor.extract_medical_facts(database, extraction)
    rows = database.scalars(
        select(models.ClinicalEvidence).where(models.ClinicalEvidence.source_type == "DOCUMENT")
    ).all()
    assert len(rows) == 1
    assert rows[0].verification_status == "UNVERIFIED"
    assert rows[0].metadata_json["document_id"] == document.id
    assert rows[0].metadata_json["ocr_confidence"] == 0.8


def test_clinician_verification_rejection_and_audit(database):
    session = _session(database)
    doctor = database.get(models.User, DEMO_DOCTOR_ID)
    verified = _evidence(database, session)
    rejected = _evidence(database, session, source_id=str(uuid4()), concept_code="COUGH")
    clinical_evidence.verify(database, verified.id, doctor, "Reviewed source")
    clinical_evidence.reject(database, rejected.id, doctor, "Incorrect extraction")
    database.flush()
    assert verified.verification_status == "CLINICIAN_VERIFIED"
    assert rejected.verification_status == "REJECTED"
    assert database.get(models.ClinicalEvidence, rejected.id) is rejected
    audit = database.scalars(
        select(models.AuditLog).where(
            models.AuditLog.action == "clinical_evidence_verification_changed"
        )
    ).all()
    assert len(audit) == 2
    assert audit[0].metadata_json["old_status"] == "PATIENT_CONFIRMED"


def test_rule_evidence_has_version_and_triggering_evidence(database):
    session = _session(database)
    answer = models.InterviewAnswer(
        id=str(uuid4()),
        session_id=session.id,
        question_id="pain.severity",
        field="pain.severity",
        value_json=json.dumps({"status": "answered", "value": 10}),
        raw_value="10",
        source="touch",
        language="en",
        verification_status="patient_reported",
    )
    database.add(answer)
    database.flush()
    source = clinical_evidence.create_patient_answer_evidence(database, answer, value=10)
    alert = models.Alert(
        session_id=session.id,
        rule_id="RF-CHEST-TEST",
        rule_version="1.2",
        priority="emergency",
        category="chest_pain",
        reason="Potential emergency symptoms detected.",
        triggering_facts_json=[
            {"question_id": answer.question_id, "field": answer.field, "value": 10}
        ],
        status="new",
    )
    database.add(alert)
    database.flush()
    row = clinical_evidence.create_rule_evidence(database, alert)
    assert row.source_type == "DETERMINISTIC_RULE"
    assert row.metadata_json["rule_version"] == "1.2"
    assert row.metadata_json["triggering_evidence_ids"] == [source.id]


def test_filters_previous_history_and_unverified_exclusion(database):
    patient_id = str(uuid4())
    previous = _session(database, patient_id=patient_id)
    current = _session(database, patient_id=patient_id)
    trusted = _evidence(database, previous, concept_code="CHEST_PAIN")
    clinician = _evidence(
        database,
        previous,
        source_id=str(uuid4()),
        concept_code="COUGH",
        verification_status=EvidenceVerificationStatus.CLINICIAN_VERIFIED,
    )
    _evidence(
        database,
        previous,
        source_id=str(uuid4()),
        concept_code="LAB_OBSERVATION",
        source_type=EvidenceSourceType.DOCUMENT,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )
    _evidence(database, current, source_id=str(uuid4()), concept_code="HEADACHE")
    assert clinical_evidence.get_by_concept(database, previous.id, "CHEST_PAIN") == [trusted]
    assert len(clinical_evidence.list_for_encounter(database, previous.id)) == 3
    assert len(clinical_evidence.list_for_patient(database, patient_id)) == 4
    history = clinical_evidence.get_previous_verified_evidence(database, patient_id, current.id)
    assert {row.id for row in history} == {trusted.id, clinician.id}


def test_conflicting_evidence_coexists_and_links(database):
    session = _session(database)
    doctor = database.get(models.User, DEMO_DOCTOR_ID)
    denial = _evidence(database, session, value=False, original_text="No diabetes")
    medicine = _evidence(
        database,
        session,
        source_id=str(uuid4()),
        concept_code="MEDICATION_MENTION",
        value={"name": "Metformin", "dosage": "500 mg"},
        source_type=EvidenceSourceType.DOCUMENT,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )
    clinical_evidence.mark_conflicting(
        database, denial.id, medicine.id, doctor, "Possible discrepancy; requires review"
    )
    database.flush()
    assert database.get(models.ClinicalEvidence, denial.id) is not None
    assert database.get(models.ClinicalEvidence, medicine.id) is not None
    assert denial.verification_status == medicine.verification_status == "CONFLICTING"
    assert clinical_evidence.read(database, denial).conflicts_with == [medicine.id]


def test_existing_answer_submission_dual_writes_evidence(client, database):
    session_id = str(uuid4())
    assert (
        client.post(
            "/api/sessions",
            json={
                "id": session_id,
                "patient": {"name": "Dual Write Patient", "demo_abha_id": None},
                "hospital_token": "E-DUAL",
                "language": "en",
            },
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"/api/sessions/{session_id}/consent",
            json={
                "voice_processing": False,
                "document_processing": False,
                "share_with_doctor": True,
            },
        ).status_code
        == 200
    )
    response = client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "question_id": "chief_complaint",
            "field": "chief_complaint",
            "value": "Chest pain",
            "raw_value": "Chest pain",
            "source": "typed",
            "language": "en",
        },
    )
    assert response.status_code == 200, response.text
    rows = clinical_evidence.list_for_encounter(database, session_id)
    assert any(row.stable_key == "raw_answer" for row in rows)
    assert any(row.concept_code == "CHEST_PAIN" for row in rows)


def test_evidence_api_enforces_patient_isolation_and_roles(client, database):
    token_a = _patient_token(client, "+919876542001")
    token_b = _patient_token(client, "+919876542002")
    session_id = str(uuid4())
    created = client.post(
        "/api/sessions",
        headers=_auth(token_a),
        json={
            "id": session_id,
            "patient": {"name": "Owned Evidence", "demo_abha_id": None},
            "hospital_token": "E-OWNED",
            "language": "en",
        },
    )
    assert created.status_code == 201
    session = database.get(models.Session, session_id)
    row = _evidence(database, session)
    database.commit()
    assert (
        client.get(f"/api/evidence/encounters/{session_id}", headers=_auth(token_a)).status_code
        == 200
    )
    assert (
        client.get(f"/api/evidence/encounters/{session_id}", headers=_auth(token_b)).status_code
        == 403
    )
    legacy = _session(database)
    _evidence(database, legacy)
    database.commit()
    assert (
        client.get(f"/api/evidence/encounters/{legacy.id}", headers=_auth(token_a)).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/evidence/doctor/encounters/{session_id}/{row.id}/verify",
            headers=_auth(token_a),
            json={"reason": "not allowed"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/evidence/doctor/encounters/{session_id}/{row.id}/verify",
            headers=TRIAGE,
            json={"reason": "not allowed"},
        ).status_code
        == 403
    )


def test_doctor_can_verify_authorized_legacy_evidence(client, database):
    session = _session(database)
    database.add(
        models.Consent(
            session_id=session.id,
            share_with_doctor=True,
            voice_processing=False,
            document_processing=False,
        )
    )
    row = _evidence(database, session)
    database.commit()
    response = client.post(
        f"/api/evidence/doctor/encounters/{session.id}/{row.id}/verify",
        headers=DOCTOR,
        json={"reason": "Source reviewed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "CLINICIAN_VERIFIED"


def test_red_flag_engine_still_creates_alert_and_evidence(database, monkeypatch):
    session = _session(database)
    rule = red_flags.RuleDefinition(
        rule_id="RF-TEST-001",
        version="1",
        flow_id="test.flow",
        priority="urgent",
        category="test",
        reason="Immediate clinical assessment recommended.",
        conditions=[red_flags.RuleCondition(field="severity", operator="equals", value=10)],
    )
    monkeypatch.setattr(
        red_flags,
        "get_rule_catalog",
        lambda: red_flags.RuleCatalog(
            schema_version="1", rules_version="1", description="test", rules=[rule]
        ),
    )
    fact = red_flags.Fact(
        answer_id=str(uuid4()),
        question_id="severity",
        field="severity",
        label={"en": "Severity", "bn": "Severity", "hi": "Severity"},
        status="answered",
        value=10,
        raw_value="10",
        source="touch",
        language="en",
        recorded_at=clinical_evidence._now(),
    )
    alerts = red_flags.evaluate_and_persist(database, session.id, "test.flow", [fact])
    assert len(alerts) == 1
    assert (
        database.scalar(
            select(models.ClinicalEvidence).where(models.ClinicalEvidence.source_id == alerts[0].id)
        )
        is not None
    )
