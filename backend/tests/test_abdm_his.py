import uuid

DOCTOR_HEADERS = {"X-Demo-Doctor": "true"}


def _create_test_session(client) -> str:
    client_uuid = str(uuid.uuid4())
    create_resp = client.post(
        "/api/sessions",
        json={
            "id": client_uuid,
            "patient": {"name": "ABDM Test Patient", "demo_abha_id": "patient@abdm"},
            "hospital_token": "T-ABDM-101",
            "language": "en",
        },
    )
    assert create_resp.status_code == 201
    consent_resp = client.put(
        f"/api/sessions/{client_uuid}/consent",
        json={
            "share_with_doctor": True,
            "voice_processing": True,
            "document_processing": True,
        },
    )
    assert consent_resp.status_code == 200
    return client_uuid


def test_abdm_verify_standalone_abha(client, database):
    # 1. Invalid input
    res = client.post("/api/sessions/verify-abha", json={"abha_input": "invalid"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["profile"] is None
    assert "Invalid ABHA format" in data["message"]

    # 2. Valid 14-digit format
    res = client.post(
        "/api/sessions/verify-abha", json={"abha_input": "91-1234-5678-9012"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["profile"]["status"] == "mock_verified"
    assert data["profile"]["abha_number"] == "91-1234-5678-9012"

    # 3. Valid ABHA address
    res = client.post(
        "/api/sessions/verify-abha", json={"abha_input": "test.patient@abdm"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["profile"]["status"] == "mock_verified"
    assert data["profile"]["abha_address"] == "test.patient@abdm"


def test_abdm_session_verify_and_status(client, database):
    session_id = _create_test_session(client)

    # 1. Get initial status
    res = client.get(
        f"/api/doctor/sessions/{session_id}/abdm/status", headers=DOCTOR_HEADERS
    )
    assert res.status_code == 200
    status_data = res.json()
    assert status_data["session_id"] == session_id
    assert status_data["abha_address"] == "patient@abdm"
    assert status_data["care_context_status"] == "unlinked"
    assert status_data["his_dispatch_status"] == "not_dispatched"

    # 2. Verify with new 14-digit ABHA
    res = client.post(
        f"/api/doctor/sessions/{session_id}/abdm/verify-abha",
        headers=DOCTOR_HEADERS,
        json={"abha_input": "91-9876-5432-1098"},
    )
    assert res.status_code == 200
    verify_data = res.json()
    assert verify_data["success"] is True
    assert verify_data["profile"]["abha_number"] == "91-9876-5432-1098"

    # 3. Verify status reflects the update
    res = client.get(
        f"/api/doctor/sessions/{session_id}/abdm/status", headers=DOCTOR_HEADERS
    )
    assert res.status_code == 200
    updated_status = res.json()
    assert updated_status["abha_number"] == "91-9876-5432-1098"
    assert updated_status["abha_status"] == "mock_verified"


def test_abdm_care_context_linking(client, database):
    session_id = _create_test_session(client)

    # Link care context
    res = client.post(
        f"/api/doctor/sessions/{session_id}/abdm/link-care-context",
        headers=DOCTOR_HEADERS,
    )
    assert res.status_code == 200
    link_data = res.json()
    assert link_data["success"] is True
    assert link_data["status"] == "linked"
    assert link_data["care_context_reference"].startswith("medikiosk_ctx_")
    assert "Token T-ABDM-101" in link_data["display"]

    # Verify status reflects linked state
    res = client.get(
        f"/api/doctor/sessions/{session_id}/abdm/status", headers=DOCTOR_HEADERS
    )
    assert res.status_code == 200
    status_data = res.json()
    assert status_data["care_context_status"] == "linked"
    assert status_data["care_context_reference"] == link_data["care_context_reference"]
    assert status_data["care_context_linked_at"] is not None


def test_his_dispatch_with_fhir_document(client, database):
    session_id = _create_test_session(client)

    # Consent
    res = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "share_with_doctor": True,
            "voice_processing": True,
            "document_processing": True,
        },
    )
    assert res.status_code == 200

    # Answers
    answers = [
        ("chief_complaint", "chief_complaint", "Severe cough for 3 days"),
        ("onset_duration", "onset_duration", "3 days"),
        ("medications", "medications", "None"),
        ("allergies", "allergies", "None"),
        ("past_history", "past_history", "None"),
    ]
    for qid, field, val in answers:
        client.post(
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

    # Dispatch to HIS
    res = client.post(
        f"/api/doctor/sessions/{session_id}/his/dispatch",
        headers=DOCTOR_HEADERS,
        json={"target_system": "Central Hospital HIS OPD"},
    )
    assert res.status_code == 200
    dispatch_data = res.json()
    assert dispatch_data["success"] is True
    assert dispatch_data["status"] == "dispatched"
    assert dispatch_data["receipt_reference"].startswith("HIS-ACK-")
    assert dispatch_data["attached_bundle_type"] == "document"

    # Verify HIS status endpoint
    res = client.get(
        f"/api/doctor/sessions/{session_id}/his/status", headers=DOCTOR_HEADERS
    )
    assert res.status_code == 200
    his_status = res.json()
    assert his_status["his_dispatch_status"] == "dispatched"
    assert (
        his_status["his_dispatch_receipt"]["receipt_id"]
        == dispatch_data["receipt_reference"]
    )

    # Verify audit trail contains HIS_DISPATCHED
    res = client.get(
        f"/api/doctor/sessions/{session_id}/audit-trail", headers=DOCTOR_HEADERS
    )
    assert res.status_code == 200
    audit_data = res.json()
    actions = [item["action"] for item in audit_data["items"]]
    assert "HIS_DISPATCHED" in actions


def test_abdm_his_authorization(client, database):
    session_id = _create_test_session(client)

    # Unauthenticated calls must fail closed
    res = client.get(f"/api/doctor/sessions/{session_id}/abdm/status")
    assert res.status_code == 401

    res = client.post(
        f"/api/doctor/sessions/{session_id}/abdm/verify-abha",
        json={"abha_input": "patient@abdm"},
    )
    assert res.status_code == 401

    res = client.post(f"/api/doctor/sessions/{session_id}/abdm/link-care-context")
    assert res.status_code == 401

    res = client.post(f"/api/doctor/sessions/{session_id}/his/dispatch")
    assert res.status_code == 401
