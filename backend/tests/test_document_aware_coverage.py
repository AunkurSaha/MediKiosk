from uuid import uuid4

from sqlalchemy import select

from app import models
from app.services import clinical_coverage, medical_extractor
from app.services.sms_provider import get_sms_provider
from tests.test_adaptive import payload
from tests.test_workflow import create


def _session_with_document(client, database, medication="Metformin", dosage="500 mg"):
    session_id, _ = create(client)
    consent = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": False,
            "document_processing": True,
            "share_with_doctor": True,
        },
    )
    assert consent.status_code == 200
    selected = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": "fever"})
    assert selected.status_code == 200
    document = models.Document(
        id=str(uuid4()),
        session_id=session_id,
        object_key=f"synthetic/{session_id}/prescription.png",
        original_filename="metformin-prescription.png",
        media_type="image/png",
        file_size_bytes=100,
        sha256_hash="a" * 64,
        document_type="prescription",
        processing_status="mock_fixture",
    )
    extraction = models.DocumentExtraction(
        id=str(uuid4()),
        document_id=document.id,
        session_id=session_id,
        extractor="mock",
        extractor_version="document-aware-v1",
        raw_text=f"Rx\nTab {medication} {dosage} - twice daily",
        structured_json={
            "document_type": "prescription",
            "medications": [
                {
                    "name": medication,
                    "dosage": dosage,
                    "frequency": "twice daily",
                    "source_text": f"{medication} {dosage} twice daily",
                    "source_location": "page 1",
                }
            ],
            "observations": [],
            "allergies": [],
        },
        confidence=0.91,
        verification_status="unverified",
    )
    database.add_all([document, extraction])
    database.flush()
    medical_extractor.extract_medical_facts(database, extraction)
    lab_document = models.Document(
        id=str(uuid4()),
        session_id=session_id,
        object_key=f"synthetic/{session_id}/lab.png",
        original_filename="fasting-glucose-report.png",
        media_type="image/png",
        file_size_bytes=100,
        sha256_hash="b" * 64,
        document_type="lab_report",
        processing_status="mock_fixture",
    )
    lab_extraction = models.DocumentExtraction(
        id=str(uuid4()),
        document_id=lab_document.id,
        session_id=session_id,
        extractor="mock",
        extractor_version="document-aware-v1",
        raw_text="Fasting glucose 146 mg/dL",
        structured_json={
            "document_type": "lab_report",
            "medications": [],
            "observations": [{"test_name": "Fasting glucose", "value": "146", "unit": "mg/dL"}],
            "allergies": [],
        },
        confidence=0.93,
        verification_status="unverified",
    )
    database.add_all([lab_document, lab_extraction])
    database.flush()
    medical_extractor.extract_medical_facts(database, lab_extraction)
    database.commit()
    evidence = database.scalar(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.session_id == session_id,
            models.ClinicalEvidence.concept_code == "MEDICATION_MENTION",
        )
    )
    return session_id, selected.json(), document, evidence


def _advance_to_document_confirmation(client, session_id, state):
    for _ in range(80):
        if state.get("document_confirmation"):
            return state
        response = client.post(
            f"/api/sessions/{session_id}/interview/answers",
            json=payload(state),
        )
        assert response.status_code == 200, response.text
        state = response.json()
    raise AssertionError("Document confirmation was not reached")


def test_document_medication_is_supported_but_not_patient_confirmed(client, database):
    session_id, _, document, evidence = _session_with_document(client, database)
    response = client.get(f"/api/sessions/{session_id}/coverage")
    assert response.status_code == 200
    medication = next(
        item for item in response.json()["fields"] if item["field"] == "medications.details"
    )
    assert medication["state"] == "DOCUMENT_SUPPORTED_UNCONFIRMED"
    assert medication["provenance"][0]["source_document_id"] == document.id
    assert medication["provenance"][0]["ocr_provider"] == "mock"
    assert evidence.verification_status == "UNVERIFIED"


def test_confirmation_creates_linked_patient_evidence_and_skips_generic_medication(
    client, database
):
    session_id, state, _, document_evidence = _session_with_document(client, database)
    state = _advance_to_document_confirmation(client, session_id, state)
    assert "Metformin" in state["question"]["text"]["en"]
    response = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json=payload(state, "yes", "answered", source="touch", raw_value="Yes"),
    )
    assert response.status_code == 200, response.text
    next_state = response.json()
    assert next_state["question"]["field"] not in {"medications.any", "medications.details"}
    database.refresh(document_evidence)
    assert document_evidence.verification_status == "UNVERIFIED"
    linked = database.scalars(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.session_id == session_id,
            models.ClinicalEvidence.verification_status == "PATIENT_CONFIRMED",
        )
    ).all()
    assert any(
        row.metadata_json.get("document_evidence_id") == document_evidence.id for row in linked
    )
    coverage = clinical_coverage.coverage(database, session_id)
    assert (
        next(item for item in coverage.fields if item.field == "medications.details").state
        == "CONFIRMED"
    )
    metrics = clinical_coverage.demo_metrics(database, session_id)
    assert metrics.confirmation_questions_added == 1
    assert metrics.questions_avoided == 1
    assert (
        metrics.questions_with_document_context
        == metrics.questions_without_document_context - metrics.questions_avoided
    )


