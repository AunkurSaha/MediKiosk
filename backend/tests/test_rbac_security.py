"""Exhaustive role-based access control (RBAC) security test suite for MediKiosk.

Covers:
- Strict role boundaries (patient, doctor, triage)
- Unauthenticated rejection (401)
- Patient rejection on all doctor endpoints (403)
- Patient rejection on all triage endpoints (403)
- Patient rejection on triage WebSocket (403 / 1008)
- Patient rejection on fact verification, document extraction verification, and summary confirmation
- Cross-patient session data isolation (403)
- Triage access to triage endpoints (200)
- Triage rejection on doctor endpoints (403)
- Triage rejection on direct patient intake sessions (403)
- Doctor access to doctor operations (200)
- Public /api/config secret leakage prevention
"""

from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.services.sms_provider import get_sms_provider


def login_patient(client, phone_number: str) -> str:
    res_req = client.post("/api/auth/otp/request", json={"phone_number": phone_number})
    assert res_req.status_code == 200, res_req.text
    sms_provider = get_sms_provider()
    otp = sms_provider.get_last_dev_otp(phone_number)
    assert otp is not None
    res_verify = client.post("/api/auth/otp/verify", json={"phone_number": phone_number, "otp": otp})
    assert res_verify.status_code == 200, res_verify.text
    return res_verify.json()["token"]


