import io
from pathlib import Path
from uuid import uuid4

from app import models
from app.services.sms_provider import get_sms_provider

FIXTURE_PNG = (Path(__file__).resolve().parents[2] / "ai" / "document_fixtures" / "prescription.png").read_bytes()


def login_patient(client, phone_number: str) -> str:
    res_req = client.post("/api/auth/otp/request", json={"phone_number": phone_number})
    assert res_req.status_code == 200, res_req.text
    sms_provider = get_sms_provider()
    otp = sms_provider.get_last_dev_otp(phone_number)
    assert otp is not None
    res_verify = client.post("/api/auth/otp/verify", json={"phone_number": phone_number, "otp": otp})
    assert res_verify.status_code == 200, res_verify.text
    return res_verify.json()["token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}



def create_patient_session(client, token: str) -> str:
    headers = auth_header(token)
    session_id = str(uuid4())
    hosp_res = client.get("/api/hospitals")
    hospital_id = hosp_res.json()["items"][0]["id"] if hosp_res.status_code == 200 and hosp_res.json().get("items") else None
    res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Test Patient", "demo_abha_id": None},
            "hospital_id": hospital_id,
            "hospital_token": f"T-{session_id[:8]}",
            "language": "en",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_patient_creates_owned_session(client, database):
    token = login_patient(client, "+919876540001")
    session_id = create_patient_session(client, token)

    session = database.get(models.Session, session_id)
    assert session is not None
    assert session.user_id is not None
    user = database.query(models.User).filter_by(phone_number="+919876540001").first()
    assert session.user_id == user.id


def test_owned_patient_can_select_flow_and_repeat_selection(client):
    token = login_patient(client, "+919876540021")
    session_id = create_patient_session(client, token)
    headers = auth_header(token)
    hosp_res = client.get("/api/hospitals")
    if hosp_res.status_code == 200 and hosp_res.json().get("items"):
        hosp_id = hosp_res.json()["items"][0]["id"]
        client.put(
            f"/api/sessions/{session_id}/hospital",
            json={"hospital_id": hosp_id},
            headers=headers,
        )

    consent = client.put(
        f"/api/sessions/{session_id}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=headers,
    )
    assert consent.status_code == 200, consent.text

    selected = client.put(
        f"/api/sessions/{session_id}/interview/flow",
        json={"flow_id": "chest_pain"},
        headers=headers,
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["question"]["question_id"] == "chief_complaint.description"

    repeated = client.put(
        f"/api/sessions/{session_id}/interview/flow",
        json={"flow_id": "chest_pain"},
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["question"]["question_id"] == "chief_complaint.description"

    doc_matches = client.get(f"/api/sessions/{session_id}/doctors", headers=headers)
    assert doc_matches.status_code == 200, doc_matches.text
    assert len(doc_matches.json()["items"]) > 0, "Expected matched doctors"
    matched_doc_id = doc_matches.json()["items"][0]["doctor_id"]
    choose_doc = client.put(
        f"/api/sessions/{session_id}/doctor",
        json={"doctor_id": matched_doc_id},
        headers=headers,
    )
    assert choose_doc.status_code == 200, choose_doc.text

    state = repeated.json()
    for _ in range(100):
        question = state["question"]
        if question is None:
            break
        answered = question["type"] == "boolean"
        response = client.post(
            f"/api/sessions/{session_id}/interview/answers",
            json={
                "request_id": str(uuid4()),
                "expected_revision": state["revision"],
                "question_id": question["question_id"],
                "status": "answered" if answered else "unknown",
                "value": False if answered else None,
                "raw_value": "No" if answered else "Unknown",
                "source": "touch" if answered else "typed",
                "language": "en",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        state = response.json()
    assert state["is_complete"] is True

    completed = client.post(f"/api/sessions/{session_id}/complete", headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "ready_for_review"

    doctor_login = client.post("/api/auth/demo-login", json={"role": "doctor"})
    assert doctor_login.status_code == 200, doctor_login.text
    exported = client.get(
        f"/api/doctor/sessions/{session_id}/fhir/export",
        headers=auth_header(doctor_login.json()["token"]),
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["bundle"]["resourceType"] == "Bundle"


def test_cross_patient_session_detail_forbidden(client):
    token_a = login_patient(client, "+919876540002")
    token_b = login_patient(client, "+919876540003")

    session_a = create_patient_session(client, token_a)

    # Owner can read session detail
    res_owner = client.get(f"/api/sessions/{session_a}", headers=auth_header(token_a))
    assert res_owner.status_code == 200

    # Another patient cannot read session detail (must return 403 Forbidden)
    res_other = client.get(f"/api/sessions/{session_a}", headers=auth_header(token_b))
    assert res_other.status_code == 403
    assert res_other.json()["error"]["code"] == "FORBIDDEN"


def test_unauthenticated_access_to_owned_session_unauthorized(client):
    token = login_patient(client, "+919876540004")
    session_id = create_patient_session(client, token)

    # Clear client cookie jar to simulate unauthenticated client
    client.cookies.clear()

    # Unauthenticated GET must return 401
    res = client.get(f"/api/sessions/{session_id}")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_REQUIRED"


def test_cross_patient_consent_forbidden(client):
    token_a = login_patient(client, "+919876540005")
    token_b = login_patient(client, "+919876540006")

    session_a = create_patient_session(client, token_a)

    # Patient B cannot update Patient A's consent
    res = client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_b),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    # Patient A can update own consent
    res_ok = client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )
    assert res_ok.status_code == 200


def test_cross_patient_answers_forbidden(client):
    token_a = login_patient(client, "+919876540007")
    token_b = login_patient(client, "+919876540008")

    session_a = create_patient_session(client, token_a)

    # Put consent first
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    # Patient B cannot read answers
    res = client.get(f"/api/sessions/{session_a}/answers", headers=auth_header(token_b))
    assert res.status_code == 403

    # Patient B cannot post answers
    res_post = client.post(
        f"/api/sessions/{session_a}/answers",
        json={
            "question_id": "chief_complaint",
            "field": "chief_complaint",
            "value": "Severe chest tightness",
            "raw_value": "Severe chest tightness",
            "source": "typed",
            "language": "en",
        },
        headers=auth_header(token_b),
    )
    assert res_post.status_code == 403


def test_cross_patient_interview_state_forbidden(client):
    token_a = login_patient(client, "+919876540009")
    token_b = login_patient(client, "+919876540010")

    session_a = create_patient_session(client, token_a)
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    # Patient B cannot get interview state
    res = client.get(f"/api/sessions/{session_a}/interview", headers=auth_header(token_b))
    assert res.status_code == 403

    # Patient B cannot select flow
    res_flow = client.put(
        f"/api/sessions/{session_a}/interview/flow",
        json={"flow_id": "adult_general.chest_pain"},
        headers=auth_header(token_b),
    )
    assert res_flow.status_code == 403


def test_cross_patient_document_upload_forbidden(client):
    token_a = login_patient(client, "+919876540011")
    token_b = login_patient(client, "+919876540012")

    session_a = create_patient_session(client, token_a)
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    # Patient B cannot upload document to Patient A's session
    res = client.post(
        f"/api/sessions/{session_a}/documents",
        files={"file": ("prescription.png", io.BytesIO(FIXTURE_PNG), "image/png")},
        data={"document_type": "prescription"},
        headers=auth_header(token_b),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_cross_patient_document_view_and_download_forbidden(client):
    token_a = login_patient(client, "+919876540013")
    token_b = login_patient(client, "+919876540014")

    session_a = create_patient_session(client, token_a)
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    upload_res = client.post(
        f"/api/sessions/{session_a}/documents",
        files={"file": ("prescription.png", io.BytesIO(FIXTURE_PNG), "image/png")},
        data={"document_type": "prescription"},
        headers=auth_header(token_a),
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Patient B cannot list documents
    res_list = client.get(f"/api/sessions/{session_a}/documents", headers=auth_header(token_b))
    assert res_list.status_code == 403

    # Patient B cannot get document detail
    res_detail = client.get(f"/api/sessions/{session_a}/documents/{doc_id}", headers=auth_header(token_b))
    assert res_detail.status_code == 403

    # Patient B cannot download document file
    res_file = client.get(f"/api/sessions/{session_a}/documents/{doc_id}/file", headers=auth_header(token_b))
    assert res_file.status_code == 403


def test_owner_patient_can_view_own_document(client):
    token_a = login_patient(client, "+919876540015")
    session_a = create_patient_session(client, token_a)
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    upload_res = client.post(
        f"/api/sessions/{session_a}/documents",
        files={"file": ("my_prescription.png", io.BytesIO(FIXTURE_PNG), "image/png")},
        data={"document_type": "prescription"},
        headers=auth_header(token_a),
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Owner can list documents
    res_list = client.get(f"/api/sessions/{session_a}/documents", headers=auth_header(token_a))
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 1

    # Owner can download own document file
    res_file = client.get(f"/api/sessions/{session_a}/documents/{doc_id}/file", headers=auth_header(token_a))
    assert res_file.status_code == 200
    assert len(res_file.content) == len(FIXTURE_PNG)


def test_patient_cannot_access_doctor_routes(client):
    token = login_patient(client, "+919876540016")
    headers = auth_header(token)

    # Doctor session list
    res_sessions = client.get("/api/doctor/sessions", headers=headers)
    assert res_sessions.status_code == 403
    assert res_sessions.json()["error"]["code"] == "FORBIDDEN"

    # Doctor seed showcase
    res_seed = client.post("/api/doctor/demo/seed-showcase", headers=headers)
    assert res_seed.status_code == 403

    # Doctor reset
    res_reset = client.post("/api/doctor/demo/reset", headers=headers)
    assert res_reset.status_code == 403


def test_patient_cannot_access_triage_routes(client):
    token = login_patient(client, "+919876540017")
    headers = auth_header(token)

    res_alerts = client.get("/api/triage/alerts", headers=headers)
    assert res_alerts.status_code == 403
    assert res_alerts.json()["error"]["code"] == "FORBIDDEN"


def test_patient_cannot_verify_document_extractions(client):
    token = login_patient(client, "+919876540018")
    session_id = create_patient_session(client, token)

    # Attempting extraction verification with patient auth returns 403
    res = client.post(
        f"/api/sessions/{session_id}/documents/fake-doc/extractions/fake-ext/verify",
        json={"status": "verified"},
        headers=auth_header(token),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_cross_patient_speech_transcribe_and_synthesize_forbidden(client):
    token_a = login_patient(client, "+919876540019")
    token_b = login_patient(client, "+919876540020")

    session_a = create_patient_session(client, token_a)
    client.put(
        f"/api/sessions/{session_a}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": True},
        headers=auth_header(token_a),
    )

    # Patient B cannot synthesize on Patient A's session
    res_synth = client.post(
        f"/api/sessions/{session_a}/interview/speech/synthesize",
        json={"question_id": "chief_complaint.description"},
        headers=auth_header(token_b),
    )
    assert res_synth.status_code == 403

    # Patient B cannot transcribe on Patient A's session
    fake_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    res_trans = client.post(
        f"/api/sessions/{session_a}/interview/speech/transcribe",
        files={"audio": ("sample.wav", fake_wav, "audio/wav")},
        data={"question_id": "chief_complaint.description"},
        headers=auth_header(token_b),
    )
    assert res_trans.status_code == 403


def test_expired_or_revoked_token_rejected(client):
    token = login_patient(client, "+919876540021")
    session_id = create_patient_session(client, token)

    # Verify session detail works before logout
    res_before = client.get(f"/api/sessions/{session_id}", headers=auth_header(token))
    assert res_before.status_code == 200

    # Logout
    res_logout = client.post("/api/auth/logout", headers=auth_header(token))
    assert res_logout.status_code == 200

    # Verify subsequent request returns 401
    res_after = client.get(f"/api/sessions/{session_id}", headers=auth_header(token))
    assert res_after.status_code == 401


def test_public_config_no_secret_leakage(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "demo_mode" in data

    # Check text for any accidental secrets or hashes
    text = res.text.lower()
    for sensitive_word in ["secret", "password", "key", "token", "hash", "otp"]:
        assert sensitive_word not in text, f"Potential sensitive word '{sensitive_word}' leaked in /api/config"
