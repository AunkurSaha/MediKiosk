import uuid

from sqlalchemy.orm import Session

from app import models


def _seed_complete_session(client, db: Session) -> str:
    """Create a rich session with answers, facts, documents, and confirmed summary."""
    session_id = str(uuid.uuid4())
    headers = {"X-Demo-Doctor": "true"}

    # 1. Create session via client
    res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Sunita Sharma"},
            "hospital_token": "HOSP-FHIR-101",
            "language": "en",
        },
    )
    assert res.status_code == 201

    # Update patient's demo_abha_id
    sess = db.get(models.Session, session_id)
    pat = db.get(models.Patient, sess.patient_id)
    pat.demo_abha_id = "91-1234-5678-9012"
    db.flush()

    # 2. Consent
    res = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "share_with_doctor": True,
            "voice_processing": True,
            "document_processing": True,
        },
    )
    assert res.status_code == 200

    # 3. Answers (Include all 5 required fields)
    answers = [
        ("chief_complaint", "chief_complaint", "Acute substernal chest pressure"),
        ("onset_duration", "onset_duration", "started 2 hours ago"),
        ("medications", "medications", "Atorvastatin 40mg once daily"),
        ("allergies", "allergies", "No known allergies"),
        ("past_history", "past_history", "Hypertension and hyperlipidemia"),
    ]
    for qid, field, val in answers:
        res_ans = client.post(
            f"/api/sessions/{session_id}/answers",
            json={
                "question_id": qid,
                "field": field,
                "value": val,
                "raw_value": val,
                "source": "typed",
                "language": "en",
            },
        )
        assert res_ans.status_code == 200

    # 4. Complete intake
    comp_res = client.post(f"/api/sessions/{session_id}/complete")
    assert comp_res.status_code == 200

    # 5. Medical Facts: Medication & Lab
    db.add(
        models.MedicationFact(
            id=str(uuid.uuid4()),
            session_id=session_id,
            name="Atorvastatin",
            dosage="40mg",
            frequency="once daily",
            route="oral",
            source_text="Atorvastatin 40mg once daily",
            verification_status="verified",
        )
    )
    db.add(
        models.LabFact(
            id=str(uuid.uuid4()),
            session_id=session_id,
            test_name="High-Sensitivity Troponin I",
            value="45",
            unit="ng/L",
            reference_range="0 - 14 ng/L",
            flag="high",
            source_text="High-Sensitivity Troponin I: 45 ng/L",
            verification_status="verified",
        )
    )

    # 6. Document
    db.add(
        models.Document(
            id=str(uuid.uuid4()),
            session_id=session_id,
            object_key="uploads/ecg_report.pdf",
            original_filename="ecg_report.pdf",
            media_type="application/pdf",
            file_size_bytes=102400,
            sha256_hash="e" * 64,
            document_type="lab_report",
            processing_status="completed",
        )
    )
    db.flush()

    # 7. Review and Confirm Clinical Summary
    sum_res = client.get(f"/api/doctor/sessions/{session_id}/summary", headers=headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.json()

    rev_res = client.put(
        f"/api/doctor/sessions/{session_id}/summary",
        headers=headers,
        json={
            "expected_version": sum_data["version"],
            "reviewed_text": sum_data["reviewed_text"],
        },
    )
    assert rev_res.status_code == 200

    conf_res = client.post(
        f"/api/doctor/sessions/{session_id}/summary/confirm",
        headers=headers,
        json={"expected_version": rev_res.json()["version"]},
    )
    assert conf_res.status_code == 200

    return session_id


def test_fhir_bundle_export_document_and_collection(client, database):
    session_id = _seed_complete_session(client, database)
    headers = {"X-Demo-Doctor": "true"}

    # 1. Document Bundle Export
    res = client.get(f"/api/doctor/sessions/{session_id}/fhir/export", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["session_id"] == session_id
    assert data["bundle_type"] == "document"
    assert "HL7 FHIR R4" in data["compliance_profile"]

    counts = data["resource_counts"]
    assert counts.get("Patient") == 1
    assert counts.get("Encounter") == 1
    assert counts.get("QuestionnaireResponse") == 1
    assert counts.get("Condition") >= 1
    assert counts.get("MedicationStatement") >= 1
    assert counts.get("Observation") >= 1
    assert counts.get("DocumentReference") >= 1
    assert counts.get("Composition") == 1

    # In document bundle, entry[0] must be Composition
    bundle = data["bundle"]
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "document"
    assert len(bundle["entry"]) >= 8
    assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"

    # Verify 0 validation errors
    validation = data["validation"]
    assert validation["resourceType"] == "OperationOutcome"
    errors = [issue for issue in validation["issue"] if issue["severity"] in ["error", "fatal"]]
    assert len(errors) == 0, f"Unexpected validation errors: {errors}"

    # 2. Collection Bundle Export
    res_col = client.get(
        f"/api/doctor/sessions/{session_id}/fhir/export?bundle_type=collection",
        headers=headers,
    )
    assert res_col.status_code == 200
    col_data = res_col.json()
    assert col_data["bundle_type"] == "collection"
    assert col_data["bundle"]["type"] == "collection"


def test_fhir_bundle_raw_json_endpoint(client, database):
    session_id = _seed_complete_session(client, database)
    headers = {"X-Demo-Doctor": "true"}
    res = client.get(f"/api/doctor/sessions/{session_id}/fhir/bundle", headers=headers)
    assert res.status_code == 200
    assert "application/fhir+json" in res.headers["content-type"]

    bundle = res.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["id"] == f"bundle-{session_id}"
    assert isinstance(bundle["entry"], list)


def test_fhir_non_diagnostic_guardrails_and_patient_data(client, database):
    session_id = _seed_complete_session(client, database)
    headers = {"X-Demo-Doctor": "true"}
    res = client.get(f"/api/doctor/sessions/{session_id}/fhir/export", headers=headers)
    assert res.status_code == 200
    bundle = res.json()["bundle"]

    entries = {e["resource"]["resourceType"]: e["resource"] for e in bundle["entry"]}

    # Patient assertions
    patient = entries["Patient"]
    assert patient["name"][0]["text"] == "Sunita Sharma"
    assert patient["gender"] in ["female", "unknown"]
    ids = [i["value"] for i in patient["identifier"]]
    assert "HOSP-FHIR-101" in ids
    assert "91-1234-5678-9012" in ids

    # Condition assertions (Strictly provisional and non-diagnostic)
    condition = entries["Condition"]
    ver_coding = condition["verificationStatus"]["coding"][0]
    assert ver_coding["code"] == "provisional"
    note_text = condition["note"][0]["text"]
    assert "Non-diagnostic" in note_text
    assert "Requires clinical assessment" in note_text

    # Observation assertions
    obs = entries["Observation"]
    assert obs["code"]["text"] == "High-Sensitivity Troponin I"
    assert obs["valueString"] == "45 ng/L"
    assert obs["interpretation"][0]["coding"][0]["code"] == "H"
    assert obs["status"] == "final"

    # MedicationStatement assertions
    med = entries["MedicationStatement"]
    assert med["medicationCodeableConcept"]["text"] == "Atorvastatin"
    assert med["status"] == "active"
    assert "40mg" in med["dosage"][0]["text"]


def test_fhir_reference_integrity_and_validation(client, database):
    session_id = _seed_complete_session(client, database)
    headers = {"X-Demo-Doctor": "true"}

    # Run validation endpoint
    val_res = client.post(f"/api/doctor/sessions/{session_id}/fhir/validate", headers=headers)
    assert val_res.status_code == 200
    outcome = val_res.json()
    assert outcome["resourceType"] == "OperationOutcome"
    errors = [iss for iss in outcome["issue"] if iss["severity"] in ["error", "fatal"]]
    assert len(errors) == 0

    # Run export to generate audit event
    exp_res = client.get(f"/api/doctor/sessions/{session_id}/fhir/export", headers=headers)
    assert exp_res.status_code == 200

    # Test audit trail logs export event
    audit_res = client.get(f"/api/doctor/sessions/{session_id}/audit-trail", headers=headers)
    assert audit_res.status_code == 200
    actions = [ev["action"] for ev in audit_res.json()["items"]]
    assert "FHIR_EXPORTED" in actions


def test_fhir_security_unauthorized(client, database):
    session_id = _seed_complete_session(client, database)

    # Without staff header
    res = client.get(f"/api/doctor/sessions/{session_id}/fhir/export")
    assert res.status_code == 401

    res_bundle = client.get(f"/api/doctor/sessions/{session_id}/fhir/bundle")
    assert res_bundle.status_code == 401
