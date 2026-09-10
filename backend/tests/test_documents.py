import io
import uuid
from pathlib import Path

from app.api.deps import DEMO_DOCTOR_ID

STAFF = {"X-Demo-Doctor": "true"}

def fixture(name="prescription"):
    return (Path(__file__).resolve().parents[2] / "ai/document_fixtures" / (name + ".png")).read_bytes()


def _setup_session(client, lang="en", doc_consent=True):
    session_id = str(uuid.uuid4())
    create_res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Document Test Patient", "demo_abha_id": None},
            "hospital_token": f"DOC-{session_id[:6]}",
            "language": lang,
        },
    )
    assert create_res.status_code == 201

    consent_res = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": False,
            "document_processing": doc_consent,
            "share_with_doctor": True,
        },
    )
    assert consent_res.status_code == 200

    flow_res = client.put(
        f"/api/sessions/{session_id}/interview/flow",
        json={"flow_id": "chest_pain"},
    )
    assert flow_res.status_code == 200
    return session_id


def test_upload_prescription_success(client):
    session_id = _setup_session(client, doc_consent=True)

    fake_image = io.BytesIO(fixture())
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("rx_prescription.png", fake_image, "image/png")},
        data={"document_type": "prescription"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["session_id"] == session_id
    assert data["original_filename"] == "rx_prescription.png"
    assert data["media_type"] == "image/png"
    assert data["document_type"] == "prescription"
    assert data["processing_status"] == "mock_fixture"
    assert len(data["sha256_hash"]) == 64
    assert len(data["extractions"]) == 1

    ext = data["extractions"][0]
    assert ext["verification_status"] == "unverified"
    assert ext["confidence"] is None
    assert "medications" in ext["structured_json"]
    meds = ext["structured_json"]["medications"]
    assert len(meds) > 0
    # Checks that Paracetamol or Amoxicillin was extracted
    med_names = [m["name"].lower() for m in meds]
    assert any("paracetamol" in name for name in med_names)


def test_upload_lab_report_success(client):
    session_id = _setup_session(client, doc_consent=True)

    fake_png = io.BytesIO(fixture("lab_report"))
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("blood_test_report.png", fake_png, "image/png")},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["document_type"] == "lab_report"
    assert len(data["extractions"]) == 1

    ext = data["extractions"][0]
    assert ext["verification_status"] == "unverified"
    assert "observations" in ext["structured_json"]
    obs = ext["structured_json"]["observations"]
    assert len(obs) >= 3
    test_names = [o["test_name"].lower() for o in obs]
    assert any("hemoglobin" in t for t in test_names)
    assert any("glucose" in t for t in test_names)


def test_upload_requires_document_consent(client):
    session_id = _setup_session(client, doc_consent=False)

    fake_image = io.BytesIO(fixture())
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("rx.jpg", fake_image, "image/png")},
    )
    assert res.status_code == 403
    data = res.json()
    assert data["error"]["code"] == "DOCUMENT_CONSENT_REQUIRED"


def test_upload_rejects_empty_file(client):
    session_id = _setup_session(client, doc_consent=True)

    empty = io.BytesIO(b"")
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("empty.jpg", empty, "image/png")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_rejects_invalid_media_type(client):
    session_id = _setup_session(client, doc_consent=True)

    fake_exe = io.BytesIO(b"MZ\x90\x00" + b"\x00" * 32)
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("payload.exe", fake_exe, "application/x-msdownload")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_MEDIA_TYPE"


def test_upload_rejects_oversized_file(client):
    session_id = _setup_session(client, doc_consent=True)

    # 11 MB file exceeds 10MB limit
    oversized = io.BytesIO(b"\xff\xd8" + b"\x00" * (11 * 1024 * 1024))
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("huge.jpg", oversized, "image/png")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_list_and_get_documents(client):
    session_id = _setup_session(client, doc_consent=True)

    # Upload 2 documents
    client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("doc1.png", io.BytesIO(fixture()), "image/png")},
    )
    client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("doc2.jpg", io.BytesIO(fixture()), "image/png")},
    )

    list_res = client.get(f"/api/sessions/{session_id}/documents", headers=STAFF)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] == 2
    assert len(list_data["documents"]) == 2

    doc_id = list_data["documents"][0]["id"]
    detail_res = client.get(f"/api/sessions/{session_id}/documents/{doc_id}", headers=STAFF)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == doc_id


def test_document_file_retrieval_endpoint(client):
    session_id = _setup_session(client, doc_consent=True)

    sample_bytes = fixture()
    up_res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("prescription.png", io.BytesIO(sample_bytes), "image/png")},
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]

    file_res = client.get(f"/api/sessions/{session_id}/documents/{doc_id}/file", headers=STAFF)
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "image/png"
    assert file_res.content == sample_bytes


def test_doctor_verify_document_extraction(client):
    session_id = _setup_session(client, doc_consent=True)

    up_res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("rx.jpg", io.BytesIO(fixture()), "image/png")},
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]
    ext_id = up_res.json()["extractions"][0]["id"]

    # Verify extraction as doctor
    verify_res = client.post(
        f"/api/sessions/{session_id}/documents/{doc_id}/extractions/{ext_id}/verify",
        json={
            "status": "verified",
            "notes": "Confirmed current medications against physical prescription.",
        },
        headers={"X-Demo-Doctor": "true"},
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["verification_status"] == "verified"
    assert v_data["verified_by"] == DEMO_DOCTOR_ID
    assert v_data["verified_at"] is not None

    # Check Doctor session detail includes the verified document
    doc_session = client.get(
        f"/api/doctor/sessions/{session_id}",
        headers={"X-Demo-Doctor": "true"},
    )
    assert doc_session.status_code == 200
    doc_data = doc_session.json()
    assert len(doc_data["documents"]) == 1
    assert doc_data["documents"][0]["extractions"][0]["verification_status"] == "verified"


def test_document_facts_do_not_mutate_interview_answers(client):
    session_id = _setup_session(client, doc_consent=True)

    # 1. Check initial interview state has zero answers
    initial_state = client.get(f"/api/sessions/{session_id}/interview", headers=STAFF).json()
    assert len(initial_state["active_answers"]) == 0
    current_q = initial_state["question"]["question_id"]

    # 2. Upload document with multiple extracted medications
    client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("rx.jpg", io.BytesIO(fixture()), "image/png")},
    )

    # 3. Clinical Invariant Check: interview answers must remain unchanged!
    post_upload_state = client.get(f"/api/sessions/{session_id}/interview", headers=STAFF).json()
    assert len(post_upload_state["active_answers"]) == 0
    assert post_upload_state["question"]["question_id"] == current_q