def test_rejection_preserves_document_fact_and_surfaces_conflict(client, database):
    session_id, state, _, document_evidence = _session_with_document(client, database)
    state = _advance_to_document_confirmation(client, session_id, state)
    response = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json=payload(state, "no", "answered", source="touch", raw_value="No"),
    )
    assert response.status_code == 200
    database.refresh(document_evidence)
    assert document_evidence.verification_status == "UNVERIFIED"
    coverage = clinical_coverage.coverage(database, session_id)
    assert (
        next(item for item in coverage.fields if item.field == "medications.details").state
        == "CONFLICTED"
    )


def test_not_sure_keeps_document_evidence_unconfirmed_without_claiming_conflict(client, database):
    session_id, state, _, _ = _session_with_document(client, database)
    state = _advance_to_document_confirmation(client, session_id, state)
    response = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json=payload(state, "not_sure", "answered", source="touch", raw_value="Not sure"),
    )
    assert response.status_code == 200
    coverage = clinical_coverage.coverage(database, session_id)
    assert (
        next(item for item in coverage.fields if item.field == "medications.details").state
        == "DOCUMENT_SUPPORTED_UNCONFIRMED"
    )


def test_unrelated_lab_evidence_does_not_cover_medication_history(client, database):
    session_id, _, _, _ = _session_with_document(client, database)
    for row in database.scalars(
        select(models.ClinicalEvidence).where(
            models.ClinicalEvidence.session_id == session_id,
            models.ClinicalEvidence.concept_code == "MEDICATION_MENTION",
        )
    ):
        database.delete(row)
    database.commit()
    coverage = clinical_coverage.coverage(database, session_id)
    medication = next(item for item in coverage.fields if item.field == "medications.details")
    assert medication.state == "MISSING"
    lab = database.scalar(select(models.LabFact).where(models.LabFact.session_id == session_id))
    assert lab.test_name == "Fasting glucose"
    assert lab.value == "146"


def test_confirmation_metadata_preserves_original_document_provenance(client, database):
    session_id, state, document, evidence = _session_with_document(client, database)
    state = _advance_to_document_confirmation(client, session_id, state)
    client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json=payload(state, "yes", "answered", source="touch", raw_value="Yes"),
    )
    patient_evidence = next(
        row
        for row in database.scalars(
            select(models.ClinicalEvidence).where(
                models.ClinicalEvidence.session_id == session_id,
                models.ClinicalEvidence.verification_status == "PATIENT_CONFIRMED",
            )
        )
        if row.metadata_json.get("document_evidence_id") == evidence.id
    )
    assert patient_evidence is not None
    assert patient_evidence.metadata_json["source_document_id"] == document.id
    assert patient_evidence.source_id != evidence.source_id


def test_unconfirmed_document_cannot_complete_required_interview(client, database):
    session_id, state, _, _ = _session_with_document(client, database)
    state = _advance_to_document_confirmation(client, session_id, state)
    assert state["is_complete"] is False
    result = client.post(f"/api/sessions/{session_id}/complete")
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "ANSWERS_REQUIRED"


def test_document_from_another_session_does_not_change_coverage(client, database):
    _session_with_document(client, database)
    other_id, _ = create(client)
    client.put(
        f"/api/sessions/{other_id}/consent",
        json={
            "voice_processing": False,
            "document_processing": True,
            "share_with_doctor": True,
        },
    )
    client.put(f"/api/sessions/{other_id}/interview/flow", json={"flow_id": "fever"})
    coverage = clinical_coverage.coverage(database, other_id)
    medication = next(item for item in coverage.fields if item.field == "medications.details")
    assert medication.state == "MISSING"
    assert medication.provenance == []


def test_cross_patient_coverage_access_is_forbidden(client):
    def login(phone):
        assert client.post("/api/auth/otp/request", json={"phone_number": phone}).status_code == 200
        otp = get_sms_provider().get_last_dev_otp(phone)
        return client.post("/api/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()[
            "token"
        ]

    owner_token = login("+919700001111")
    stranger_token = login("+919700001112")
    session_id = str(uuid4())
    created = client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "id": session_id,
            "patient": {"name": "Coverage Owner"},
            "hospital_token": "COVERAGE-OWNER",
            "language": "en",
        },
    )
    assert created.status_code == 201
    response = client.get(
        f"/api/sessions/{session_id}/coverage",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert response.status_code == 403