def login_doctor(client) -> str:
    res = client.post("/api/auth/demo-login", json={"role": "doctor"})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def login_triage(client) -> str:
    res = client.post("/api/auth/demo-login", json={"role": "triage"})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_patient_session(client, token: str) -> str:
    session_id = str(uuid4())
    res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "RBAC Test Patient", "demo_abha_id": None},
            "hospital_token": f"T-{session_id[:8]}",
            "language": "en",
        },
        headers=auth_header(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------------------------------------------------------
# 1. Unauthenticated calls receive 401
# ---------------------------------------------------------------------------

def test_unauthenticated_requests_receive_401(client):
    fake_id = str(uuid4())
    assert client.get("/api/doctor/sessions").status_code == 401
    assert client.get(f"/api/doctor/sessions/{fake_id}").status_code == 401
    assert client.get(f"/api/doctor/sessions/{fake_id}/summary").status_code == 401
    assert client.get(f"/api/doctor/sessions/{fake_id}/fhir/export").status_code == 401
    assert client.get(f"/api/doctor/sessions/{fake_id}/medical-facts").status_code == 401
    assert client.get("/api/triage/alerts").status_code == 401
    assert client.post("/api/triage/ws-ticket").status_code == 401


# ---------------------------------------------------------------------------
# 2. Patient cannot access any doctor API (403 FORBIDDEN)
# ---------------------------------------------------------------------------

def test_patient_cannot_access_doctor_workspace_apis(client):
    token = login_patient(client, "+919876541001")
    headers = auth_header(token)
    session_id = create_patient_session(client, token)

    # 1. Doctor session list
    res = client.get("/api/doctor/sessions", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    # 2. Doctor session detail
    res = client.get(f"/api/doctor/sessions/{session_id}", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    # 3. Summary endpoints
    assert client.get(f"/api/doctor/sessions/{session_id}/summary", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/summary/regenerate", json={"strategy": "full"}, headers=headers).status_code == 403
    assert client.put(f"/api/doctor/sessions/{session_id}/summary", json={"reviewed_text": "Hacked", "expected_version": 1}, headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/summary/confirm", json={"expected_version": 1}, headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/summary/revisions", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/summary/evidence", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/summary/amend", json={"amendment_note": "Hacked"}, headers=headers).status_code == 403

    # 4. Field verifications and audit trail
    assert client.get(f"/api/doctor/sessions/{session_id}/field-verifications", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/field-verifications", json={"field_name": "chief_complaint", "status": "verified"}, headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/audit-trail", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/cross-references", headers=headers).status_code == 403

    # 5. FHIR export & validation
    assert client.get(f"/api/doctor/sessions/{session_id}/fhir/export", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/fhir/bundle", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/fhir/validate", headers=headers).status_code == 403

    # 6. ABDM & HIS operations
    assert client.get(f"/api/doctor/sessions/{session_id}/abdm/status", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/abdm/verify-abha", json={"abha_input": "91-1234-5678-9012"}, headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/abdm/link-care-context", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/his/dispatch", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/his/status", headers=headers).status_code == 403

    # 7. Demo commands & translation tools
    assert client.post("/api/doctor/demo/seed-showcase", headers=headers).status_code == 403
    assert client.post("/api/doctor/demo/reset", headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/translate", json={"text": "hi", "source_language": "en", "target_language": "bn"}, headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/transliterate", json={"text": "hi", "source_language": "en", "target_language": "bn"}, headers=headers).status_code == 403
    assert client.post(f"/api/doctor/sessions/{session_id}/identify-language", json={"text": "hi"}, headers=headers).status_code == 403

    # 8. Medical facts & timeline
    fake_fact = str(uuid4())
    assert client.get(f"/api/doctor/sessions/{session_id}/medical-facts", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/timeline", headers=headers).status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}/discrepancies", headers=headers).status_code == 403
    assert client.patch(f"/api/doctor/sessions/{session_id}/medical-facts/medications/{fake_fact}", json={"status": "verified"}, headers=headers).status_code == 403
    assert client.patch(f"/api/doctor/sessions/{session_id}/medical-facts/labs/{fake_fact}", json={"status": "verified"}, headers=headers).status_code == 403

    # 9. Document extraction verification
    assert client.post(f"/api/sessions/{session_id}/documents/fake/extractions/fake/verify", json={"status": "verified"}, headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# 3. Patient cannot access any triage API (403 FORBIDDEN)
# ---------------------------------------------------------------------------

def test_patient_cannot_access_triage_apis(client):
    token = login_patient(client, "+919876541002")
    headers = auth_header(token)
    session_id = create_patient_session(client, token)

    # 1. Triage alert list
    res_list = client.get("/api/triage/alerts", headers=headers)
    assert res_list.status_code == 403
    assert res_list.json()["error"]["code"] == "FORBIDDEN"

    # 2. Acknowledge alert
    fake_alert = str(uuid4())
    res_ack = client.post(f"/api/triage/alerts/{fake_alert}/acknowledge", json={"expected_revision": 1, "note": "fake"}, headers=headers)
    assert res_ack.status_code == 403

    # 3. WebSocket ticket
    res_ticket = client.post("/api/triage/ws-ticket", headers=headers)
    assert res_ticket.status_code == 403

    # 4. Session alerts
    assert client.get(f"/api/triage/sessions/{session_id}/alerts", headers=headers).status_code == 403
    assert client.get(f"/api/sessions/{session_id}/alerts", headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# 4. WebSocket security: patient cannot connect to triage WebSocket
# ---------------------------------------------------------------------------

def test_patient_cannot_connect_to_triage_websocket(client):
    token = login_patient(client, "+919876541003")
    # Patient cannot get a ticket
    ticket_res = client.post("/api/triage/ws-ticket", headers=auth_header(token))
    assert ticket_res.status_code == 403

    # Patient attempting WebSocket connection with random ticket or subprotocol is rejected
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            "/api/triage/ws",
            subprotocols=["medikiosk", "fake-token"],
            headers={"Origin": "http://127.0.0.1:5175"},
        ):
            pass
    assert exc.value.code == 1008


# ---------------------------------------------------------------------------
# 5. Cross-patient session ownership isolation (403 FORBIDDEN)
# ---------------------------------------------------------------------------

def test_cross_patient_session_isolation(client):
    token_a = login_patient(client, "+919876541004")
    token_b = login_patient(client, "+919876541005")

    session_a = create_patient_session(client, token_a)

    # Patient B cannot read Patient A's session detail
    res_read = client.get(f"/api/sessions/{session_a}", headers=auth_header(token_b))
    assert res_read.status_code == 403
    assert res_read.json()["error"]["code"] == "FORBIDDEN"

    # Patient B cannot update consent on Patient A's session
    res_consent = client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": False, "document_processing": False},
        headers=auth_header(token_b),
    )
    assert res_consent.status_code == 403

    # Patient B cannot submit answers on Patient A's session
    res_ans = client.post(
        f"/api/sessions/{session_a}/interview/answers",
        json={
            "request_id": str(uuid4()),
            "expected_revision": 1,
            "question_id": "chief_complaint.description",
            "status": "answered",
            "value": "hacked",
            "raw_value": "hacked",
            "source": "typed",
            "language": "en",
        },
        headers=auth_header(token_b),
    )
    assert res_ans.status_code == 403

    # Patient B cannot complete Patient A's session
    res_comp = client.post(f"/api/sessions/{session_a}/complete", headers=auth_header(token_b))
    assert res_comp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Doctor access: Doctor can access doctor workspace & operations
# ---------------------------------------------------------------------------

def test_doctor_can_access_doctor_workspace(client):
    doc_token = login_doctor(client)
    doc_headers = auth_header(doc_token)

    res_sessions = client.get("/api/doctor/sessions", headers=doc_headers)
    assert res_sessions.status_code == 200
    assert "items" in res_sessions.json()


# ---------------------------------------------------------------------------
# 7. Triage role: Authorized triage user can access triage & ws
# ---------------------------------------------------------------------------

def test_triage_user_can_access_triage_operations(client):
    triage_token = login_triage(client)
    triage_headers = auth_header(triage_token)

    # 1. Can list alerts
    res_alerts = client.get("/api/triage/alerts", headers=triage_headers)
    assert res_alerts.status_code == 200
    assert "items" in res_alerts.json()

    # 2. Can obtain WebSocket ticket
    res_ticket = client.post("/api/triage/ws-ticket", headers=triage_headers)
    assert res_ticket.status_code == 200
    ticket = res_ticket.json()["ticket"]
    assert ticket is not None

    # 3. Can connect to WebSocket using ticket
    with client.websocket_connect(
        "/api/triage/ws",
        subprotocols=["medikiosk", ticket],
        headers={"Origin": "http://127.0.0.1:5175"},
    ) as ws:
        assert ws is not None


# ---------------------------------------------------------------------------
# 8. Triage role CANNOT access doctor workspace or patient intake
# ---------------------------------------------------------------------------

def test_triage_user_cannot_access_doctor_workspace(client):
    triage_token = login_triage(client)
    triage_headers = auth_header(triage_token)

    # Triage user blocked from doctor session list
    res_doc = client.get("/api/doctor/sessions", headers=triage_headers)
    assert res_doc.status_code == 403
    assert res_doc.json()["error"]["code"] == "FORBIDDEN"

    # Triage user blocked from direct patient intake session
    patient_token = login_patient(client, "+919876541099")
    patient_session_id = create_patient_session(client, patient_token)
    res_intake = client.get(f"/api/sessions/{patient_session_id}", headers=triage_headers)
    assert res_intake.status_code == 403
    assert res_intake.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 9. Public /api/config secret leakage prevention
# ---------------------------------------------------------------------------

def test_public_config_does_not_leak_authorization_secrets(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "demo_mode" in data

    text = res.text.lower()
    for forbidden in ["secret", "password", "token", "hash", "otp", "key"]:
        assert forbidden not in text, f"Found forbidden secret word '{forbidden}' in /api/config output"
